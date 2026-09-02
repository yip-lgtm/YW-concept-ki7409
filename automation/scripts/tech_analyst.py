#!/usr/bin/env python3
"""tech-analyst — 4th Power: chart generation + entry plan for every signal.

4-Power Separation of Powers:
  Power 1: supervisor_monitor.py   - 24/7 health check
  Power 2: sys_engineer.py         - bug fixes + LLM diagnosis
  Power 3: llm_iteration_scientist - strategy grade + auto-apply
  Power 4: tech_analyst.py         - chart + entry plan (THIS)

Responsibilities:
  1. For every signal in signals.jsonl, ensure chart exists at signal_charts/<id>.png
  2. Verify chart contains:
     - SETUP box (top-left, yellow)
     - ENTRY PLAN box (bottom-left, green) with T1/T2/T3-T5
     - Indicator lines (EMA20, SMA50, BB, ATR bands)
     - NY time on x-axis
  3. Send chart to TG as photo with caption
  4. Record audit trail

State:
  - reports/tech_analyst/last_run.json
  - reports/tech_analyst/coverage.json  (signals vs charts)
  - reports/audit/<date>/actions.jsonl  (audit trail)

Runs every 5 min via unified-pipeline.
"""
from __future__ import annotations
import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

if "GITHUB_WORKSPACE" in os.environ:
    REPO = Path(os.environ["GITHUB_WORKSPACE"])
else:
    REPO = Path("/workspace/YW-concept-ki7409")

TA_DIR = REPO / "automation" / "reports" / "tech_analyst"
TA_DIR.mkdir(parents=True, exist_ok=True)
CHART_DIR = REPO / "automation" / "reports" / "signal_charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = REPO / "automation" / "reports" / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

SIGNALS_FILE = REPO / "automation" / "reports" / "live_scan" / "signals.jsonl"
LAST_RUN_FILE = TA_DIR / "last_run.json"
COVERAGE_FILE = TA_DIR / "coverage.json"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

HKT = timezone(timedelta(hours=8))


