# Flamingo 與少樣本 VLM 的帶閘門交叉注意力

> DeepMind 的 Flamingo（2022）做到了兩件別人還沒做到的事。它證明了單一模型可以處理任意交錯的影像、影片與文字序列。它也證明了 VLM 能在脈絡中學習 —— 給一段帶三組 (影像, 字幕) 範例的少樣本提示詞，模型就能替一張新影像寫字幕，完全不用做任何梯度更新。機制是：帶閘門的交叉注意力層，插進凍結 LLM 既有的層與層之間，搭配一個從零開始的可學習 tanh 閘門，讓 LLM 的文字能力在初始化時原封不動。這一課會走一遍 Flamingo 的 Perceiver resampler 與帶閘門交叉注意力架構 —— 它是 Gemini 交錯輸入與 Idefics2 視覺詞元的祖先。

**類型：** 學習
**程式語言：** Python (stdlib, gated cross-attention + Perceiver resampler demo)
**先修單元：** 階段 12 · 03（BLIP-2 Q-Former）
**時間：** 約 120 分鐘

## 學習目標

- 說明帶閘門的交叉注意力如何透過 tanh(gate) = 0，在初始化時保住凍結 LLM 的文字能力。
- 走一遍 Perceiver resampler：N 個影像 patch → 經交叉注意力變成 K 個固定的「latent」query。
- 描述 Flamingo 如何用尊重影像位置的因果遮罩，處理交錯的影像—文字序列。
- 重現一段少樣本多模態提示詞的結構（3 組影像—字幕範例，接著一張查詢影像）。

## 問題所在

BLIP-2 把 32 個視覺詞元餵進凍結 LLM 的輸入層。一段提示詞配一張影像時很好用。但如果你想餵*很多*張與文字交錯的影像呢？像是「這是影像 A，寫個字幕；這是影像 B，寫個字幕；那麼這是影像 C，寫個字幕」。LLM 的自注意力就得在單一串流裡同時處理影像詞元與文字詞元，而「哪些位置可以關注哪些影像」這個問題會變得很麻煩。

Flamingo 的答案是：完全不去動 LLM 的輸入串流。改成在既有的 LLM 區塊之間，插入額外的交叉注意力層。文字詞元一如既往地流過 LLM 的因果自注意力。每隔幾個 LLM 區塊，文字詞元會再透過一個新的帶閘門層，去交叉關注影像特徵。那個閘門（初始化為零）意味著在第 0 步時這些新層形同無作用 —— 模型的行為和預訓練好的 LLM 一模一樣。隨著訓練推進，閘門打開，視覺資訊才開始流動。

Flamingo 回答的第二個問題是：每段提示詞的影像數量不定（0 張、1 張或很多張）時要怎麼處理？靠一個 Perceiver resampler —— 一個小型的交叉注意力模組，不管你手上有多少 patch，都產出固定數量的視覺 latent 詞元。無論提示詞裡有幾張影像，LLM 的交叉注意力層看到的形狀都一樣。

## 核心概念

### 凍結的 LLM

Flamingo 以一個凍結的 Chinchilla 70B LLM 為起點。全部 700 億權重都沒動過。既有的文字自注意力與 FFN 照常運作。

### Perceiver resampler

提示詞裡的每一張影像，ViT 都會產出 N 個 patch 詞元。Perceiver resampler 有 K 個固定的可學習 latent（Flamingo 用 K=64）。每個 resampler 區塊分兩個子步驟：

1. 交叉注意力：K 個 latent 去關注那 N 個 patch 詞元（Q 來自 latent，K/V 來自 patch）。
2. latent 之間的自注意力 + FFN。

跑完 6 個 resampler 區塊後，輸出是 K=64 個維度 1024 的視覺詞元，與 ViT 產出多少 patch 無關。一張 224x224 的影像（196 個 patch）和一張 480x480 的影像（900 個 patch），出來的都是 64 個 resampler 詞元。

對影片，resampler 是沿時間軸套用的：每個畫格的 patch 產出 64 個 latent，再用一個時間位置編碼讓模型能分辨 t=0 與 t=N。整段影片就變成 T * 64 個視覺詞元。

### 帶閘門的交叉注意力

在凍結 LLM 每隔 M 層的地方（Flamingo 用 M=4），插入一個新的帶閘門交叉注意力區塊：

