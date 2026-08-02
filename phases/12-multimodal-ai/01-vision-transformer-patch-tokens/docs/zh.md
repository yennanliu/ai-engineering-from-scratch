# Vision Transformer 與 patch-token 這個基本單位

> 在談任何多模態之前，影像得先變成一串 Transformer 吃得下的詞元。2020 年的 ViT 論文給的答案是：16x16 像素的區塊（patch）、一個線性投影，加上位置嵌入。五年後，2026 年的每個前沿模型（原生 2576px 的 Claude Opus 4.7、Gemini 3.1 Pro、Qwen3.5-Omni）依然從這裡開始 —— 編碼器從 ViT 換成 DINOv2 再換成 SigLIP 2，register 詞元加了進來，位置方案變成 2D-RoPE，但這個基本單位撐住了。這一課會把 patch-token 管線從頭到尾讀一遍，並用 stdlib Python 把它做出來，好讓 Phase 12 接下來的內容，對「視覺詞元」有一個具體的心智模型。

**類型：** 學習
**程式語言：** Python (stdlib, patch tokenizer + geometry calculator)
**先修單元：** 階段 7（Transformers）、階段 4（電腦視覺）
**時間：** 約 120 分鐘

## 學習目標

- 把一張 HxWx3 的影像，轉換成一串帶有正確位置編碼的 patch 詞元。
- 給定 (patch 大小、解析度、隱藏維度、深度)，算出一個 ViT 的序列長度、參數量與 FLOPs。
- 說出讓 ViT 從 2020 年的研究走到 2026 年生產環境的三項升級：自監督預訓練（DINO／MAE）、register 詞元，以及原生解析度打包。
- 針對一個下游任務，在 CLS pooling、mean pooling 與 register 詞元之間做出選擇。

## 問題所在

Transformer 處理的是向量序列。文字本來就是序列（位元組或詞元）。影像則是一個帶三個色彩通道的二維像素網格 —— 不是序列。如果你把每個像素攤平，一張 224x224 的 RGB 影像會變成 150,528 個詞元，在這種長度下做自注意力根本不用談（序列長度的平方複雜度）。

2020 年之前的做法，是在前面接一個 CNN 特徵抽取器：ResNet 產出一張 7x7、每格 2048 維向量的特徵圖，再把那 49 個詞元餵給 Transformer。這行得通，但也繼承了 CNN 的歸納偏誤（平移等變性、局部感受野），並且失去了 Transformer 對規模的胃口。

Dosovitskiy 等人（2020）直接問了一個粗暴的問題：如果我們乾脆跳過 CNN 呢？把影像切成固定大小的區塊（比方說 16x16 像素），對每一塊做線性投影得到一個向量，加上位置嵌入，然後把這串序列餵給一個普通的 Transformer。在當時這是異端 —— 不用卷積做視覺。但只要資料夠多（JFT-300M，後來是 LAION），它在 ImageNet 上就贏過 ResNet，而且還持續變好。

到了 2026 年，ViT 這個基本單位已是毫無疑問的地基。每個開放權重 VLM 的視覺塔都是它的後裔（DINOv2、SigLIP 2、CLIP、EVA、InternViT）。問題不再是「我們該不該用 patch？」，而是「patch 多大、解析度怎麼排程、預訓練目標是什麼、位置編碼用哪種」。

## 核心概念

### 把 patch 當詞元

給定一張形狀為 `(H, W, 3)` 的影像 `x` 與 patch 大小 `P`，你會把影像切成一個 `(H/P) x (W/P)` 的網格，各區塊互不重疊。每個 patch 是一個 `P x P x 3` 的像素立方體。把每個立方體攤平成一個 `3 P^2` 的向量。再套用一個形狀為 `(3 P^2, D)` 的共享線性投影 `W_E`，把每個 patch 映射到模型的隱藏維度 `D`。

以 ViT-B/16 的標準設定為例：
- 解析度 224、patch 大小 16 → 網格 14x14 → 196 個 patch 詞元。
- 每個 patch 是 `16 x 16 x 3 = 768` 個像素值，投影到 `D = 768`。
- 再加上一個可學習的 `[CLS]` 詞元 → 序列長度 197。

patch 投影在數學上，等同於一個 kernel 大小為 `P`、stride 為 `P`、輸出通道數為 `D` 的二維卷積。生產環境的程式碼實際上就是這樣寫的 —— `nn.Conv2d(3, D, kernel_size=P, stride=P)`。「線性投影」是概念上的說法；kernel 的說法才是有效率的實作。

### 位置嵌入

patch 本身沒有先後順序 —— Transformer 看到的是一袋東西。早期的 ViT 加了一個可學習的一維位置嵌入（每個位置一個 768 維向量，共 197 個）。這行得通，但會把模型綁死在訓練解析度上：推論時只要改變網格大小，你就得對位置表做內插。

