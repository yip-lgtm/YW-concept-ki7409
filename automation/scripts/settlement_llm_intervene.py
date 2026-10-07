#!/usr/bin/env python3
"""LLM Intervention — auto-lower settlement conditions for stuck agents.

User directive (10/07): "llm iter 介入降條件".

WHY:
  Settlement promotes (all 3 met) / demotes (all 3 fail) / stays flat (1-2 fail).
  A strategy in the neutral zone NEVER moves — it just sits at its level forever.
  That's the problem this script solves.

  Example stuck agent (today's data):
    50-20-Pullback  n=44  PF=1.02  WR=38.6%  RR=1.62
      → WR ≤ 0.5 (fails), PF > 1 (ok), RR > 1 (ok)
      → NOT promoted (WR fails)
      → NOT demoted (PF & RR pass)
      → STUCK FOREVER at lv1

  This is a HIGH-RR strategy (RR 1.62) with slightly-low WR. It should be
  promoted under relaxed WR conditions. But the global settlement config
  applies the same WR > 0.5 threshold to all 11 agents — including
  high-RR/low-WR strategies where WR > 0.5 is the wrong bar.

SOLUTION:
  Per-agent threshold overrides. The LLM reviews each stuck agent's real
  metrics + its strategy character, then proposes relaxed (or tightened)
  thresholds for THAT agent only.

  Example override for 50-20-Pullback:
    min_WR: 0.35   (down from 0.50 — justified: RR 1.62 compensates)
    min_PF: 0.95   (down from 1.00 — PF 1.02 is real but thin)
    min_RR: 1.00   (unchanged — this is the agent's edge)

  Overrides live in automation/config/settlement_overrides.json and are
  applied by daily_settlement.py BEFORE computing promote_ok / demote_ok.

GUARDRAILS (numeric, not LLM-judged):
  - Only agents stuck ≥ min_stuck_days (default 3) in the neutral zone qualify
  - Thresholds can only relax within hard bounds (e.g. WR ∈ [0.30, 0.60])
  - min_n can only relax down to ≥ 5 (never below — sample size matters)
  - Never relax ALL 3 at once for the same agent (would let junk promote)
  - Max 1 override revision per agent per 7 days (prevent thrash)
  - LLM output is JSON-validated; anything unparseable is discarded

Schedule: runs right after daily_settlement.py in strategy-ranking.yml.
"""
from __future__ import annotations
import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

SETTLE_DIR = REPO / "automation" / "reports" / "strategy_settlement"
OVERRIDES_FILE = REPO / "automation" / "config" / "settlement_overrides.json"
CONFIG_FILE = REPO / "automation" / "config" / "ranking_settings.json"
HISTORY_FILE = SETTLE_DIR / "history.jsonl"

AGENT_NAMES = [
    "H-Pattern", "3-Pushes", "Two-Yang", "RSI-Div", "50-20-Pullback",
    "Stair", "B1", "B1-3in1", "Kell-Cycle", "CRT", "OCS-BTC-5m",
]

# Strategy character hints — helps the LLM pick sane thresholds
STRATEGY_CHARACTER = {
    "50-20-Pullback": "High-RR trend pullback. Low WR is EXPECTED and fine (RR compensates). "
                      "Judge on PF + RR, not WR.",
    "CRT":            "High-RR range reversal. WR naturally moderate. RR is the edge.",
    "Stair":          "Trend continuation. Needs momentum; WR should be OK but PF thin is common.",
    "3-Pushes":       "Exhaustion reversal. Counter-trend, so WR can be low if RR is high.",
    "Kell-Cycle":     "Cycle-based. Volatile, expect low WR / high RR profile.",
    "H-Pattern":      "Structural reversal. Moderate WR, moderate RR.",
    "Two-Yang":       "Candle pattern. Low sample count typical.",
    "RSI-Div":        "Mean reversion. Higher WR expected, thin RR.",
    "B1":             "Multi-indicator confluence. Balanced profile.",
    "B1-3in1":        "Multi-asset combined. Diversified, expect moderate both.",
    "OCS-BTC-5m":     "ML/kNN based. BTC 24/7 — different session profile.",
}

# Hard bounds — LLM cannot exceed these
BOUNDS = {
    "min_PF":     {"min": 0.80, "max": 1.50},
    "min_WR":     {"min": 0.30, "max": 0.70},
    "min_RR":     {"min": 0.80, "max": 2.00},
    "min_trades": {"min": 5,    "max": 50},
}

