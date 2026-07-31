# 潛在擴散與 Stable Diffusion

> 在 512×512 影像上做像素空間擴散，簡直是計算資源上的戰爭罪。Rombach 等人（2022）注意到：要生成一張影像，你並不需要全部 78.6 萬個維度 —— 你只需要足以捕捉語意結構的那些，其餘交給另一個解碼器。把擴散放進 VAE 的潛在空間裡跑。這一個想法就是 Stable Diffusion。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 8 · 02（VAE）、階段 8 · 06（DDPM）、階段 7 · 09（ViT）
**時間：** 約 75 分鐘

## 問題所在

512² 的像素空間擴散，意味著 U-Net 要跑在形狀為 `[B, 3, 512, 512]` 的張量上。對一個 5 億參數的 U-Net 來說，每一個取樣步驟約 100 GFLOPS。五十步就是每張影像 5 TFLOPS。拿十億張影像去訓練，這筆算力帳單荒謬到不行。

那些 FLOPs 大多花在把感知上不重要的細節推過網路 —— 那些有損 VAE 本來就能壓掉的高頻紋理。Rombach 的想法是：先把一個 VAE 訓練好（*第一階段*），凍結它，然後整個擴散都在 4 通道 64×64 的潛在空間裡跑（*第二階段*）。U-Net 不變。像素數只剩十六分之一。在品質相當的前提下，FLOPs 少了約 64 倍。

這就是 Stable Diffusion 的配方。SD 1.x／2.x 在 `64×64×4` 的潛在表示上用 8.6 億參數的 U-Net，SDXL 在 `128×128×4` 上用 26 億參數的 U-Net，SD3 則把 U-Net 換成搭配 flow matching 的擴散 Transformer（DiT）。Flux.1-dev（Black Forest Labs, 2024）推出的是 120 億參數的 DiT-MMDiT。它們全都跑在同一套兩階段地基上。

## 核心概念

![潛在擴散：VAE 壓縮 + 在潛在空間裡做擴散](../assets/latent-diffusion.svg)

**兩個階段，分開訓練。**

1. **第一階段 —— VAE。** 編碼器 `E(x) → z`，解碼器 `D(z) → x`。壓縮目標：兩個空間軸各降採樣 8 倍，再調整通道數，使潛在表示的總大小約為像素數的十六分之一。損失 = 重建（L1 + LPIPS 感知）+ KL（權重很小，這樣 `z` 不會被硬逼成高斯，因為我們並不需要真的從 `z` 取樣）。通常還會加上對抗損失，讓解碼出來的影像夠銳利。

2. **第二階段 —— 在 `z` 上做擴散。** 把 `z = E(x_real)` 當成資料。訓練一個 U-Net（或 DiT）去為 `z_t` 去噪。推論時：先用擴散取樣出 `z_0`，再算 `x = D(z_0)`。

**文字條件控制。** 多兩個元件。一個凍結的文字編碼器（SD 1.x 用 CLIP-L，SD 2／XL 用 CLIP-L+OpenCLIP-G，SD3 與 Flux 用 T5-XXL）。以及一個交叉注意力注入點：每個 U-Net 區塊都吃 `[Q = image features, K = V = text tokens]` 並把它們混起來。這些詞元是文字影響影像的唯一途徑。

**損失函式和單元 06 完全一樣。** 同一套 DDPM／flow matching 的雜訊 MSE。你只是換了資料所在的定義域。

## 架構變體

| 模型 | 年份 | 骨幹 | 潛在形狀 | 文字編碼器 | 參數量 |
|-------|------|----------|--------------|--------------|--------|
| SD 1.5 | 2022 | U-Net | 64×64×4 | CLIP-L（77 詞元） | 860M |
| SD 2.1 | 2022 | U-Net | 64×64×4 | OpenCLIP-H | 865M |
| SDXL | 2023 | U-Net + refiner | 128×128×4 | CLIP-L + OpenCLIP-G | 2.6B + 6.6B |
| SDXL-Turbo | 2023 | 蒸餾版 | 128×128×4 | 同上 | 1 到 4 步取樣 |
| SD3 | 2024 | MMDiT（多模態 DiT） | 128×128×16 | T5-XXL + CLIP-L + CLIP-G | 2B／8B |
| Flux.1-dev | 2024 | MMDiT | 128×128×16 | T5-XXL + CLIP-L | 12B |
| Flux.1-schnell | 2024 | MMDiT 蒸餾版 | 128×128×16 | T5-XXL + CLIP-L | 12B，1 到 4 步 |