現代的視覺骨幹用的是 2D-RoPE（Qwen2-VL 的 M-RoPE、SigLIP 2 的預設）或分解式的二維位置。2D-RoPE 會依據 patch 的 (列, 行) 索引去旋轉 query 與 key 向量，模型因此能從旋轉角度推得相對的二維位置。不需要位置表。推論時模型能處理任意大小的網格。

### CLS 詞元、pooled 輸出與 register 詞元

影像層級的表徵是什麼？三種選擇並存：

1. `[CLS]` 詞元。在 patch 序列前面接上一個可學習的向量。跑完所有 Transformer 區塊後，CLS 詞元的隱藏狀態就是影像的表徵。這是從 BERT 繼承來的。最初的 ViT 與 CLIP 都用它。
2. Mean pool。把所有 patch 詞元的輸出隱藏狀態取平均。SigLIP、DINOv2 與多數現代 VLM 都用這個。
3. Register 詞元。Darcet 等人（2023）觀察到，沒有明確 sink 詞元的 ViT 在訓練後會長出高範數的「假影」patch，把自注意力給劫持了。加上 4 到 16 個可學習的 register 詞元能吸收這股負載，並改善密集預測的品質（分割、深度）。DINOv2 與 SigLIP 2 出廠都帶 register。

這個選擇對下游任務有影響。要做分類，CLS 就夠了。至於把 patch 詞元餵進 LLM 的 VLM，你會完全跳過 pooling —— 每個 patch 都成為 LLM 的一個輸入詞元。register 則在交棒之前就被丟掉（它們是鷹架，不是內容）。

### 預訓練：監督式、對比式、遮罩式、自蒸餾

2020 年的 ViT 是用 JFT-300M 上的監督式分類做預訓練的。這很快就被取代了：

- CLIP（2021）：在 4 億組配對上做影像—文字對比學習。見單元 12.02。
- MAE（2021，He 等人）：遮掉 75% 的 patch，再重建像素。自監督，只用純影像就能跑。
- DINO（2021）／DINOv2（2023）：學生—教師的自蒸餾，不需要標籤，也不需要字幕。2023 年的 DINOv2 ViT-g/14 是最強的純視覺骨幹，也是「密集特徵」類用途的預設選擇。
- SigLIP／SigLIP 2（2023、2025）：換成 sigmoid 損失的 CLIP，並用 NaFlex 支援原生長寬比。2026 年開放 VLM 中最主流的視覺塔（Qwen、Idefics2、LLaVA-OneVision）。

你選的預訓練方式，決定了這個骨幹擅長什麼：CLIP／SigLIP 適合與文字做語意匹配，DINOv2 適合密集視覺特徵，MAE 則適合當作下游微調的起點。

### 尺度法則

ViT 的尺度研究（Zhai 等人 2022）確立了一件事：ViT 的品質在模型大小、資料量與計算量上，遵循可預測的法則。在固定計算量下：
- 模型更大 + 資料更多 → 品質更好。
- patch 大小是一根在序列長度與保真度之間拉扯的槓桿。patch 14（DINOv2／SigLIP SO400m 的典型值）每張影像產生的詞元比 patch 16 多；對 OCR 與密集任務更好，但速度較差。
- 解析度是另一根大槓桿。從 224 拉到 384 再拉到 512，幾乎總是有幫助，代價是 FLOPs 的平方成長。

ViT-g/14（10 億參數、patch 14、解析度 224 → 256 個詞元）與 SigLIP SO400m/14（4 億參數、patch 14）是 2026 年開放 VLM 的兩匹主力編碼器。

### 一個 ViT 的參數量

完整的計算在 `code/main.py` 裡。以 224 解析度的 ViT-B/16 為例：

```
patch_embed = 3 * 16 * 16 * 768 + 768  =  591k
cls + pos    = 768 + 197 * 768          =  152k
block        = 4 * 768^2 (QKVO) + 2 * 4 * 768^2 (MLP) + 2 * 2*768 (LN)
             = 12 * 768^2 + 3k          =  7.1M
12 blocks    = 85M
final LN    = 1.5k
total       ≈ 86M
```

在載入檢查點之前，先這樣估算每一個 ViT。骨幹的大小，會決定你在任何下游 VLM 中的 VRAM 下限。

### 2026 年的生產設定

2026 年多數開放 VLM 出廠搭載的編碼器，是原生解析度（NaFlex）的 SigLIP 2 SO400m/14。它的規格是：
- 4 億參數。
- patch 大小 14，預設解析度 384 → 每張影像 729 個 patch 詞元。
- 影像層級的任務用 mean pool；做 VQA 時全部 729 個 patch 都流進 LLM。
- 4 個 register 詞元，交棒給 LLM 之前丟掉。
- 帶影像層級縮放的 2D-RoPE，以支援原生長寬比。

這份設定裡的每一個決定，都能追溯到一篇你讀得到的論文。

```figure
image-patch-tokens
```

## 框架應用

