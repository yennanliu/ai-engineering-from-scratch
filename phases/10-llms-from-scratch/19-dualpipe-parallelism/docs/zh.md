# DualPipe 平行化

> DeepSeek-V3 是在 2,048 張 H800 GPU 上訓練的，MoE 專家散落在各節點之間。跨節點的專家 all-to-all 通訊，每 1 GPU-小時的計算就要配上 1 GPU-小時的通訊。GPU 有一半時間閒著。DualPipe（DeepSeek，2024 年 12 月）是一種雙向管線，把前向與反向計算，跟它們觸發的 all-to-all 通訊重疊起來。氣泡下降、吞吐量攀升，而多留一份模型參數副本（名字裡那個「dual」的由來）其實很便宜 —— 反正專家並行早就把專家攤薄到各個 rank 上了。這個單元是學習型的導覽，講清楚 DualPipe 實際上做了什麼，以及 Sea AI Lab 的 DualPipeV 改良版為什麼願意用略大一點的氣泡，換掉那 2 倍的參數成本。

**類型：** 學習
**程式語言：** Python (stdlib, schedule simulator)
**先修單元：** 階段 10 · 05（分散式訓練、FSDP、DeepSpeed）、階段 10 · 14（開源模型架構與 MoE）
**時間：** 約 60 分鐘

## 學習目標

- 說出 DualPipe 一個前向-反向 chunk 的四個組成部分，以及每一個為什麼各自需要一個重疊視窗。
- 解釋規模化之下的管線氣泡問題，以及「無氣泡」在實務上與在行銷話術上分別是什麼意思。
- 手動追一遍 8 個 PP rank、16 個微批次的 DualPipe 排程，確認正向與反向兩條流各自填滿了對方的閒置時段。
- 說明 DualPipeV（Sea AI Lab，2025）做的取捨：捨棄 2 倍參數複製，代價是在專家並行沒有啟用時氣泡稍微大一些。

## 問題所在

在 2 千張 H800 GPU 上訓練一個 6710 億參數的 MoE 模型，會撞上三個互相疊加的瓶頸：

1. **記憶體壓力。** 每張 GPU 只持有模型的一片。序列長度 8k、61 層、128 個頭之下的啟動值記憶體大得驚人。
2. **管線氣泡。** 傳統的管線平行（GPipe、1F1B）會讓 GPU 閒著等自己這一階段的輸入或梯度。在 8 個階段時，就算用 1F1B 排程，也大約有 12% 的 GPU 時間是氣泡。
3. **跨節點 all-to-all。** 搭配專家並行的 MoE 會把專家散到各節點上。每一次前向傳播都要觸發一次 all-to-all 把詞元分派給它們的專家，再觸發一次把結果合併回來。在 2 千張 GPU 的規模下，這輕易就變成 1:1 的計算對通訊比。

這三者各自有各自的解法：記憶體用梯度檢查點、管線氣泡用 Zero Bubble（Sea AI Lab，2023）、all-to-all 用專家並行的通訊 kernel。DualPipe 做的事，是讓它們一起運作。這套排程在單一個前向-反向 chunk 之內就把計算與通訊重疊起來，同時從管線的兩端注入微批次，再利用產生出來的排程把 all-to-all 藏進計算視窗裡。

論文回報的結果：管線氣泡幾乎被消除，DeepSeek-V3 那次 14.8T 詞元的訓練跑出超過 95% 的 GPU 使用率。

## 核心概念

### 管線平行複習

把一個 N 層的模型切給 P 台裝置。裝置 `i` 持有第 `i * N/P .. (i+1) * N/P - 1` 層。一個微批次從裝置 0 一路前向流到裝置 P-1，再從 P-1 反向流回 0。每台裝置只有在前一台送來輸出時才能開始自己的前向階段，也只有在下游裝置送來上游梯度時才能開始反向。