```
x_after_llm_block = llm_block(x_before)
cross = cross_attn(x_after, resampler_output)
gated = tanh(alpha) * cross + x_after
x_before_next_block = gated
```

- `alpha` 是一個可學習的純量，初始化為零。
- `tanh(0) = 0`，所以初始化時帶閘門的那條分支貢獻為零。
- 隨著 `alpha` 離開零，交叉注意力的貢獻會平滑地成長。
- 那條殘差連接意味著，就算閘門全開也不會覆寫 LLM 的文字表徵；它只是在上面疊加視覺資訊。

這是 Flamingo 最重要的一項設計決策：視覺條件化是加法的、帶閘門的，而且在初始化時為零。第 0 步的 Flamingo，在純文字輸入上就是一個完美的 Chinchilla 70B。

### 給交錯輸入用的遮罩式交叉注意力

在「<image A> caption A <image B> caption B <image C> ?」這樣的提示詞裡，每個文字詞元只應該看到序列中排在它前面的影像。交叉注意力遮罩強制的規則是：位置 `t` 的文字詞元，只關注影像索引 `i < i_t` 的影像 resampler 詞元，其中 `i_t` 是位置 `t` 之前最近的那張影像。「只看到緊鄰在前的那一張影像」與「看到前面所有影像」都是合理的選擇；Flamingo 選了前者。

### 脈絡內的少樣本學習

一段 Flamingo 提示詞長這樣：

```
<image1> A photo of a cat. <image2> A photo of a dog. <image3> A photo of a
```

模型看出了這個補全模式，就輸出「bird」（或者 image3 裡是什麼就輸出什麼）。沒有梯度更新。凍結 LLM 的脈絡內學習能力，穿過了帶閘門的交叉注意力傳了下來 —— 這是論文的重點，也是它之所以重要的原因。

### 訓練資料

Flamingo 用三份資料集訓練：

1. MultiModal MassiveWeb（M3W）：4300 萬個影像與文字交錯的網頁，並還原閱讀順序。
2. 影像—文字配對（ALIGN + LTIP）：44 億組配對。
3. 影片—文字配對（VTP）：2700 萬段短影片。

OBELICS（2023）是這份交錯網頁語料的開放重現，Idefics、Idefics2 以及多數開放的「類 Flamingo」模型都用它訓練。

### OpenFlamingo 與 Otter

OpenFlamingo（2023）是開放的重現版。架構完全相同（Perceiver resampler + 在凍結的 LLaMA 或 MPT 上做帶閘門交叉注意力）。檢查點有 3B、4B、9B。由於基礎 LLM 較小、資料較少，品質落後於 Flamingo。

Otter（2023）在 OpenFlamingo 之上，用 MIMIC-IT（一份多模態指令資料集）做指令微調，顯示帶閘門的交叉注意力在指令跟隨上也行得通。

### 後裔們

- Idefics／Idefics2／Idefics3：Hugging Face 的帶閘門交叉注意力血脈，一代比一代更簡單（Idefics2 捨棄了 resampler，改用搭配自適應池化的直接 patch 詞元）。
- 從 Flamingo 到 Chameleon 的轉向：到了 2024 年，許多團隊轉向早期融合（見單元 12.11）；在必須凍結骨幹的場景，Flamingo 式的帶閘門交叉注意力仍在生產環境中存活。
- Gemini 的交錯輸入：在概念上繼承了 Flamingo 交錯格式的彈性，不過確切的機制並未公開。

### 與 BLIP-2 的比較

| | BLIP-2 | Flamingo |
|---|---|---|
| 視覺橋樑 | 在輸入端用一次 Q-Former | 每 M 層一個帶閘門交叉注意力 |
| 視覺詞元 | 每張影像 32 個 | 每張影像、每個交叉注意力層 64 個 |
| 凍結 LLM | 是 | 是 |
| 少樣本脈絡內學習 | 弱 | 強 —— 論文的核心賣點 |
| 交錯輸入 | 沒有原生支援 | 有，這就是設計目標 |
| 訓練資料 | 1.3 億組配對 | 13 億組配對 + 4300 萬個交錯網頁 |
| 參數量 | 訓練 1.88 億 | 訓練約 100 億（交叉注意力層） |
| 計算量 | 8 張 A100 跑幾天 | 數千張 TPUv4 跑幾週 |

預算有限、要做單影像 VQA，就選 BLIP-2。要做交錯、少樣本或多影像推理，就選 Flamingo／Idefics2。

## 框架應用