# Global safety
MIN_STUCK_DAYS = 3          # consecutive neutral-zone days before LLM intervenes
MIN_REVISION_DAYS = 7       # don't revise same agent more than once per 7 days
MAX_RELAX_AT_ONCE = 2       # never relax all 3 metrics for the same agent


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[llm-intervene {ts}] {msg}", flush=True)


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception as e:
        log(f"WARN: config read failed: {e}")
        return {}


def load_overrides() -> dict:
    if not OVERRIDES_FILE.exists():
        return {}
    try:
        return json.loads(OVERRIDES_FILE.read_text())
    except Exception:
        return {}


def save_overrides(data: dict):
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_history() -> list[dict]:
    """Load settlement history.jsonl (one record per day)."""
    if not HISTORY_FILE.exists():
        return []
    records = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return records


def find_stuck_agents(min_stuck_days: int) -> dict[str, dict]:
    """Find agents stuck in neutral zone for ≥ min_stuck_days consecutive days.

    Returns {agent: {stuck_days, latest_metrics, history}}
    """
    history = load_history()
    if len(history) < min_stuck_days:
        log(f"History has only {len(history)} days (need {min_stuck_days}) — nothing to do")
        return {}

    # Take last N days
    recent = history[-min_stuck_days:]

    # Build per-agent neutral streak
    streaks: dict[str, int] = {}
    for rec in recent:
        for r in rec.get("results", []):
            name = r.get("strategy")
            if not name:
                continue
            flat = (not r.get("promoted")) and (not r.get("demoted"))
            # Only count as "stuck" if agent had enough trades to be evaluable
            evaluable = r.get("n_trades", 0) >= 5
            if flat and evaluable:
                streaks[name] = streaks.get(name, 0) + 1
            else:
                # Reset streak (promoted/demoted/insufficient breaks it)
                if name in streaks:
                    del streaks[name]

    stuck = {k: v for k, v in streaks.items() if v >= min_stuck_days}
    if stuck:
        log(f"Found {len(stuck)} stuck agent(s) (≥{min_stuck_days}d neutral + n≥5): {list(stuck.keys())}")
    else:
        log(f"No stuck agents (checked {len(AGENT_NAMES)} agents over {len(recent)} days)")
    return stuck


def recently_revised(overrides: dict, min_days: int = MIN_REVISION_DAYS) -> set[str]:
    """Agents revised within min_days — skip them to prevent thrash."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_days)
    out = set()
    for agent, ov in overrides.items():
        if agent.startswith("_"):
            continue
        ts = ov.get("last_revised")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                out.add(agent)
        except Exception:
            pass
    return out


def call_minimax(prompt: str, system: str) -> str:
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return ""
    try:
        r = requests.post(
            "https://api.minimax.io/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "MiniMax-M3",
                "max_tokens": 2048,   # room for think + JSON
                "temperature": 0.2,   # less rambling, more format-compliant
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"  LLM call failed: {e}")
        return ""


def parse_thresholds(content: str) -> dict | None:
    """Extract JSON thresholds from LLM response. Returns None if unparseable.

    Robust to:
      - <think>...</think> blocks (MiniMax-M3 emits these despite instructions)
      - Markdown code fences (```json ... ```)
      - Prose before/after the JSON block
    """
    if not content:
        return None

    # 1. Strip <think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE)
    # Unclosed <think> (LLM ran out of tokens mid-thought) — the actual JSON
    # usually came BEFORE the think block, so keep the part before it.
    if "<think>" in cleaned and "</think>" not in cleaned:
        cleaned = cleaned.split("<think>")[0]
    cleaned = cleaned.replace("</think>", "")

    # 2. Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    # 3. Balanced-brace scan — find first {...} that parses
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
        start = cleaned.find("{", start + 1)

    # 4. Fallback: regex for individual fields (LLM emitted prose-ish JSON)
    out = {}
    for key in ("min_PF", "min_WR", "min_RR", "min_trades"):
        m = re.search(rf'"{key}"\s*:\s*([0-9.]+)', cleaned)
        if m:
            try:
                out[key] = float(m.group(1))
            except Exception:
                pass
    m = re.search(r'"action"\s*:\s*"(relax|tighten|hold)"', cleaned)
    if m:
        out["action"] = m.group(1)
    if out:
        log("  (used regex fallback extractor)")
        return out
    return None


def clamp(name: str, value) -> float | int | None:
    """Clamp an LLM-proposed value into hard bounds."""
    if value is None:
        return None
    b = BOUNDS.get(name)
    if not b:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    v = max(b["min"], min(b["max"], v))
    if name == "min_trades":
        return int(round(v))
    return round(v, 3)


def intervene_agent(agent: str, metrics: dict, stuck_days: int,
                    base_cfg: dict) -> dict | None:
    """Ask LLM for threshold overrides for one stuck agent."""
    d_s = base_cfg.get("daily_settlement", {})
    base_pf = d_s.get("min_PF", 1.0)
    base_wr = d_s.get("min_WR", 0.5)
    base_rr = d_s.get("min_RR", 1.0)
    base_n = d_s.get("min_trades", 10)

    char = STRATEGY_CHARACTER.get(agent, "Unknown strategy character.")

    prompt = f"""你係 settlement condition reviewer。今日有 agent 卡喺 neutral zone 好耐，promotion 唔到、demotion 又唔應該。