GPipe（Huang et al., 2019）一次只排一個微批次，浪費掉大半的 GPU 時間。1F1B（Narayanan et al., 2021）把多個微批次的前向與反向交錯排程。Zero Bubble（Qi et al., 2023）把反向傳遞拆成兩塊 —— 對輸入的反向（B）與對權重的反向（W）—— 再排程它們去填氣泡。有了 Zero Bubble 之後，管線已經幾乎塞滿了。

DualPipe 是下一步。它在上面再疊兩個想法：

### 想法 1：chunk 分解

每一個前向 chunk 被切成四個組成部分：

- **注意力。** Q/K/V 投影、注意力、輸出投影。
- **All-to-all dispatch。** 把詞元送給它們的專家的跨節點通訊。
- **MLP。** MoE 專家的計算。
- **All-to-all combine。** 把專家輸出帶回來的跨節點通訊。

一個反向 chunk 再加上這四者各自的梯度版本。DualPipe 這樣排程它們：all-to-all dispatch 與下一個 chunk 的注意力計算平行進行，all-to-all combine 與再下一個 chunk 的 MLP 計算平行進行。

### 想法 2：雙向排程

多數管線排程都從第 0 階段注入微批次，往第 P-1 階段流。DualPipe 從**兩端**同時注入。第 0 階段看得到從它這裡出發的前向微批次；第 P-1 階段也看得到從它那裡出發的前向微批次。兩條流在中間交會。

要讓這件事成立，裝置 `i` 必須同時持有管線前段的第 `i` 層**和**管線後段的第 `P - 1 - i` 層。這就是 DualPipe 裡「dual」的部分：每台裝置為自己要服務的模型層各留兩份副本（一個方向一份）。在 DeepSeek-V3 的規模下，這是 2 倍的參數複製成本。之所以負擔得起，是因為專家並行早就把 MoE 專家攤得夠薄了，把非專家的那些層複製兩份根本是小錢。

關鍵在於：一個方向的前向流與另一個方向的反向流，剛好重疊在單向排程會出現氣泡的位置。氣泡就此消失。

### 手動追一遍排程

考慮 P = 4 個 rank、8 個微批次，分成 4 個正向 / 4 個反向。時間由左往右走；每一列是一個裝置 rank。

```
           Time →
rank 0:  F1 F2 F3 F4  F5R F6R F7R F8R  B1 B2 B3 B4  ...
rank 1:     F1 F2 F3  F4/F5R F6R F7R   B1 B2 ...
rank 2:        F1 F2  F3/F5R F4/F6R    B1 ...
rank 3:           F1  F2/F5R F3/F6R    ...
```

讀懂「F4/F5R」這個記法：rank 1 在同一個時段裡同時跑微批次 4 的前向（在管線裡由左往右走）**和**微批次 5 的前向（由右往左走）。這就是「雙向」在運作層面的意思。

在 rank 2，兩條交叉的流比較早重疊；在 rank 0 與 P-1 則最晚重疊。在排程的穩定中段，每個 rank 都在跑「某方向的前向」疊上「另一方向的反向」。計算是滿的。前向傳播的 all-to-all dispatch 藏在反向計算裡。All-to-all combine 藏在前向計算裡。氣泡被擠光了。

### 氣泡帳目

標準 1F1B 的管線氣泡（每個 rank 浪費的時間）：

```
bubble_1F1B = (P - 1) * forward_chunk_time
```

Zero Bubble 的改良把它壓下來，但沒有壓到零。DualPipe 在穩定階段裡，只要微批次數量能被 2 倍管線深度整除，氣泡就是零。在穩定階段之外（暖機與收尾），還是有一些氣泡，但它不會隨微批次數量成長 —— 這是論文特別強調的關鍵性質。

用行銷的講法：「無氣泡」。用技術的講法：氣泡不隨微批次數量成長。Sea AI Lab 的後續分析（DualPipeV / Cut-in-half）指出，只有在專家並行不是瓶頸時才看得到完整的零氣泡；一旦有 EP 驅動的 all-to-all，排程上就一定得有所妥協。