趨勢是：用 DiT（在潛在圖塊上跑的 Transformer）取代 U-Net、把文字編碼器放大（在提示詞遵循度上 T5 勝過 CLIP）、增加潛在通道數（4 → 16 給了更多細節餘裕）。

```figure
noise-schedule
```

## 動手實作

`code/main.py` 在單元 06 的 DDPM 之上疊了一個 1 維的玩具「VAE」（恆等的編碼器 + 解碼器，只為示範用；真正的 VAE 會是一個卷積網路），並加上帶無分類器引導的類別條件控制。它示範了同一個擴散損失無論跑在原始 1 維數值或編碼後的數值上都成立 —— 這就是關鍵洞見。

### 步驟 1：編碼器／解碼器

```python
def encode(x):    return x * 0.5          # toy "compression" to smaller scale
def decode(z):    return z * 2.0
```

真正的 VAE 有訓練好的權重。就教學而言，這個線性映射已經足以說明：擴散是在 `z` 上運作的，它不在乎原本的資料空間長什麼樣。

### 步驟 2：在 `z` 空間裡做擴散

和單元 06 的 DDPM 一樣。網路看到的資料是 `z = E(x)`。取樣出 `z_0` 之後，用 `D(z_0)` 解碼。

### 步驟 3：無分類器引導

訓練時有 10% 的機率把類別標籤丟掉（換成空詞元）。推論時同時算出 `ε_cond` 與 `ε_uncond`，然後：

```python
eps_cfg = (1 + w) * eps_cond - w * eps_uncond
```

`w = 0` 表示沒有引導（多樣性最大），`w = 3` 是預設，`w = 7+` 會過飽和／過銳。

### 步驟 4：文字條件控制（概念，不是程式碼）

把類別標籤換成凍結文字編碼器的輸出。透過交叉注意力把文字嵌入餵給 U-Net：

```python
h = h + CrossAttention(Q=h, K=text_embed, V=text_embed)
```

這就是類別條件擴散模型與 Stable Diffusion 之間唯一實質的差別。

## 常見陷阱

- **VAE 尺度沒對上。** SD 1.x 的 VAE 在編碼之後會套用一個縮放常數（`scaling_factor ≈ 0.18215`）。忘掉它，U-Net 就會在變異數大錯特錯的潛在表示上訓練。每一份檢查點都附了一個。
- **文字編碼器悄悄用錯。** SD3 需要 T5-XXL 搭配 >=128 個詞元，退回只用 CLIP 是有損的。一定要確認 `use_t5=True`，否則提示詞的忠實度會直接崩掉。
- **混用潛在空間。** SDXL、SD3、Flux 用的是不同的 VAE。在 SDXL 潛在表示上訓練的 LoRA 在 SD3 上不會動。Hugging Face diffusers 0.30+ 會拒絕載入對不上的檢查點。
- **CFG 太高。** `w > 10` 會產生過飽和、油膩感的影像，並以多樣性為代價過度擬合提示詞。甜蜜區間是 `w = 3-7`。
- **負面提示詞外洩。** 空的負面提示詞會變成空詞元；填了內容的負面提示詞則變成 `ε_uncond`。這兩者不是同一回事；有些流程會悄悄預設成空詞元。

## 框架應用

2026 年的生產技術棧：

| 目標 | 建議骨幹 |
|--------|----------------------|
| 窄領域、成對資料、從零訓練一個模型 | SDXL 微調（LoRA／完整）—— 最快上線 |
| 開放領域文字生圖、開放權重 | Flux.1-dev（12B，Apache／非商業）或 SD3.5-Large |
| 最快推論、開放權重 | Flux.1-schnell（1 到 4 步，Apache）或 SDXL-Lightning |
| 最佳提示詞遵循度、託管服務 | GPT-Image／DALL-E 3（目前仍是）、Midjourney v7、Imagen 4 |
| 編輯工作流 | Flux.1-Kontext（2024 年 12 月）—— 原生接受影像 + 文字 |
| 研究、基準線 | SD 1.5 —— 老古董，但被研究得很透徹 |

## 產出交付

存成 `outputs/skill-sd-prompter.md`。這項技能吃一段文字提示詞加上目標風格，輸出：模型 + 檢查點、CFG 強度、取樣器、負面提示詞、解析度、選用的 ControlNet／IP-Adapter 組合，以及一份逐步的 QA 檢查清單。

## 練習