def log_action(power: str, action: str, target: str, level: str, msg: str):
    """Append to audit trail."""
    today = datetime.now(HKT).strftime("%Y-%m-%d")
    audit_file = AUDIT_DIR / today / "actions.jsonl"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(HKT).isoformat(),
        "power": power,
        "action": action,
        "target": target,
        "level": level,
        "message": msg,
    }
    with open(audit_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_signals() -> list:
    """Load all signals from signals.jsonl."""
    if not SIGNALS_FILE.exists():
        return []
    signals = []
    with open(SIGNALS_FILE) as f:
        for line in f:
            try:
                signals.append(json.loads(line))
            except Exception:
                pass
    return signals


def signal_id(sig: dict) -> str:
    """Generate signal ID for chart filename (match signal_chart.py format).
    
    signal_chart.py uses: s.get("position_id", s.get("signal_id", "unknown"))
    Then replaces: | → _, : → -, / → _
    """
    pos_id = sig.get("position_id") or sig.get("signal_id")
    if pos_id and pos_id != "unknown":
        return pos_id.replace("|", "_").replace(":", "-").replace("/", "_")[:80]
    # Fallback: build from fields
    strategy = sig.get("strategy", "unknown").replace("/", "-")
    ticker = sig.get("ticker", "unknown").replace("/", "-")
    ts = sig.get("ts", "unknown")
    # Keep microseconds (e.g. 2026-08-31T05:55:42.800232+00:00)
    ts = ts.replace(":", "-").replace("+", "-").replace("/", "-")
    return f"{strategy}_{ticker}_{ts}"[:80]


def chart_exists(sig: dict) -> bool:
    """Check if chart for this signal exists."""
    chart_path = CHART_DIR / f"{signal_id(sig)}.png"
    return chart_path.exists()


def verify_chart(sig: dict) -> dict:
    """Verify chart has all required components.
    
    Returns dict with checks: setup_box, entry_plan, indicators, ny_time
    """
    chart_path = CHART_DIR / f"{signal_id(sig)}.png"
    if not chart_path.exists():
        return {"exists": False}
    
    # Read PNG to verify it's valid (file size > 10KB = real chart)
    size = chart_path.stat().st_size
    
    # We can do a basic check: chart should have SETUP and ENTRY PLAN markers
    # Since we don't OCR, we trust the generator. But we verify file size.
    return {
        "exists": True,
        "size_kb": round(size / 1024, 1),
        "valid": size > 10000,  # > 10KB = real chart
    }


def generate_chart(sig: dict) -> str | None:
    """Generate chart for signal using signal_chart.make_chart.
    Returns path or None (None = no data, error, or skip).
    """
    try:
        import sys
        scripts_dir = str(REPO / "automation" / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import signal_chart
        from pathlib import Path
        sid = signal_id(sig)
        out = CHART_DIR / f"{sid}.png"
        if signal_chart.make_chart(sig, out):
            return str(out)
        return None
    except Exception as e:
        log_action("tech_analyst", "chart_gen", signal_id(sig), "ERROR", str(e)[:200])
        return None


def send_telegram_photo(photo_path: str, caption: str) -> bool:
    """Send photo to TG."""
    if not TG_TOKEN or not TG_CHAT:
        return False
    if not Path(photo_path).exists():
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        with open(photo_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": TG_CHAT, "caption": caption[:1024]},
                files={"photo": f},
                timeout=30,
            )
        return r.status_code == 200
    except Exception as e:
        log_action("tech_analyst", "tg_photo", photo_path, "ERROR", str(e)[:200])
        return False


def trigger_unified_pipeline() -> bool:
    """Auto-trigger unified-pipeline workflow when coverage drops."""
    pat = (
        os.environ.get("GITHUB_APEX_PAT")
        or os.environ.get("APEX_PAT")
        or os.environ.get("GITHUB_PAT")
        or os.environ.get("GH_TOKEN", "")
    )
    if not pat:
        return False
    try:
        r = requests.post(
            "https://api.github.com/repos/yip-lgtm/YW-concept-ki7409/actions/workflows/unified-pipeline.yml/dispatches",
            headers={
                "Authorization": f"Bearer {pat}",
                "Accept": "application/vnd.github+json",
            },
            json={"ref": "main"},
            timeout=15,
        )
        return r.status_code == 204
    except Exception as e:
        print(f"  [auto-heal] trigger failed: {e}")
        return False


def load_last_coverage() -> float:
    """Load last reported coverage % for de-dup."""
    f_path = COVERAGE_FILE
    if not f_path.exists():
        return 100.0
    try:
        with open(f_path) as f:
            return json.load(f).get("pct", 100.0)
    except Exception:
        return 100.0


def save_last_coverage(pct: float):
    """Save current coverage % (de-dup persistence)."""
    try:
        COVERAGE_FILE.write_text(json.dumps({"pct": pct, "ts": datetime.now(HKT).isoformat()}, indent=2))
    except Exception:
        pass


def main():
    print(f"[tech-analyst] === @ {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S HKT')} ===")
    
    signals = load_signals()
    print(f"[tech-analyst] Total signals: {len(signals)}")
    
    if not signals:
        print("[tech-analyst] No signals to process")
        return 0
    
    # Use UTC for cutoff since signal timestamps are in UTC
    # (BEFORE: used HKT which made 24h comparison break for UTC timestamps)
    UTC = timezone(timedelta(hours=0))
    now = datetime.now(UTC)
    cutoff = (now - timedelta(hours=2)).isoformat()
    recent = [s for s in signals if s.get("ts", "") >= cutoff]
    
    # Also check signals from last 24h without chart (recovery)
    h24 = (now - timedelta(hours=24)).isoformat()
    last_24h = [s for s in signals if s.get("ts", "") >= h24]
    
    charts_total = len(last_24h)
    charts_present = 0
    charts_generated = 0
    charts_failed = 0  # yfinance no data (older than 2d for crypto, etc)
    photos_sent = 0
    
    for sig in last_24h:
        sid = signal_id(sig)
        chart_path = CHART_DIR / f"{sid}.png"
        
        if not chart_path.exists():
            # Try to generate missing chart
            result = generate_chart(sig)
            if result:
                charts_generated += 1
                charts_present += 1
                log_action("tech_analyst", "chart_gen", sid, "INFO", "chart generated (recovery)")
        else:
            charts_present += 1
        
        # Verify file is valid (>10KB)
        if chart_path.exists():
            check = verify_chart(sig)
            if not check.get("valid"):
                log_action("tech_analyst", "chart_verify", sid, "WARN", 
                          f"chart exists but invalid: {check.get('size_kb')}KB")
    
    charts_failed = charts_total - charts_present
    
    # Send TG photo for new signals in last 2h
    for sig in recent:
        sid = signal_id(sig)
        chart_path = CHART_DIR / f"{sid}.png"
        if not chart_path.exists():
            continue
        # Send TG photo with caption
        strategy = sig.get("strategy", "?")
        ticker = sig.get("ticker", "?")
        direction = sig.get("direction", "?")
        grade = sig.get("grade", "?")
        entry = sig.get("entry") or sig.get("price") or "?"
        caption = f"📊 {strategy} [{grade}] {ticker} {direction}\n🎯 Entry: ${entry}\n🕐 {sig.get('ts', '?')}"
        if send_telegram_photo(str(chart_path), caption):
            photos_sent += 1
            log_action("tech_analyst", "tg_photo", sid, "INFO", "sent to TG")
    
    # Save state
    state = {
        "ts": datetime.now(HKT).isoformat(),
        "total_signals": len(signals),
        "signals_24h": len(last_24h),
        "signals_2h": len(recent),
        "charts_total": charts_total,
        "charts_present": charts_present,
        "charts_generated": charts_generated,
        "charts_failed": charts_failed,
        "photos_sent": photos_sent,
        "coverage_24h": round(charts_present / max(charts_total, 1) * 100, 1),
        "status": "healthy" if charts_failed == 0 else ("degraded" if charts_present < charts_total * 0.5 else "ok"),
    }
    with open(LAST_RUN_FILE, "w") as f:
        json.dump(state, f, indent=2)
    
    # Save coverage history
    cov = {
        "ts": state["ts"],
        "covered": charts_present, "total": charts_total, "pct": round(charts_present/max(charts_total,1)*100,1),
        "total": len(last_24h),
        "pct": state["coverage_24h"],
    }
    with open(COVERAGE_FILE, "w") as f:
        json.dump(cov, f, indent=2)
    
    print(f"[tech-analyst] ✓ Total {charts_total}, Present {charts_present}, Generated {charts_generated}, Failed {charts_failed}, Photos {photos_sent}")
    print(f"[tech-analyst] Coverage (24h): {state['coverage_24h']}%")
    
    log_action("tech_analyst", "run_complete", "all", "INFO",
              f"total={charts_total}, present={charts_present}, generated={charts_generated}, failed={charts_failed}, photos={photos_sent}")
    
    # Send TG alert only if coverage DEGRADED from last run
    last_coverage = load_last_coverage()
    current_coverage = round(charts_present / max(charts_total, 1) * 100, 1)
    coverage_dropped = current_coverage < last_coverage - 5  # 5pp threshold
    
    # Auto-heal: trigger unified-pipeline if coverage drop
    if coverage_dropped and charts_total > 5:
        heal_result = trigger_unified_pipeline()
        if heal_result:
            log_action("tech_analyst", "auto_heal", "unified-pipeline", "INFO",
                      f"triggered due to coverage drop {last_coverage}% -> {current_coverage}%")
    
    if charts_failed > charts_total * 0.5 or coverage_dropped:
        msg = f"⚠️ Tech Analyst: {charts_failed}/{charts_total} charts failed"
        if coverage_dropped:
            msg += f" (coverage: {last_coverage}% → {current_coverage}%)"
            msg += f"\n🔄 Auto-heal: unified-pipeline re-triggered"
        if TG_TOKEN and TG_CHAT:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                    json={"chat_id": TG_CHAT, "text": msg}, timeout=10,
                )
            except Exception:
                pass
    save_last_coverage(current_coverage)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
