# Ops Notes

Operational notes that are not about any single strategy: how this
repository's automation actually runs, what has bitten us, and where the
tooling lives.

---

## 1. The live system was silent for a day (2026-10-21)

### What happened

Between roughly 2026-10-20 17:00 UTC and 2026-10-21 16:50 UTC every scan
reported `LLM-confirmed signals: 0`, and the sys-engineer flagged
H-Pattern and 3-Pushes as "lazy — 0 signals in 24 hours". The detectors
were firing the whole time. Nothing downstream of the grade step
survived.

### Root cause

Three scripts called `chat(prompt, system=system)` where no `system`
variable existed in scope:

| script | function | effect |
|---|---|---|
| `automation/scripts/live_scan.py` | `llm_grade` | every signal graded 0 → skipped |
| `automation/scripts/llm_iteration_scientist.py` | `call_llm_scientist` | every diagnosis "no parse" |
| `automation/scripts/sys_engineer.py` | `diagnose_with_llm` | every diagnosis empty |

`NameError` was swallowed by a broad `except Exception`, so the system
degraded silently instead of failing loudly.

### The diagnostic trap

Earlier runs in the log said `http 429`, which is real and still true —
the MiniMax Token Plan runs on a five-hour window and does run out. It
is also a red herring: it made the symptom look like a quota problem.
The `NameError` only appeared in the two most recent runs, once the 429s
had cleared.

**Lesson: a symptom that stays "429" after the quota recovers is not a
quota problem.** Read the newest run log, not the pattern.

### Fixes

- `9f58f0f9` — one `chat()` call per signal with the system prompt
  passed explicitly, real API errors surfaced in the reason field. Each
  signal had been burning two LLM calls (a `requests.post` for the
  status code, body discarded, then `chat()` again); it is now one.
- `automation/scripts/test_llm_callers.py` — regression test: a static
  check that no `chat()` call references an undefined name, plus
  functional checks on the three entry points. No network, no API key.

---

## 2. The backtest was silently discarding three strategies

`historical_backtest.build_trade` required the direction string to
already be `long` or `short`. The detectors do not agree on the
spelling:

| strategy | raw direction |
|---|---|
| 3-Pushes | `up` / `down` |
| RSI-Div | `bullish` / `bearish` |
| CRT | `bullish` / `bearish` |
| Kell-Cycle | sometimes `none` |

The live system copes because `live_scan._normalize_direction` maps all
of them before a signal is built. The backtest did not, so 100% of
3-Pushes, RSI-Div and CRT trades were dropped.

The consequences were larger than the missing trades:

- the deep 5m track covered 5 strategies instead of 8
- the 1h "second independent track" held zero trades for those three
- so the 2026-10-20 "0 of 9 configurations survive" verdict marked
  3-Pushes and CRT **overfit** when the real reason was that the second
  track had no data for them at all

**Lesson: any harness that calls a detector directly must normalise the
output the same way the live path does.** See
`automation/scripts/audit_detector_formats.py`, which prints what each
detector actually emits so a format change is visible.

---

## 3. The nightly backtest output was never committed

`daily_auto_push.py`'s `WATCHED_PATHS` did not include
`automation/reports/historical_backtest/`, and the strategy-ranking
workflow's own commit step only adds `automation/reports/strategy_ranking/`.
So the workflow recomputed the 1h track every night and the result was
discarded; the copy in the repository stayed frozen at whatever was last
committed by hand.

`backtest_optimizer.py` reads that same path as its second track, so
anything reading it outside the CI run that produced it was reading a
stale sample. Fixed in `32d8814a`.

---

## 4. MGC=F and GC=F are the same metal

Measured over the ten minutes where both fired: median price difference
$0.10 on ~$4,140 — 0.0024% — and every sample inside 0.05%. An earlier
comment in `live_scan.py` claimed their closes "agree only about a
quarter of the time", which is why the "do not run both" rule was only
ever applied to Argon-Gold and never carried across to CRT.

On 2026-10-21 CRT opened the same gold setup twice: MGC=F long @ 4150.60
and GC=F long @ 4150.30, same bar, same direction, two positions on one
underlying. Fixed in `56d3b025` — `CRT_BAN_TICKERS = {"GC=F"}`. CRT keeps
MGC=F (112 closed trades of history, and a 10-oz contract sizes a
$50-risk book ten times finer than GC's 100 oz); GC=F stays for Argon,
which needs the front-month contract.

The four index futures in the ticker list are genuinely different
underlyings — `M2K=F` is Micro **Russell**, not a second Nasdaq — so no
other pair shares this hazard.

---

## 5. GitHub Actions scheduling is running at 6.2% of design

Designed: 1,157 scheduled runs per day across the repo. Actual in a
24-hour window: 72. Every high-frequency workflow — `live-scan`,
`ocs-btc-5m`, `pipeline-scheduler`, `pipeline-watchdog`,
`always-on-trigger-2/3` — got exactly 6 runs regardless of whether it
is scheduled every 5 or every 15 minutes. `unified-pipeline` got 12.
The 16:00 UTC daily `strategy-ranking` schedule had still not fired
49 minutes past its time.

`workflow_dispatch` always works, which is what makes manual runs the
reliable way to verify anything here.

---

## 6. Sandbox pitfalls that cost real time

- **`write` must target a path inside the workspace.** A patch script
  written to `/tmp/patch_hbt.py` was rejected with "Workspace path
  escapes Cloud Host root", and every patch in it was lost. This is what
  killed the 2026-10-21 rescue of session `404738755453207` (the
  "Coder" session): it died of `2013 context window exceeds limit` with
  its last nine patches unapplied.
- **`pkill -f <script>.py` kills the shell issuing it** — the pattern
  matches the pkill command's own command line.
- **`git clone` needs `GIT_SSL_NO_VERIFY=true`** (no CA bundle in the
  sandbox). Push with the token in the remote URL:
  `git push "https://x-access-token:$TOKEN@github.com/yip-lgtm/YW-concept-ki7409.git" HEAD:main`.
- **`pip install` needs `--break-system-packages`** and an explicit
  index URL.
- **`mavis session messages` has no usable cursor.** The `before`
  parameter is ignored; long transcripts truncate into
  `.mavis/tool-results/<session>/<call>/chunks`, and grepping those
  files is cheaper than pulling the history into context.
- **A dead session cannot be revived.** Every turn adds an error
  message, which makes the context larger. Open a new session and hand
  over a checklist, never a transcript.
- **Yahoo Finance returns 429 from the sandbox**, so the 1h track can
  only be regenerated by CI. The Polygon deep history is in the
  repository as CSV and can be read locally.

---

## 7. Tools built for these problems

| script | what it does |
|---|---|
| `automation/scripts/compare_backtest_tracks.py` | compares the live, 1h and deep 5m tracks with instrument and period matched |
| `automation/scripts/audit_detector_formats.py` | prints what direction/strength format each detector emits |
| `automation/scripts/test_llm_callers.py` | regression test for the LLM call sites |
| `automation/scripts/test_crt_gold_dedup.py` | regression test for the CRT gold gate |
| `automation/scripts/historical_backtest.py --mode deep5m` | runs the detectors over real five-minute history |

See `automation/reports/historical_backtest/deep5m_track_review_2026-10-21.md`
for the three-sample cross-validation.