1. **簡單。** 用引導強度 `w ∈ {0, 1, 3, 7, 15}` 執行 `code/main.py`。記錄每個類別的樣本平均值。在哪個 `w` 之後，各類別的平均值開始超出真實資料的平均值？
2. **中等。** 把玩具線性編碼器換成一對帶重建損失的 tanh-MLP 編碼器／解碼器。在新的潛在表示上重新訓練擴散。樣本品質有變嗎？
3. **困難。** 用 diffusers 架一套真正的 Stable Diffusion 推論：載入 `sdxl-base`，跑 30 步 Euler 搭配 CFG=7，計時。接著換成 `sdxl-turbo`，4 步、CFG=0。同一個主體、不同品質 —— 描述變了什麼、以及為什麼。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 第一階段 | 「那個 VAE」 | 訓練好的編碼器／解碼器對；把 512² 壓成 64²。 |
| 第二階段 | 「那個 U-Net」 | 跑在潛在空間上的擴散模型。 |
| CFG | 「引導強度」 | `(1+w)·ε_cond - w·ε_uncond`；調整條件控制的力道。 |
| 空詞元 | 「空提示詞的嵌入」 | 用來算 `ε_uncond` 的無條件嵌入。 |
| 交叉注意力 | 「文字是怎麼進來的」 | 每個 U-Net 區塊都把文字詞元當成 K 和 V 去注意。 |
| DiT | 「擴散 Transformer」 | 用在潛在圖塊上跑的 Transformer 取代 U-Net；擴展性更好。 |
| MMDiT | 「多模態 DiT」 | SD3 的架構：文字流與影像流做聯合注意力。 |
| VAE 縮放係數 | 「那個魔術數字」 | 把潛在表示除以約 5.4，讓擴散在單位變異數的空間裡運作。 |

## 產品筆記：在 8GB 消費級 GPU 上跑 Flux-12B

參考用的 Flux 整合方案，就是那份標準的「我只有一張消費級 GPU，這東西能上線嗎？」配方。訣竅就是生產推論文獻列出的那同樣三個旋鈕，套用到擴散 DiT 上：

1. **錯開載入。** Flux 有幾個網路從來不必同時待在 VRAM 裡：T5-XXL 文字編碼器（fp32 下約 10 GB）、CLIP-L（很小）、120 億參數的 MMDiT，以及 VAE。先把提示詞編碼好，*刪掉*編碼器，載入 DiT，去噪，*刪掉* DiT，載入 VAE，解碼。8GB 的消費級 GPU 一次只塞得下一個階段。
2. **用 bitsandbytes 做 4-bit 量化。** 在 T5 編碼器和 DiT 上都套 `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16)`。記憶體砍到八分之一，而依 Aritra 的基準測試（連結在 notebook 裡），文字生圖的品質下降是看不出來的。
3. **CPU 卸載。** `pipe.enable_model_cpu_offload()` 會隨著每次前向傳播推進，自動在 CPU 與 GPU 之間搬動模組。多付 10 到 20% 的延遲，但至少整條流程跑得起來。

記憶體帳是這樣算的：`10 GB T5 / 8 = 1.25 GB` 量化後、`12 B params × 0.5 bytes = ~6 GB` 量化後的 DiT，再加上激活值。用 stas00 的說法，這是 TP=1 推論的極端一端 —— 沒有模型平行，量化開到最滿。真要上生產，你會在 H100 上跑 TP=2 或 TP=4；但對一台開發用筆電來說，這就是配方。

## 延伸閱讀

- [Rombach et al. (2022). High-Resolution Image Synthesis with Latent Diffusion Models](https://arxiv.org/abs/2112.10752) —— Stable Diffusion。
- [Podell et al. (2023). SDXL: Improving Latent Diffusion Models for High-Resolution Image Synthesis](https://arxiv.org/abs/2307.01952) —— SDXL。
- [Peebles & Xie (2023). Scalable Diffusion Models with Transformers (DiT)](https://arxiv.org/abs/2212.09748) —— DiT。
- [Esser et al. (2024). Scaling Rectified Flow Transformers for High-Resolution Image Synthesis](https://arxiv.org/abs/2403.03206) —— SD3、MMDiT。
- [Ho & Salimans (2022). Classifier-Free Diffusion Guidance](https://arxiv.org/abs/2207.12598) —— CFG。
- [Labs (2024). Flux.1 — Black Forest Labs announcement](https://blackforestlabs.ai/announcing-black-forest-labs/) —— Flux.1 家族。
- [Hugging Face Diffusers docs](https://huggingface.co/docs/diffusers/index) —— 上述每一份檢查點的參考實作。