### DualPipeV —— 改良版

Sea AI Lab（2025）注意到，當 EP 通訊重疊不是重點時，那 2 倍的參數複製是浪費。他們的 DualPipeV 排程把雙向注入折成一種「V 型」排程，只用一份參數副本就能跑。氣泡比 DualPipe 稍大，但省下的記憶體很可觀。DeepSeek 在自己開源的 DualPipe 實作裡採用了 DualPipeV，當作 EP 關閉時的模式。

取捨如下：

| 特性 | DualPipe | DualPipeV | 1F1B | Zero Bubble |
|---------|---------|-----------|------|------------|
| 每台裝置的參數副本數 | 2 | 1 | 1 | 1 |
| 氣泡 vs 微批次數 | 固定 | 微幅成長 | 成長 | 成長 |
| 計算-通訊重疊 | 完整 | 部分 | 極少 | 部分 |
| 何時使用 | EP 吃重的 MoE | 密集模型或 EP 輕量 | 基準線 | 任何管線 |

### 這對一次 14.8T 詞元的訓練意味著什麼

DeepSeek-V3 的預訓練在 2,048 張 H800 GPU 上吃掉 14.8T 詞元，大約 280 萬 GPU-小時。用天真的 1F1B，他們會有 12-15% 的算力賠給管線氣泡 —— 也就是 34 萬到 42 萬 GPU-小時，足夠訓練一個完整的 700 億參數模型。DualPipe 把其中大部分救了回來。沒有內部紀錄的話很難直接量化它的貢獻，但論文的說法是整個訓練平均下來超過 95% 的 GPU 使用率。

對比較小的訓練（1 千張 GPU 以下），DualPipe 是殺雞用牛刀 —— 管線氣泡相對於總成本比較小，而密集模型的訓練也很少撞上 all-to-all 瓶頸。但對數千張 GPU 規模的前沿 MoE 訓練來說，它實質上是必需品。

### 它在整個技術堆疊裡的位置

- 與 **FSDP**（階段 10 · 05）互補。FSDP 把模型參數分片到各 rank 上；DualPipe 把計算排程到各 rank 上。兩者可以合用。
- 與 **ZeRO-3** 的梯度分片相容。兩份副本複製的帳務處理，必須和 ZeRO 分片後的梯度配合好。
- 需要針對特定叢集拓撲調校過的**自訂 all-to-all kernel**。DeepSeek 開源的 kernel 就是參考實作。

```figure
expert-capacity
```

## 框架應用

`code/main.py` 是一個管線排程模擬器。它吃 `(P, n_micro_batches, schedule)`，然後印出 1F1B、Zero Bubble、DualPipe 與 DualPipeV 各自在穩定階段的使用率。它是教學工具 —— 這些數字符合論文裡的定性說法，但不代表任何生產環境實測到的加速比。

這個模擬器的價值：拿不同的 P 與微批次數量去跑，看氣泡比例在 1F1B 上怎麼往上長，而在 DualPipe 上不會。

真實訓練要整合時的考量：

- 挑一個能整除你微批次數量的管線平行深度。
- 確認你的專家並行 mesh 支援雙向 all-to-all。DeepSeek 的 kernel 是參考標準。
- 第一次做的話，預期要在排程本身上燒掉一週的除錯時間。這些帳務細節很煩。
- 監控每個 rank 的 GPU 使用率，不要只看整體。DualPipe 的好處來自把落後者收緊。

## 產出交付

這個單元會產出 `outputs/skill-dualpipe-planner.md`。給定一份訓練叢集規格（GPU 數量、拓撲、互連、模型形狀），它會建議一套管線平行策略、該用的排程演算法，以及在目標規模下預期的氣泡比例。

## 練習

1. 用 `(P=8, micro_batches=16, schedule=dualpipe)` 與 `(P=8, micro_batches=16, schedule=1f1b)` 跑 `code/main.py`。算出 GPU 使用率的差異，並換算成每訓練一百萬詞元救回多少 GPU-小時。