`code/main.py` 示範了：

1. 在 36 個假的 patch 詞元上，用 8 個可學習 latent 跑一個 Perceiver resampler（純 Python 的交叉注意力）。
2. 一次帶閘門的交叉注意力步驟：`alpha = 0` → 輸出等於輸入（LLM 不變），接著 `alpha = 2.0` → 視覺貢獻被混了進來。
3. 一個交錯遮罩產生器，為「(影像 1) (文字 1) (影像 2) (文字 2)」這樣的序列產出二維注意力遮罩。

## 產出交付

這一課產出 `outputs/skill-gated-bridge-diagnostic.md`。給定一個開放 VLM 的設定（有沒有 resampler、交叉注意力的頻率、閘門方案），它會指認出屬於 Flamingo 血脈的元素，並解釋其凍結策略。這在除錯「為什麼微調之後文字表現退步了」時很有用（答案：閘門開得太快太大了）。

## 練習

1. 算出 Flamingo-9B 的視覺參數量：9B 的 LLM + 14 億的帶閘門交叉注意力層 + 6400 萬的 resampler。有在訓練的參數佔總量的多少比例？

2. 用 PyTorch 實作帶閘門的殘差 `y = tanh(alpha) * cross + x`。用實驗證明在 `alpha=0` 時，初始化當下 `y==x` 完全成立。

3. 讀 OpenFlamingo 第 3.2 節（arXiv:2308.01390），看他們在同一批次中每段提示詞影像數量不同時怎麼處理。描述那個填補策略。

4. Flamingo 的交叉注意力遮罩，為什麼只讓文字詞元關注*緊鄰在前的那一張*影像，而不是前面所有影像？讀 Flamingo 論文第 2.4 節並說明其取捨。

5. 脈絡內少樣本：替一個新的 Flamingo 變體，建一段帶 4 個「影像 → 主要物件的顏色」範例的提示詞。描述當你把範例數從 0 變到 8 時，預期的準確率變化模式。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| Perceiver resampler | 「固定 latent 的交叉注意力」 | 一個模組，從數量不定的輸入 patch 產出 K 個固定詞元 |
| 帶閘門交叉注意力 | 「tanh 閘門橋」 | 殘差層 `y = tanh(alpha)*cross + x`，alpha 可學習，初值為 0 |
| 交錯輸入 | 「混合序列」 | 影像與文字依閱讀順序自由混排的提示詞格式 |
| 凍結 LLM | 「LLM 不吃梯度」 | 文字 LLM 的權重不更新；只有 resampler + 交叉注意力層在訓練 |
| 少樣本 | 「脈絡內範例」 | 在提示詞裡給幾組 (影像, 答案) 配對；模型不必微調就能類推 |
| OBELICS | 「交錯網頁語料」 | 一份開放資料集，含 1.41 億個依閱讀順序排列影像與文字的網頁 |
| Chinchilla | 「70B 的凍結基礎模型」 | Flamingo 凍結的文字 LLM，出自 DeepMind 的 Chinchilla 論文 |
| 閘門排程 | 「alpha 怎麼動」 | 訓練期間交叉注意力閘門打開的速率 |
| 交叉注意力頻率 | 「每 M 層一次」 | 隔多久插入一個帶閘門交叉注意力區塊；Flamingo 用 M=4 |
| OpenFlamingo | 「開放重現版」 | MosaicML／LAION 的 3B 到 9B 開放檢查點；架構與 Flamingo 相同 |

## 延伸閱讀

- [Alayrac et al. — Flamingo (arXiv:2204.14198)](https://arxiv.org/abs/2204.14198) —— 原始論文。
- [Awadalla et al. — OpenFlamingo (arXiv:2308.01390)](https://arxiv.org/abs/2308.01390) —— 開放重現版。
- [Laurençon et al. — OBELICS (arXiv:2306.16527)](https://arxiv.org/abs/2306.16527) —— 交錯網頁語料。
- [Jaegle et al. — Perceiver IO (arXiv:2107.14795)](https://arxiv.org/abs/2107.14795) —— 通用的 Perceiver 架構。
- [Li et al. — Otter (arXiv:2305.03726)](https://arxiv.org/abs/2305.03726) —— 經指令微調的 Flamingo 後裔。
- [Laurençon et al. — Idefics2 (arXiv:2405.02246)](https://arxiv.org/abs/2405.02246) —— Flamingo 路線的現代簡化版。
