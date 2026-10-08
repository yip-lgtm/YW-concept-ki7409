# 19. TTrades L13 — 交易 Candle 3

來源：第三方筆記整理 TTrades 免費課程 L13，非原文複製、非官網  
https://notes.powerofdeal.com/courses/ttrades-fractal-model/lesson-13/  
關聯：[17-TTrades-Model.md](17-TTrades-Model.md)、[18-TTrades-L12.md](18-TTrades-L12.md)  
更新：2026-10-09

L13 講 Candle 3 怎麼進，不再定義 C2。整套只交易擴張蠟燭。

## 1. 影線決定做 C2 還是 C3

只做擴張燭：影線小、開盤後單邊走。長影線代表開盤與收盤接近、雙向拉扯，不支持即時擴張。

| C2 形態 | 做法 |
|---------|------|
| 小影線反轉 | 可在 C2 內配低周期 CISD 直接做 |
| 長影線，或大區間對向走完再收回 | 等收盤確認 C2 closure，C3 開盤後做延續 |
| C2 本身已是擴張（淺影線後直接拉開） | 不做後面的 C3，容易掉進新階段的回調或整固 |

## 2. C3 進場：continuation order block

1. C3 開盤後，先掃短線高／低，或進入 POI（例如 FVG）。
2. 出現一根對向蠟燭，確認高時間框影線已經成形。這個位置就是 continuation order block。
3. 價格再轉回原方向時進場。
4. 停損放在 protected swing 外。
5. 目標至少 2R，或 projection／流動性。

EURUSD 例子（筆記）：日線週二是反轉（跌的擴張碰上漲的擴張）。週三是 C3，降到小時圖，等收盤跌破造就低點的連續下跌蠟燭（CISD），收破後在新蠟燭開盤做多，停損在 protected low，目標 2R。

## 3. Bias 決定進取程度

- 高時間框延續日加強 bias：低周期可以做反轉（HTF continuation 配 LTF reversal）。日線強烈看空時，5 分鐘 V 形反轉加 SMT 加 CISD 就可以空。停損用低周期 swing，因為目標近，停損放在日線高點拿不到 2R。講者預期 CISD 的 0.5 會守住。這條沒有客觀量尺，快市容易被掃。
- Bias 一般：等低周期也形成 continuation order block 先入。勝率較高，盈虧比較差。
- 高時間框本身是反轉日（在做 C2）：更要等低周期延續確認，因為高時間框偏向未確認。

4 小時配 15 分鐘：整固時不要急。等淺回調、protected swing 形成、再收破連續下跌蠟燭，回測時進場。目標是區間高點或 2R。

## 4. 降級與避雷

- C2 有少少擴張，但短線流動性未掃（目標還在）：C3 仍可做。C2 已經掃到目標：不追。
- C3 不大跌、只在區間慢速整固：可看成 C4 延續的前奏。若要反轉，應該快收破；遲遲不破，仍是整固。
- 賣方流動性同 CISD 幾乎同一價：CISD 成立時目標已被掃掉。three drives 例子，講者明講通常不做。
- 小影線蠟燭用整根區間的 0.5 判斷回調深淺，不用影線的 0.5。用影線 0.5 會把回調看成太淺。

## 5. C2／C3／C4 串接例子

月線掃前高後 V 形反轉，CISD 且持續尊重該位。回調時出現 C3 closure（強勢收破 C2 極值），於是 C4 偏向向下，目標是下方 sellside。小時圖 projection 同該流動性重合。再配高時間框 order block 同 EQ，價格回測高時間框 FVG 時，在 15 分鐘找 model。三次延續機會，兩次成功。講者偏好第一次延續，後面像追價。

## 6. 同現有 pipeline 的缺口

H4 C2 收盤就開，對不上 L13。開倉應是 C3 開盤後的 continuation order block：先掃短線流動性或入 POI，再有對向燭確認影線，然後先轉回方向。停損在 protected swing 外，目標 2R 或 projection，不是固定 1.6×ATR。