2. 手繪 `(P=4, micro_batches=8, schedule=dualpipe)` 的排程表。在每個時段標上微批次編號與方向。找出第一個沒有氣泡的時段。

3. 讀 DeepSeek-V3 技術報告（arXiv:2412.19437）的圖 5。找出 DualPipe 前向 chunk 裡 all-to-all dispatch 的重疊視窗。解釋計算排程是怎麼把它藏起來的。

4. 算出 DualPipe 對一個 P=8 管線階段的 700 億參數密集模型、以及一個 P=16 管線階段的 6710 億參數 MoE 模型各自的 2 倍參數額外開銷。說明為什麼 MoE 那一邊的開銷按比例來說比較小（絕大多數參數是專家，被分片到一個很大的 EP 群組上）。

5. 把 DualPipe 拿來跟 Chimera（2021 年一個競爭的雙向排程器）比較。以論文第 3.4 節為依據，指出 DualPipe 多了哪兩項 Chimera 沒有的具體性質。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| 管線氣泡 | 「每個 rank 的閒置時間」 | 因為某個管線階段在等輸入或梯度而浪費掉的 GPU 週期 |
| 1F1B | 「預設的管線排程」 | 一次前向／一次反向交錯的排程；DualPipe 要打敗的基準線 |
| Zero Bubble | 「Sea AI Lab 2023」 | 把反向拆成 B（輸入梯度）與 W（權重梯度）；幾乎把管線完全塞滿 |
| DualPipe | 「DeepSeek-V3 的排程」 | 雙向管線 + 計算-通訊重疊；氣泡不隨微批次數量成長 |
| DualPipeV | 「Cut-in-half」 | V 型的改良版，捨棄 2 倍參數複製，代價是氣泡稍大 |
| Chunk | 「管線工作的單位」 | 一個微批次通過一個管線階段的一次前向或反向傳遞 |
| All-to-all dispatch | 「把詞元送給專家」 | 把詞元路由到它們被指派的 MoE 專家的跨節點通訊 |
| All-to-all combine | 「把專家輸出帶回來」 | MLP 之後收集專家輸出的跨節點通訊 |
| 專家並行（EP） | 「專家散在各 GPU 上」 | 把 MoE 專家分片到各 rank 上，讓不同 GPU 持有不同專家 |
| 管線平行（PP） | 「層散在各 GPU 上」 | 把模型層分片到各 rank 上；DualPipe 排程的就是這個維度 |
| 氣泡比例 | 「浪費掉的 GPU 時間」 | （bubble_time / total_time）；DualPipe 要把它推向零的那個比例 |

## 延伸閱讀

- [DeepSeek-AI — DeepSeek-V3 Technical Report (arXiv:2412.19437), Section 3.3.2 and Figure 5](https://arxiv.org/abs/2412.19437) —— DualPipe 的主要參考文獻
- [DeepSeek — DualPipe GitHub repository](https://github.com/deepseek-ai/DualPipe) —— 開源的參考實作，含 DualPipeV（Cut-in-half）模式
- [Qi et al. — Zero Bubble Pipeline Parallelism (arXiv:2401.10241, Sea AI Lab 2023)](https://arxiv.org/abs/2401.10241) —— Zero Bubble 這個前身
- [Sea AI Lab — DualPipe could be better without the Dual](https://sail.sea.com/blog/articles/63) —— 促成 DeepSeek EP 關閉模式的 DualPipeV 分析
- [Narayanan et al. — PipeDream / 1F1B (arXiv:1806.03377, 2018-2021)](https://arxiv.org/abs/1806.03377) —— DualPipe 拿來對照的 1F1B 排程
- [Huang et al. — GPipe (arXiv:1811.06965, 2018)](https://arxiv.org/abs/1811.06965) —— 管線平行與氣泡問題的原始論文