AGENT: {agent}
STUCK: 連續 {stuck_days} 日 neutral zone (promote/demote 都唔觸發)

實際 metrics (7d rolling, n={metrics.get('n_trades', 0)}):
  PF  = {metrics.get('profit_factor', 0):.3f}   (promote 門檻 > {base_pf})
  WR  = {metrics.get('win_rate', 0)*100:.1f}%    (promote 門檻 > {base_wr*100:.0f}%)
  RR  = {metrics.get('rr_ratio', 0):.3f}   (promote 門檻 > {base_rr})
  n   = {metrics.get('n_trades', 0):<8}  (最少要求 ≥ {base_n})

呢個 strategy 嘅性格 (重要，唔好當全部 strategy 一樣):
  {char}

CONFLICT:
  Global 門檻係為「平均」strategy 設嘅，但呢個 agent 嘅 profile 可能唔同。
  例如 50-20-Pullback 係 high-RR / low-WR 設計，WR 38% 對佢係正常，唔應該因為 WR 唔夠就永遠唔升 lv。

你嘅任務: 建議呢個 agent 專屬嘅 promotion 門檻 (per-agent override)。
- 可以放寬 (relax) 令佢終於可以升 lv
- 亦可以收緊 (tighten) 令佢更加唔容易升 (如果實際表現真係差)
- **最多只可以放寬 2 個指標** (唔准 3 個全放寬 — 咁樣垃圾都升到 lv)
- min_trades 最低只可以到 5 (樣本量要有意義)
- 門檻範圍硬限制: PF ∈ [0.80, 1.50], WR ∈ [0.30, 0.70], RR ∈ [0.80, 2.00], n ∈ [5, 50]

請用 EXACT format 回覆 (JSON only, 唔好其他文字):

REASONING: <一句話點解咁調>

{{
  "min_PF": <number>,
  "min_WR": <number, 0-1 小數>,
  "min_RR": <number>,
  "min_trades": <integer>,
  "action": "relax" | "tighten" | "hold"
}}

