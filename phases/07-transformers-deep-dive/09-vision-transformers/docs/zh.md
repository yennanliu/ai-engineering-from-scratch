# 視覺 Transformer（ViT）

> 影像是一格一格影像區塊組成的網格。句子是一個一個詞元組成的網格。同一個 transformer 兩種都吃。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 05（完整的 Transformer）、階段 4 · 03（CNN）、階段 4 · 14（視覺 Transformer 導論）
**時間：** 約 45 分鐘

## 問題所在

2020 年之前，電腦視覺就等於卷積。ImageNet、COCO 與各種偵測基準上的每一個 SOTA 都用 CNN 主幹。Transformer 是語言的東西。

Dosovitskiy 等人（2020）——「An Image is Worth 16x16 Words」——證明了卷積可以整個丟掉。把影像切成固定大小的影像區塊，每一塊線性投影成一個嵌入，再把這個序列餵給一個普通的 transformer 編碼器。在足夠規模下（ImageNet-21k 預訓練或更大），ViT 追平甚至打敗以 ResNet 為基礎的模型。

ViT 是 2026 年一個更大格局的起點：一套架構，多種模態。Whisper 把音訊變成詞元。ViT 把影像變成詞元。機器人有動作詞元。影片有像素詞元。Transformer 根本不在意——餵它一個序列，它就學。

到了 2026 年，ViT 及其後代（DeiT、Swin、DINOv2、ViT-22B、SAM 3）拿下了視覺領域的大半。CNN 在邊緣裝置與對延遲敏感的任務上仍然勝出。其他所有場景的技術堆疊裡，某處都有一個 ViT。

## 核心概念

![影像 → 影像區塊 → 詞元 → transformer](../assets/vit.svg)

### 步驟 1 —— 切成影像區塊

把一張 `H × W × C` 的影像切成 `N × (P·P·C)` 的攤平影像區塊序列。典型設定：`224 × 224` 的影像、`16 × 16` 的影像區塊 → 196 個影像區塊，每個 768 個數值。

```
image (224, 224, 3) → 14 × 14 grid of 16x16x3 patches → 196 vectors of length 768
```

影像區塊大小就是那根調節桿。區塊越小 = 詞元越多、解析度越好、注意力成本呈二次成長。區塊越大 = 越粗、越便宜。

### 步驟 2 —— 線性嵌入

單一個學習出來的矩陣，把每個攤平的影像區塊投影到 `d_model`。這等價於卷積核大小 `P`、stride `P` 的卷積。在 PyTorch 裡它就字面上是 `nn.Conv2d(C, d_model, kernel_size=P, stride=P)`——兩行就實作完了。

### 步驟 3 —— 在最前面接上 `[CLS]` 詞元、加上位置嵌入

- 在序列最前面接上一個可學習的類別詞元 `[CLS]`。它最後的隱藏狀態就是拿來做分類的影像表示。
- 加上可學習的位置嵌入（原版 ViT），或正弦式的 2D 位置編碼（後續變體）。
- 2024 年之後 RoPE 被擴展到 2D 來表示位置，有時候連顯式的位置嵌入都不要了。

### 步驟 4 —— 標準的 transformer 編碼器

疊 L 個 `LayerNorm → Self-Attention → + → LayerNorm → MLP → +` 區塊。跟 BERT 完全相同。沒有任何視覺專屬的層。這正是這篇論文在教學上最精華的一擊。

### 步驟 5 —— 輸出頭

做分類：取 `[CLS]` 的隱藏狀態 → 線性層 → softmax。做 DINOv2 或 SAM：把 `[CLS]` 丟掉，直接用各個影像區塊的嵌入。

### 真正有影響力的變體

| 模型 | 年份 | 改了什麼 |
|-------|------|--------|
| ViT | 2020 | 原版。固定的影像區塊大小、完整的全域注意力。 |
| DeiT | 2021 | 蒸餾；只用 ImageNet-1k 就訓得起來。 |
| Swin | 2021 | 階層式加位移視窗。把成本壓到次二次。 |
| DINOv2 | 2023 | 自監督（不用標籤）。最好的通用視覺特徵。 |
| ViT-22B | 2023 | 220 億參數；擴展法則同樣適用。 |
| SigLIP | 2023 | ViT 配上語言側，採用 sigmoid 對比損失。 |
| SAM 3 | 2025 | Segment anything；ViT-Large 加上可提示的遮罩解碼器。 |

### 為什麼花了這麼久

ViT 需要*非常多*資料才追得上 CNN，因為它完全沒有 CNN 的那些歸納偏差（平移不變性、局部性）。少了超過一億張標註影像，或是強力的自監督預訓練，在同等算力下 CNN 依然勝出。DeiT 在 2021 年用蒸餾技巧補上了這個缺口；DINOv2 在 2023 年用自監督徹底解決了它。

## 動手實作

請看 `code/main.py`。純標準函式庫的切塊 + 線性嵌入 + 健全性檢查。不做訓練——任何實際規模的 ViT 都需要 PyTorch 與好幾個小時的 GPU 時間。

### 步驟 1：假影像

一張 24 × 24 的 RGB 影像，表示成一個由 `(R, G, B)` 元組構成的列的列表。我們用 6×6 的影像區塊 → 16 個影像區塊，每個對應一個 108 維的嵌入向量。

