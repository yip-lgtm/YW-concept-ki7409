# 4 權分立 + 問責制 (4-Power Separation + Accountability)

> **Date**: 2026-08-28 v1  
> **Architecture**: 4 powers, mutually exclusive, audit-trailed

## 1 句话总结

**4 個獨立嘅 sub-agents 互相制衡，每個有明確職責、權限、問責範圍，failure 要被 recorded + reviewed。**

---

## 4 權架構

```
                  ┌────────────────────────────────────────┐
                  │   Power 1: SUPERVISOR  (監督者)         │
                  │   • 職責: Health check 11 個 agents    │
                  │   • 權限: Read-only                     │
                  │   • 唔可以做: Auto-fix, 落單             │
                  │   • 問責: 冇 detect 到 BUG = supervisor  │
                  └────────────────┬───────────────────────┘
                                   │ 報 BUG/WARN
                                   ▼
┌────────────────────┐    ┌────────────────────┐    ┌────────────────────┐
│  Power 3:          │◄───┤   Power 2:         ├───►│  Power 4:          │
│  10 STRATEGY       │    │   SYSTEM ENGINEER  │    │  LLM ITERATION     │
│  AGENTS            │    │   (系統工程師)     │    │  SCIENTIST         │
│  (執行者)          │    │   • 職責: Auto-fix │    │  (科學家)          │
│  • 職責: Trade     │    │   • 權限: Write   │    │  • 職責: Optimize │
│  • 權限: Signal    │    │   • 唔可以做: Trade │    │  • 權限: Param     │
│  • 唔可以做:       │    │   • 問責: 漏 fix  │   │  • 唔可以做: Signal │
│    Self-monitor    │    │   = sys-engineer   │    │  • 問責: 錯 apply  │
│  • 問責: Loss      │    │                    │    │  = iter-scientist  │
│    = strategy      │    │                    │    │                    │
└────────────────────┘    └────────────────────┘    └────────────────────┘
        │                          │                          │
        └──────────────────────────┴──────────────────────────┘
                                   │
                          Audit Trail (問責記錄)
                                   │
                                   ▼
                  automation/reports/audit/<date>/actions.jsonl
```

---

## 問責矩陣 (Accountability Matrix)

| Power | 職責 (Duty) | 權限 (Permission) | 不能做 (Cannot Do) | 失敗問責 (Failure Accountability) |
|-------|-------------|-------------------|-------------------|----------------------------------|
| **1. Supervisor** | Health check 11 agents | Read supervisor/, live_scan/ | Auto-fix, change code, trade | 漏 BUG → supervisor logged, 唔 detect = supervisor 失敗 |
| **2. System Engineer** | Auto-fix lazy + BUG | Write src/, yw_grader.py | Trade, change strategy logic | 漏 fix = sys-engineer 失敗, false fix = sys-engineer 失敗 |
| **3. Strategy Agents** | Generate trade signals | Write signals.jsonl | Self-monitor, change code | 連續 loss = strategy 失敗, 假 signal = strategy 失敗 |
| **4. LLM Iteration Scientist** | Self-optimize params | Write yw_indicators.py | Trade, suppress agent | 錯 apply = iter-sci 失敗, 過度 apply = iter-sci 失敗 |

---

## 互不包備 (Mutual Exclusivity)

| Power | 唔可以干涉 (Cannot Interfere) |
|-------|------------------------------|
| Supervisor | 改 code, 落單, 改 strategy |
| System Engineer | Trade, suppress signal, 改 strategy logic |
| Strategy Agents | Self-monitor, 改 detector, 改 strategy ranking |
| LLM Iteration Sci | Suppress agent, trade, override supervisor |

---

## 問責流程 (Accountability Flow)

```
Agent fails
   ↓
Supervisor detects (Power 1)
   ↓
Report to System Engineer (Power 2)
   ↓
Sys-eng auto-fixes OR asks LLM Iteration Sci (Power 4) for help
   ↓
Iteration Sci suggests (Power 4)
   ↓
Sys-eng applies (Power 2)
   ↓
Strategy Agent resumes (Power 3)
   ↓
Audit trail records all 4 actions
```

---

## Audit Trail (問責記錄)

每個 power 嘅 action 會被 logged:

`automation/reports/audit/<date>/actions.jsonl`

```json
{
  "timestamp": "2026-08-28T01:30:00+08:00",
  "power": "supervisor",
  "action": "health_check",
  "target": "yw-50-20-pullback",
  "result": "BUG",
  "details": "KeyError: 'yw_indicators'",
  "accountable_to": "Power 1 (Supervisor)"
}
```

---

## Failure Scenarios & Accountability

| Scenario | Power Failed | Action |
|----------|--------------|--------|
| Agent 0 signals 24h | (no failure — could be market) | Log only |
| Agent BUG 6h+ | Supervisor 冇 detect | Supervisor on warning list |
| Sys-eng 漏 fix | Sys-eng 失敗 | Log, retry next hour |
| Iter-sci 錯 apply | Iter-sci 失敗 | Revert, log, learn |
| Agent loss 連續 10 trades | Strategy 失敗 | Mark for iter-sci re-analyze |
| All 4 powers down | Catastrophic | Page user immediately |

---

## Files & Sub-Agents

| Power | Script | Workflow | Audit |
|-------|--------|----------|-------|
| 1. Supervisor | `automation/scripts/strategy_supervisor.py` | `supervisor-monitor.yml` (every 5 min) | supervisor reports |
| 2. System Engineer | `automation/scripts/sys_engineer.py` | `sys-engineer.yml` (hourly) | sys_eng reports |
| 3. Strategy Agents | `automation/scripts/live_scan.py` | `live-scan.yml` (every 5 min) | signals.jsonl + trades.jsonl |
| 4. LLM Iteration Sci | `automation/scripts/llm_iteration_scientist.py` | `llm-iteration-scientist.yml` (00:00 HKT) | iteration_scientist_*.json |

---

## Co-authored-by

- Mavis <mavis@MiniMax>