禁止 <think> 標籤。直接輸出。"""

    system = (f"你係 {agent} 嘅 settlement condition reviewer。"
              "你調整嘅係 promotion 門檻，唔係 strategy 參數。"
              "要基於實際數據 + strategy 性格做判斷，唔可以離譜。")

    response = call_minimax(prompt, system)
    if not response:
        return None

    reasoning = ""
    rm = re.search(r"REASONING:\s*(.+)", response)
    if rm:
        reasoning = rm.group(1).strip()[:200]

    parsed = parse_thresholds(response)
    if not parsed:
        log(f"  {agent}: LLM response unparseable, skipping")
        log(f"      response tail: {response[-300:]!r}")
        return None

    action = parsed.get("action", "hold")
    if action == "hold":
        log(f"  {agent}: LLM says hold (no change) — recording decision only")
        return {"action": "hold", "reasoning": reasoning,
                "response_raw": response[:800]}

    # Extract + clamp proposed values
    proposed = {
        "min_PF": clamp("min_PF", parsed.get("min_PF")),
        "min_WR": clamp("min_WR", parsed.get("min_WR")),
        "min_RR": clamp("min_RR", parsed.get("min_RR")),
        "min_trades": clamp("min_trades", parsed.get("min_trades")),
    }
    proposed = {k: v for k, v in proposed.items() if v is not None}

    if not proposed:
        log(f"  {agent}: no valid thresholds in response, skipping")
        return None

    # Count how many are RELAXED vs base
    base = {"min_PF": base_pf, "min_WR": base_wr, "min_RR": base_rr, "min_trades": base_n}
    relaxed = 0
    tightened = 0
    for k, v in proposed.items():
        if v < base[k]:
            relaxed += 1
        elif v > base[k]:
            tightened += 1

    if relaxed > MAX_RELAX_AT_ONCE:
        log(f"  {agent}: REJECT — LLM relaxed {relaxed} metrics (max {MAX_RELAX_AT_ONCE})")
        return None

    log(f"  {agent}: {action} — relaxed {relaxed}, tightened {tightened}")
    for k, v in proposed.items():
        log(f"      {k}: {base[k]} → {v}")

    return {
        "action": action,
        "overrides": proposed,
        "relaxed_count": relaxed,
        "tightened_count": tightened,
        "reasoning": reasoning,
        "response_raw": response[:800],
    }


def main() -> int:
    HKT = timezone(timedelta(hours=8))
    now = datetime.now(timezone.utc)

    log("=" * 60)
    log("Settlement LLM Intervention — 降條件 for stuck agents")
    log("=" * 60)

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        log("MINIMAX_API_KEY not set — skipping (no LLM available)")
        return 0

    base_cfg = load_config()
    if not base_cfg:
        log("Cannot read ranking_settings.json — skipping")
        return 0

    d_s = base_cfg.get("daily_settlement", {})
    min_stuck = d_s.get("min_stuck_days", MIN_STUCK_DAYS)

    overrides = load_overrides()
    skip_recent = recently_revised(overrides)
    if skip_recent:
        log(f"Skipping (revised within {MIN_REVISION_DAYS}d): {sorted(skip_recent)}")

    # Ensure _meta exists
    if "_meta" not in overrides:
        overrides["_meta"] = {
            "_comment": "Per-agent settlement threshold overrides — managed by "
                        "settlement_llm_intervene.py. Applied by daily_settlement.py "
                        "BEFORE computing promote_ok / demote_ok.",
            "created": now.isoformat(),
            "runs": 0,
        }

    stuck = find_stuck_agents(min_stuck)
    if not stuck:
        log("Nothing to do — no stuck agents.")
        return 0

    # Get latest metrics for each stuck agent
    history = load_history()
    latest: dict[str, dict] = {}
    for rec in reversed(history):
        for r in rec.get("results", []):
            nm = r.get("strategy")
            if nm and nm not in latest:
                latest[nm] = r

    # Build work list
    work = []
    for agent, stuck_days in stuck.items():
        if agent in skip_recent:
            log(f"{agent}: skipped (recently revised)")
            continue
        m = latest.get(agent)
        if not m:
            continue
        work.append((agent, m, stuck_days))

    if not work:
        log("All stuck agents are on cooldown — nothing to do.")
        return 0

    log(f"Intervening on {len(work)} agent(s) in parallel...")
    results = {}
    with ThreadPoolExecutor(max_workers=min(4, len(work))) as pool:
        futures = {
            pool.submit(intervene_agent, agent, m, days, base_cfg): agent
            for agent, m, days in work
        }
        for fut in as_completed(futures):
            agent = futures[fut]
            try:
                results[agent] = fut.result()
            except Exception as e:
                log(f"  {agent}: exception {type(e).__name__}: {e}")
                results[agent] = None

    # Apply results to overrides
    applied = 0
    for agent, res in results.items():
        if not res:
            continue
        entry = {
            "last_revised": now.isoformat(),
            "stuck_days_at_revision": stuck[agent],
            "action": res.get("action"),
            "reasoning": res.get("reasoning", ""),
            "response_raw": res.get("response_raw", ""),
        }
        if res.get("overrides"):
            entry["overrides"] = res["overrides"]
            entry["relaxed_count"] = res.get("relaxed_count", 0)
            entry["tightened_count"] = res.get("tightened_count", 0)
            applied += 1
        overrides[agent] = entry

    overrides["_meta"]["runs"] = overrides["_meta"].get("runs", 0) + 1
    overrides["_meta"]["last_run"] = now.isoformat()
    overrides["_meta"]["last_applied"] = applied
    overrides["_meta"]["last_log"] = [
        {"agent": a, "action": (r or {}).get("action", "error")}
        for a, r in results.items()
    ]

    save_overrides(overrides)
    log(f"Saved overrides → {OVERRIDES_FILE}")
    log(f"Applied {applied}/{len(work)} threshold override(s)")
    log(f"  Total agents with overrides: {len([k for k in overrides if not k.startswith('_')])}")

    if applied:
        log("Next settlement run will use these thresholds.")
        log("  (Revert: git checkout automation/config/settlement_overrides.json)")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[llm-intervene] UNCAUGHT: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(99)