### 步驟 2：切成影像區塊

```python
def patchify(image, P):
    H = len(image)
    W = len(image[0])
    patches = []
    for i in range(0, H, P):
        for j in range(0, W, P):
            patch = []
            for di in range(P):
                for dj in range(P):
                    patch.extend(image[i + di][j + dj])
            patches.append(patch)
    return patches
```

掃描順序：在網格上以列為主（row-major）。每一個 ViT 都用這個順序。

### 步驟 3：線性嵌入

把每個攤平的影像區塊乘上一個隨機的 `(patch_flat_size, d_model)` 矩陣。接上類別詞元 `[CLS]` 之後，驗證輸出形狀是 `(N_patches + 1, d_model)`。

### 步驟 4：算一個實際 ViT 的參數量

把 ViT-Base 的參數量印出來：12 層、12 個注意力頭、d=768、patch=16。跟 ResNet-50（約 2,500 萬）比較。ViT-Base 落在約 8,600 萬。ViT-Large 約 3.07 億。ViT-Huge 約 6.32 億。

## 框架應用

```python
from transformers import ViTImageProcessor, ViTModel
import torch
from PIL import Image

processor = ViTImageProcessor.from_pretrained("google/vit-base-patch16-224-in21k")
model = ViTModel.from_pretrained("google/vit-base-patch16-224-in21k")

img = Image.open("cat.jpg")
inputs = processor(img, return_tensors="pt")
out = model(**inputs).last_hidden_state   # (1, 197, 768): [CLS] + 196 patches
cls_emb = out[:, 0]                       # image representation
```

**在 2026 年，影像特徵的預設就是 DINOv2 的嵌入。** 凍結主幹，訓練一個很小的輸出頭。分類、檢索、偵測、看圖說話都行得通。Meta 的 DINOv2 檢查點在每一項非文字的視覺任務上都勝過 CLIP。

**影像區塊大小怎麼挑。** 小模型用 16×16（ViT-B/16）。稠密預測（分割）用 8×8 或 14×14（SAM、DINOv2）。非常大的模型用 14×14。

## 產出交付

請看 `outputs/skill-vit-configurator.md`。這項技能會依資料集規模、解析度與算力預算，替一個新的視覺任務挑選 ViT 變體與影像區塊大小。

## 練習

1. **簡單。** 執行 `code/main.py`。驗證影像區塊的數量等於 `(H/P) * (W/P)`，且攤平後的區塊維度等於 `P*P*C`。
2. **中等。** 實作 2D 正弦式位置嵌入——為每個影像區塊的 `row` 與 `col` 各算一組獨立的正弦編碼，再串接起來。把它餵進一個很小的 PyTorch ViT，在 CIFAR-10 上跟可學習的位置嵌入比較準確率。
3. **困難。** 用 PyTorch 建一個 3 層的 ViT，以 4×4 的影像區塊在 1,000 張 MNIST 影像上訓練。量測測試準確率。接著在同樣這 1,000 張影像上加上 DINOv2 預訓練（簡化版：只訓練編碼器從被遮住的影像區塊預測區塊嵌入）。準確率有進步嗎？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 影像區塊 | 「視覺 transformer 的詞元」 | 影像上一塊 `P × P × C` 區域的像素值攤平成的向量。 |
| 切成影像區塊 | 「切開 + 攤平」 | 把影像切成互不重疊的影像區塊，每一塊攤平成一個向量。 |
| 類別詞元 `[CLS]` | 「整張影像的摘要」 | 接在最前面的可學習詞元；它最後的嵌入就是那張影像的表示。 |
| 歸納偏差 | 「模型預設了什麼」 | ViT 的先驗比 CNN 少；要靠更多資料把這個差距補起來。 |
| DINOv2 | 「自監督的 ViT」 | 不用標籤，靠影像增強加動量教師模型訓練而成。2026 年最好的通用影像特徵。 |
| SigLIP | 「CLIP 的接班人」 | ViT 加文字編碼器，以 sigmoid 對比損失訓練；同等算力下勝過 CLIP。 |
| Swin | 「視窗化的 ViT」 | 階層式 ViT，採用局部注意力加位移視窗；成本是次二次的。 |
| 寄存詞元（register tokens） | 「2023 年的小技巧」 | 幾個額外的可學習詞元，用來吸收注意力匯點；能改善 DINOv2 的特徵。 |

## 延伸閱讀

- [Dosovitskiy et al. (2020). An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale](https://arxiv.org/abs/2010.11929) —— ViT 論文。
- [Touvron et al. (2021). Training data-efficient image transformers & distillation through attention](https://arxiv.org/abs/2012.12877) —— DeiT。
- [Liu et al. (2021). Swin Transformer: Hierarchical Vision Transformer using Shifted Windows](https://arxiv.org/abs/2103.14030) —— Swin。
- [Oquab et al. (2023). DINOv2: Learning Robust Visual Features without Supervision](https://arxiv.org/abs/2304.07193) —— DINOv2。
- [Darcet et al. (2023). Vision Transformers Need Registers](https://arxiv.org/abs/2309.16588) —— DINOv2 用的那個 register-token 修法。
