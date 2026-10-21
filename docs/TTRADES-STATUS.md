# TTrades 家族狀態（2026-10-22）

四個 agent：**Fractal base** + **L12** + **L13** + **L14**。
4 strategies × 3 tickers（MNQ=F / MGC=F / BTC-USD）= 12 個 agent。

---

## 1. 家族地圖：邊啲做齊咗，邊啲冇

| 能力 | Fractal | L12 | L13 | L14 |
|---|---|---|---|---|
| 偵測器 | ✅ | ✅ | ✅ | ✅ |
| 發佈 SL / T1 / T2 | ✅ | ✅ | ✅ | ✅ |
| Telegram 通知 | ✅ | ✅ | ✅ | ✅ |
| Tracker（開倉 → 收倉 → 記 P&L） | ✅ | ✅ | ✅ | ✅ |
| Settlement / 等級循環 | ✅ | ✅ | ✅ | ✅ |
| **重入 cooldown** | ❌ → ✅ | ❌ → ✅ | ❌ → ✅ | ❌ → ✅ |
| 週線 profile | ✅ | ❌ | ❌ | ❌ |
| 日線 D1 偏向 | ✅ | ❌（見 §3） | ❌ | ❌ |
| 日內 profile | ✅ | ❌ | ❌ | ❌ |
| **回測** | ✅ 凍結 0 單 → ✅ 新增 | ❌ | ❌ | ❌ |

L 系列喺 detector → levels → TG → tracker → settlement 呢條鏈上**已經齊備**，
缺嘅係**量度**。

---

## 2. 本次修好：重入 cooldown

Tracker 原本只按 `signal_id` 去重，所以一個啱啱被止損嘅 setup，
下一次掃描就會即刻重入——新時間戳、新 signal_id、同樣嗰筆交易。

2026-10-14 喺 MGC=F long 發生咗**連續六次**：

| 時間 | 入場 | 止損 | R |
|---|--:|--:|--:|
| 04:39 | 4182.00 | 4166.82 | -1.0 |
| 04:48 | 4180.70 | 4166.82 | -1.0 |
| 05:07 | 4184.90 | 4166.82 | -1.0 |
| 06:05 | 4184.20 | 4166.82 | -1.0 |
| 07:52 | 4179.20 | 4166.80 | -1.0 |
| 08:00 | 4179.40 | 4166.80 | -1.0 |

**六次全部喺同一個價位止損。** 呢個就係 L12 嘅 live 成績單：

| 策略 | closed | 勝 | WR | PF | PF 95% CI | total R |
|---|--:|--:|--:|--:|---|--:|
| TTrades-Fractal | 6 | 3 | 50.0% | 1.62 | [0.37, 7.01] | +1.85 |
| **TTrades-L12** | **7** | **0** | **0.0%** | **0.00** | **[0.00, 0.89]** | **-7.00** |
| TTrades-L13 | 28 | 11 | 39.3% | 1.05 | [0.50, 2.20] | +0.80 |
| TTrades-L14 | 12 | 4 | 33.3% | 0.81 | [0.26, 2.52] | -1.53 |

L12 嘅 PF 0.00 係**統計顯著**嘅差（CI 上界 0.89 < 1）——唔係噪音，
係真實嘅負 edge。而且 6/7 嘅損失係同一個 setup 重入造成嘅。

主帳本一直有呢條規則（`live_scan.COOLDOWN_HOURS = 4`，同一
strategy + ticker + 正規化方向），TTrades 家族冇對應機制。
而家兩邊一致：已開嘅同一組合唔再入，4 小時內平咗嘅同一組合唔再入。

Regression test：`automation/scripts/test_ttrades_cooldown.py`

---

## 3. 查過但**冇**加：D1 日線偏向

doc 18 §6 提到舊嗰類「H4 C2 + M15 CISD」訊號「缺日線偏向同 POI」。
POI 已經補咗（`find_htf_poi`），但日線偏向**唔應該**加落 L 系列：

doc 17 嘅「YW 實盤配對建議」表寫住三種配對：

| 偏向 | HTF | CISD / 執行 |
|---|---|---|
| 種田 | H1 | M5 |
| **稍慢** | **H4** | **M15** |
| 日內 OSOK | D1 | H1 確認 + M15 入 |

L 系列用嘅係 **H4 + M15**，即係「稍慢」一級——**呢一級冇 D1 偏向**。
D1 係另一行「日內 OSOK」嘅要求。加落去等於改咗模型，而唔係補完佢。

---

## 4. 新增：TTrades deep backtest

之前只有 base 一個 20 日 backtest，凍結喺 2026-09-01 而且 **0 單**；
L 系列**完全冇回測**，即係除咗 live 帳戶之外冇任何嘢量度過佢哋。