`code/main.py` 是一個 patch 分詞器兼幾何計算器。它接收 (影像 H, W, patch P, 隱藏維度 D, 深度 L)，然後回報：

- 切塊後的網格形狀與序列長度。
- 一張 8x8 像素的合成玩具影像的詞元序列（走一遍攤平 + 投影的路徑）。
- 拆解成 patch embed、位置 embed、Transformer 區塊與 head 的參數量。
- 在目標解析度下，一次前向傳播的 FLOPs。
- 一張橫跨 ViT-B/16 @ 224、ViT-L/14 @ 336、DINOv2 ViT-g/14 @ 224、SigLIP SO400m/14 @ 384 的比較表。

跑跑看。把參數量對照已發表的數字。玩玩 patch 大小與解析度，感受一下詞元數量的代價。

## 產出交付

這一課產出 `outputs/skill-patch-geometry-reader.md`。給定一份 ViT 設定（patch 大小、解析度、隱藏維度、深度），它會產出詞元數、參數量與 VRAM 估算，並附上理由。每當你要為一個 VLM 挑選視覺骨幹時就用這項技能 —— 它能避免「詞元爆炸、我的 LLM 脈絡被塞爆了」這種驚喜。

## 練習

1. 算出 Qwen2.5-VL 在原生 1280x720 輸入、patch 大小 14 之下的 patch 詞元序列長度。這跟只用 CLS 的表徵相比如何？

2. 一張 1080p 的畫格（1920x1080）在 patch 14 之下會產生多少詞元？以 30 FPS 跑一段 5 分鐘的影片，總共有多少視覺詞元？pooling、畫格取樣、詞元合併，哪一種省得最多？

3. 用純 Python 實作對 patch 詞元的 mean pooling。驗證對 DINOv2 輸出的 196 個詞元做 mean-pool 的結果，與你向模型的 `forward` 索取 pooled 嵌入時拿到的一致。

4. 讀〈Vision Transformers Need Registers〉（arXiv:2309.16588）的第 3 節。用兩句話說明 register 吸收掉的是什麼假影，以及這對下游的密集預測為什麼重要。

5. 修改 `code/main.py` 以支援 patch-n'-pack：給定一串解析度各異的影像，產出單一的打包序列與對應的區塊對角注意力遮罩。等你讀到單元 12.06 時，再拿它來驗證。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| Patch | 「16x16 的像素方塊」 | 輸入影像上一塊固定大小、互不重疊的區域；會變成一個詞元 |
| Patch 嵌入 | 「線性投影」 | 一個共享的學習矩陣（或 stride=P 的 Conv2d），把攤平的 patch 像素映射成 D 維向量 |
| CLS 詞元 | 「類別詞元」 | 接在最前面的可學習向量，其最終隱藏狀態代表整張影像；在 2026 年是選配 |
| Register 詞元 | 「sink 詞元」 | 額外的可學習詞元，用來吸收 ViT 在預訓練期間長出的高範數注意力假影 |
| 位置嵌入 | 「位置資訊」 | 每個位置一個向量或一次旋轉，讓序列意識到順序；2D-RoPE 是現代的預設 |
| 網格 | 「patch 網格」 | 給定解析度與 patch 大小之下，那個 (H/P) x (W/P) 的二維 patch 陣列 |
| NaFlex | 「原生彈性解析度」 | SigLIP 2 的特性：單一模型不必重訓，就能服務多種長寬比與解析度 |
| 骨幹 | 「視覺塔」 | 預訓練好的影像編碼器，其 patch 詞元輸出會餵進 VLM 裡的 LLM |
| Pooling | 「影像層級的摘要」 | 把 patch 詞元變成單一向量的策略：CLS、平均、注意力池化，或基於 register |
| patch 14 對 16 | 「較細對較粗的網格」 | patch 14 每張影像產生更多詞元，OCR 的保真度更好但較慢；patch 16 是經典的預設值 |

## 延伸閱讀

- [Dosovitskiy et al. — An Image is Worth 16x16 Words (arXiv:2010.11929)](https://arxiv.org/abs/2010.11929) —— 最初的 ViT。
- [He et al. — Masked Autoencoders Are Scalable Vision Learners (arXiv:2111.06377)](https://arxiv.org/abs/2111.06377) —— MAE，自監督預訓練。
- [Oquab et al. — DINOv2 (arXiv:2304.07193)](https://arxiv.org/abs/2304.07193) —— 大規模自蒸餾，不用標籤。
- [Darcet et al. — Vision Transformers Need Registers (arXiv:2309.16588)](https://arxiv.org/abs/2309.16588) —— register 詞元與假影分析。
- [Tschannen et al. — SigLIP 2 (arXiv:2502.14786)](https://arxiv.org/abs/2502.14786) —— 2026 年的預設視覺塔。
- [Zhai et al. — Scaling Vision Transformers (arXiv:2106.04560)](https://arxiv.org/abs/2106.04560) —— 實證的尺度法則。
