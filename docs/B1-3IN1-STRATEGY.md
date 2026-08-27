# B1 战法 3合1 (Multi-Asset Combined) — Strategy Doc

> **版本**: 2026-08-27 v1  
> **Repo**: https://github.com/yip-lgtm/YW-concept-ki7409

## 1 句话总结

**B1 战法 3合1 = MNQ + MGC + BTC 联合扫描 — 3 个 ticker 任何 1 个 trigger B1 条件，pick 最强嘅 signal 入场。**

---

## 与 B1 (单 ticker) 嘅分别

| | B1 单 ticker | B1 3合1 |
|--|--|--|
| **扫描** | 1 个 ticker (e.g. MNQ=F) | 3 个 ticker (MNQ+MGC+BTC) |
| **Signal** | 该 ticker fire → 1 个 signal | 任何 ticker fire → 1 个 strongest signal |
| **Sample size** | 30d 1-3 signals/ticker | 30d ~41 signals 整体 |
| **Multi-ticker 同步** | 唔会处理 | ✅ 同步 fire 嗰陣 pick best strength |
| **Correlation bonus** | 无 | ✅ 3 ticker 同步 trending 验证更稳 |
| **PF (30d test)** | 0.87 (per ticker) | 0.87 (combined) |

---

## 核心规则

| 字段 | 值 |
|------|---|
| **Ticker set** | MNQ=F, MGC=F, BTC-USD |
| **j_threshold** | -5 (放松 from -20) |
| **use_volume_filter** | False (5 conditions, skip vol) |
| **Pick rule** | `max(strength, -j)` 跨 ticker |
| **Hold** | 5d |
| **Stop** | signal-day low |
| **R-multiples** | [1, 1.618, 2.618, 3.618, 5] |
| **Weight** | 1.0 (init) |

---

## 30d Backtest 结果 (2026-07-28 → 2026-08-27)

| Ticker | N | W-L | WR | AvgR | Total | Stops |
|--------|---|-----|-----|------|-------|-------|
| BTC-USD | 16 | 6-10 | 37.5% | +0.00% | +0.03% | 6/10 |
| MGC=F | 16 | 9-7 | 56.2% | +0.04% | +0.64% | 6/10 |
| MNQ=F | 9 | 1-8 | 11.1% | -0.11% | -0.96% | 5/4 |
| **TOTAL** | **41** | **16-25** | **39.0%** | **-0.01%** | **-0.30%** | **17/24** |

PF 0.87 (slight loss). WR 39% (low). MGC best, MNQ worst.

**Multi-ticker concurrent signals**: 0 / 41 (tickers rarely signal same bar)

---

## Trade Examples

### Best 5
- 2026-07-26 MGC=F +0.38% (hold_exit, 5d)
- 2026-08-04 MGC=F +0.25% (hold_exit, 5d)
- 2026-08-05 MGC=F +0.19% (hold_exit, 5d)
- 2026-08-02 BTC-USD +0.07% (hold_exit, 5d)
- 2026-08-13 MGC=F +0.06% (hold_exit, 5d)

### Worst 5
- 2026-08-07 MNQ=F -0.41% (stop_loss)
- 2026-08-03 BTC-USD -0.28% (stop_loss)
- 2026-08-06 MNQ=F -0.20% (stop_loss)
- 2026-07-26 MNQ=F -0.14% (stop_loss)
- 2026-08-02 BTC-USD -0.11% (stop_loss)

---

## Implementation

### detector: `automation/src/yw_indicators_b1_3in1.py`

```python
from yw_indicators_b1_3in1 import detect_b1_3in1

result = detect_b1_3in1(j_threshold=-5, use_volume_filter=False)
# → {
#   'present': True/False,
#   'count': int (how many tickers signaled),
#   'best': {ticker, direction, j, strength, signal_low, ...},
#   'all_signals': list of all signals
# }
```

### Integration

| File | Change |
|------|--------|
| `automation/src/yw_indicators_b1_3in1.py` | NEW — 3合1 detector |
| `automation/src/yw_grader.py` | Added `STRATEGIES["B1-3in1"]` config |
| `automation/scripts/strategy_ranking.py` | Added `b1-3in1` to STRATEGIES list |

---

## Recommendations

**Option A**: Keep weight 1.0, observe next 30d
- B1 3合1 is the "best" B1 variant for crypto (most signals)
- 30d sample is small; may improve with more data
- MGC=F is the winner (56% WR, +0.64%) — could increase its weight

**Option B**: Increase MGC=F weight (since it's the winner)
- Current: MNQ=0.4, MGC=0.3, BTC=0.3
- Proposed: MNQ=0.2, MGC=0.5, BTC=0.3 (MGC gets bigger share)

**Option C**: Keep single-ticker B1 + 3合1 both running
- B1 single: high-purity signals
- B1 3合1: more frequent signals
- Combined: best of both worlds

---

## 何时 iterate

- 90+ trades 后，WR 明显稳定 (or 仍 < 50%)
- 5d backtest 嘅 PF < 0.9 (考虑 adjust j_threshold to -10 进一步放松)
- MGC 持续优势 → 考虑独立 MNQ 的 weight

---

## Source Files

- detector: `automation/src/yw_indicators_b1_3in1.py`
- single B1: `automation/src/yw_indicators_b1.py`
- yw_grader config: `automation/src/yw_grader.py` (B1-3in1 entry)
- 30d backtest: `automation/reports/strategy_ranking/b1_3in1_30d.json`
- 60d single B1: `automation/reports/strategy_ranking/b1_backtest_60d.json`