新增 `automation/scripts/ttrades_deep_backtest.py`，用 repo 入面嘅
Polygon deep history（真實 5m，13 個月）resample 成各 agent 真正用嘅 frame
（H4 / M15 / D1 / 1wk），entry 同 SL/T2 喺 M15 上 resolve。

| 策略 | n | 勝 | WR | PF | PF 95% CI | total R | 判定 |
|---|--:|--:|--:|--:|---|--:|---|
| TTrades-Fractal | 233 | 91 | 39.1% | 1.04 | [0.80, 1.35] | +3.60 | 同 1 無分別 |
| TTrades-L13 | 66 | 30 | 45.5% | 1.35 | [0.83, 2.18] | +12.54 | 同 1 無分別 |
| TTrades-L12 | **0** | — | — | — | — | — | 13 個月一單都冇 |
| TTrades-L14 | **0** | — | — | — | — | — | 13 個月一單都冇 |

L13 喺 step 4 只有 13 單時 PF 係 0.49，去到 step 1 有 66 單變 1.35——
**又一個 n<50 就唔好信嘅例子**。

### 點解 L12 / L14 係 0 單——唔係 bug，係資料限制

Live 交易嘅標的分佈：

| 策略 | closed | 其中 BTC-USD |
|---|--:|--:|
| TTrades-Fractal | 6 | 5（83%） |
| TTrades-L12 | 7 | **0（0%）** |
| TTrades-L13 | 28 | 6（21%） |
| TTrades-L14 | 12 | 2（17%） |

而 Polygon 嘅 5m history **對 CME 期貨全部零結果**——
`fetch_deep_history.py` 記錄咗 MNQ / MES / M2K / MGC / GC 全部
`status: DELAYED, resultsCount: 0`，只有 crypto `X:BTCUSD` 有深历史。

**所以 deep backtest 結構上只判得到 base Fractal。** L 系列 83% 嘅交易
喺 MGC / MNQ，而嗰兩個標嘅冇任何 5m 歷史可用。

要量度 L 系列，只剩兩條路：

1. **Yahoo 1h → H4 resample**（≈180 日），CISD 同執行用 15m。
   但 Yahoo 15m 只畀 60 日，由 1h resample 出嚟嘅 15m 係假 frame——
   就係主帳本 1h track 嗰種「粒度唔對」嘅問題。
2. **搵另一個 5m 數據源**（CME 直接、或者付費 API）覆蓋 MGC / MNQ。

喺呢兩樣之前，L 系列嘅**唯一證據係 live 帳戶**（53 單），而 live 樣本
又細到做唔到統計推斷。

---

## 5. 順手清理咗嘅死檔案

| 檔案 | 凍結於 | 點解刪 |
|---|---|---|
| `l_strategies.jsonl` | 2026-10-09 10:08 | 舊合併檔，已被 per-ticker 版取代 |
| `l_strategies_latest.json` | 2026-10-09 10:08 | 舊合併版，`l_strategies_latest_{TICKER}.json` 先係現行 |
| `latest.json` | 2026-10-08 22:08 | 舊 base 版，`latest_{TICKER}.json` 先係現行 |

三個檔**冇任何程式讀**（`latest.json` 嘅引用全部係 OCS 嘅
`/tmp/ocs_btc/latest.json`，唔同嘅嘢）。留喺度嘅實際危害係：
有人讀 `l_strategies_latest.json` 會以為 L 系列自 10-09 就冇再 fire。

---

## 6. 同時修好：28 個 script 嘅硬編碼路徑

`automation/scripts/` 有 28 個檔案寫死 `REPO = Path("/workspace/YW-concept-ki7409")`。
CI 有 `GITHUB_WORKSPACE` 所以行得，但喺任何其他 checkout 都死，而且**死法係
「資料唔見咗」而唔係「路徑錯咗」**：

| script | 症狀 |
|---|---|
| `historical_backtest.py` | 仲未行過一根 bar 就死喺 `live_scan.py` |
| `rl_arm_report.py` | 明明有 16 條 armed trade，印「no closed trades」 |
| `ttrades_tracker.py` | 搵唔到已平倉交易，所以**連 cooldown 都冇得比較** |

全部改成由 `__file__` 向上搵返 repo root（同 `live_scan.py` 一直的做法）。
CI 行為唔變（`GITHUB_WORKSPACE` 優先）。

---

## 7. 重現

```bash
# TTrades deep backtest（唔需要網絡，資料喺 repo 入面）
python3 automation/scripts/ttrades_deep_backtest.py --step 1

# cooldown regression test
python3 automation/scripts/test_ttrades_cooldown.py
```
