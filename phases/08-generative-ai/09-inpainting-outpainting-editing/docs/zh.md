# 修補、外擴與影像編輯

> 文字生圖做的是新東西。修補修的是舊東西。在生產環境裡，70% 能收費的影像工作都是編輯 —— 換背景、去 logo、把畫布延伸出去、把一隻手重新生成一次。修補才是擴散模型真正賺錢的地方。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 8 · 07（潛在擴散）、階段 8 · 08（ControlNet 與 LoRA）
**時間：** 約 75 分鐘

## 問題所在

客戶寄來一張完美的產品照，但背景有一塊很礙眼的招牌。你想把招牌擦掉，其餘部分要逐像素保持原樣。你不能從零跑一次文字生圖 —— 那樣出來的顏色會不一樣、打光會不一樣、產品角度也會不一樣。你要的是*只*重新生成遮罩區域，而且重新生成的內容要照顧到周圍的脈絡。

這就是修補。它有幾種變形：

- **修補（inpainting）。** 重新生成遮罩內部，保留外部像素。
- **外擴（outpainting）。** 重新生成遮罩外部（或畫布之外的區域），保留內部。
- **影像編輯。** 整張影像都重新生成，但要保持與原圖在語意或結構上的一致（SDEdit、InstructPix2Pix）。

2026 年的每一條擴散流程都附了修補模式。Flux.1-Fill、Stable Diffusion Inpaint、SDXL-Inpaint、DALL-E 3 Edit。它們的原理都一樣。

## 核心概念

![修補：具遮罩感知的去噪，並持續重新注入脈絡](../assets/inpainting.svg)

### 直覺做法（以及它為什麼不對）

用一張遮罩去跑標準的文字生圖。每一個取樣步驟，都把有雜訊潛在表示的未遮罩區域替換成前向擴散後的乾淨影像。這確實能動……但動得很爛。邊界瑕疵會滲出來，因為模型完全不知道遮罩區域裡面是什麼。

### 正規的修補模型

訓練一個改造過的 U-Net，輸入通道從 4 個變成 9 個：

```
input = concat([ noisy_latent (4ch), encoded_image (4ch), mask (1ch) ], dim=channel)
```

多出來的通道，是 VAE 編碼後的來源影像複本，加上一張單通道遮罩。訓練時隨機遮住影像的某些區域，讓模型只針對遮罩區域去噪，同時把未遮罩區域當成乾淨的條件訊號餵進去。推論時，模型就能「看到」遮罩區域周圍是什麼，產出連貫的補完結果。

SD-Inpaint、SDXL-Inpaint、Flux-Fill 全都用這種 9 通道（或類似）的輸入。對應到 diffusers 的 `StableDiffusionInpaintPipeline`、`FluxFillPipeline`。

### SDEdit（Meng et al., 2022）—— 免訓練的編輯

把來源影像加噪到某個中間時刻 `t`，再帶著新的提示詞從 `t` 一路逆向跑到 0。不必重新訓練。起始 `t` 的選擇，就是在忠實度與創作自由之間取捨：

- `t/T = 0.3` → 幾乎與原圖相同，只有小幅風格變化
- `t/T = 0.6` → 中等程度的編輯，保留粗略結構
- `t/T = 0.9` → 近乎從純雜訊生成，幾乎不保留原圖

### InstructPix2Pix（Brooks et al., 2023）

用 `(input_image, instruction, output_image)` 三元組去微調一個擴散模型。推論時同時以輸入影像與一句文字指令為條件（「make it sunset」、「add a dragon」）。有兩個 CFG 強度：影像強度與文字強度。

### RePaint（Lugmayr et al., 2022）

沿用一個標準的無條件擴散模型。每個逆向步驟都重新取樣 —— 偶爾跳回較噪的狀態再重新生成。可以避開邊界瑕疵。當你手上沒有訓練好的修補模型時就用它。

```figure
inpaint-mask-reinject
```

## 動手實作

`code/main.py` 在 5 維資料上實作了一套 1 維的玩具修補方案。我們在 5 維混合資料上訓練一個 DDPM，每個樣本是來自兩個群集之一的 5 個浮點數。推論時「遮住」5 個維度中的 2 個，每一步都把未遮罩那三維的前向加噪版本注入回去，只重新生成被遮罩的維度。

### 步驟 1：5 維 DDPM 資料

```python
def sample_data(rng):
    cluster = rng.choice([0, 1])
    center = [-1.0] * 5 if cluster == 0 else [1.0] * 5
    return [c + rng.gauss(0, 0.2) for c in center], cluster
```

### 步驟 2：訓練涵蓋全部 5 維的去噪器

標準 DDPM。網路對 5 維的含噪輸入輸出 5 維的雜訊預測。

### 步驟 3：推論時做遮罩感知的逆向過程

```python
def inpaint_step(x_t, mask, clean_image, alpha_bars, t, rng):
    # replace unmasked dims with a freshly noised version of the clean source
    a_bar = alpha_bars[t]
    for i in range(len(x_t)):
        if not mask[i]:
            x_t[i] = math.sqrt(a_bar) * clean_image[i] + math.sqrt(1 - a_bar) * rng.gauss(0, 1)
    # ...then run the normal reverse step on x_t
```

這就是那個直覺做法，在玩具 1 維資料上它是有效的。真正的影像修補會用 9 通道輸入，因為紋理的連貫性更要緊。

### 步驟 4：外擴

外擴就是把遮罩反過來的修補：遮住新的（原本並不存在的）畫布區域，其餘部分填入原圖。訓練目標完全相同。

## 常見陷阱

- **接縫。** 直覺做法會留下看得見的邊界，因為梯度資訊不會跨過遮罩流動。解法：把遮罩膨脹 8 到 16 個像素，或改用正規的修補模型。
- **遮罩外洩。** 如果條件影像的未遮罩區域品質不佳或帶有雜訊，它會汙染遮罩內部的生成結果。先去噪或稍微模糊一下。
- **CFG 會與遮罩大小交互作用。** 小遮罩配上高 CFG＝一塊過飽和的補丁。小範圍編輯就把 CFG 調低。
- **SDEdit 的忠實度斷崖。** 從 `t/T = 0.5` 走到 `t/T = 0.6`，可能就把主體的身分弄丟了。掃一遍參數並留下檢查點。
- **提示詞對不上。** 提示詞應該描述*整張*影像，而不是只描述新增的內容。要寫「A cat sitting on a chair」，不是「a cat」。

## 框架應用

| 任務 | 流程 |
|------|----------|
| 移除物件、小遮罩 | SD-Inpaint 或 Flux-Fill，用一般提示詞 |
| 換天空 | SD-Inpaint +「blue sky at sunset」 |
| 延伸畫布 | SDXL 外擴模式（8px 羽化）或 Flux-Fill 搭配外擴遮罩 |
| 重新生成手／臉 | SD-Inpaint，提示詞重新描述主體 + ControlNet-Openpose |
| 更換某一區域的風格 | 在遮罩區域上用 `t/T=0.5` 的 SDEdit |
| 「Make it sunset」 | InstructPix2Pix 或 Flux-Kontext |
| 背景替換 | SAM 遮罩 → SD-Inpaint |
| 極致忠實度 | 最難的案例交給 Flux-Fill 或 GPT-Image（託管服務） |

SAM（Meta 的 Segment Anything，2023）+ 擴散修補，就是 2026 年的去背流程。SAM 2（2024）可以處理影片。

## 產出交付

存成 `outputs/skill-editing-pipeline.md`。這項技能吃一張原始影像 + 編輯描述 + 選用的遮罩（或 SAM 提示），輸出：遮罩生成方式、基礎模型、CFG 強度（影像 + 文字）、SDEdit 的 t 或修補模式，以及一份 QA 檢查清單。

## 練習

1. **簡單。** 在 `code/main.py` 裡，把被遮罩維度的比例從 0.2 掃到 0.8。在哪個比例上，修補品質（遮罩維度上的殘差）會等同於無條件生成？
2. **中等。** 實作 RePaint：每 10 個逆向步驟就往回跳 5 步（加噪）並重新去噪。量測它是否降低了遮罩邊緣的邊界殘差。
3. **困難。** 用 Hugging Face diffusers 做對照：在 20 個臉部重新生成任務上比較 SD 1.5 Inpaint + ControlNet-Openpose 與 Flux.1-Fill。分別為姿態遵循度與身分保持度評分。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 修補 | 「把洞補起來」 | 重新生成遮罩內部；保留外部像素。 |
| 外擴 | 「把畫布延伸出去」 | 重新生成畫布之外的區域；保留內部。 |
| 9 通道 U-Net | 「正規的修補模型」 | 以 `noisy \| encoded-source \| mask` 為輸入的 U-Net。 |
| SDEdit | 「帶雜訊強度的 img2img」 | 加噪到時刻 `t`，再用新提示詞去噪。 |
| InstructPix2Pix | 「純文字編輯」 | 用（影像、指令、輸出）三元組微調過的擴散模型。 |
| RePaint | 「不用重新訓練」 | 逆向過程中週期性地重新加噪，藉此減少接縫。 |
| SAM | 「Segment Anything」 | 靠點擊或方框產生遮罩的產生器；與修補搭配使用。 |
| Flux-Kontext | 「帶脈絡的編輯」 | Flux 的變體，接受一張參考影像 + 一句指令來做編輯。 |

## 產品筆記：編輯流程對延遲很敏感

在編輯影像的使用者期待 5 秒內來回。1024² 下跑 30 步的 SDXL-Inpaint，在 L4 上要 3 到 4 秒，再加上 SAM 遮罩生成（約 200 ms）以及 VAE 編碼／解碼（合計約 500 ms）。用生產環境的說法，這是受 TTFT 限制而非受吞吐量限制 —— 批次為 1、併發量低，每一段都要壓到最短：

- **SAM-H 是慢的那個。** SAM-H 在 1024² 下約 200 ms；SAM-ViT-B 約 40 ms，品質只掉一點點。SAM 2（影片版）會帶來時間維度的額外開銷；單張影像編輯不要用它。
- **能省的編碼就省掉。** `pipe.image_processor.preprocess(img)` 會把影像編碼成潛在表示。如果你手上已有上一次生成留下的潛在表示（在迭代式編輯的 UI 裡很常見），就直接用 `latents=...` 傳進去，省掉一次 VAE 編碼。
- **遮罩膨脹對吞吐量也有影響。** 遮罩很小，就代表 U-Net 前向傳播大部分算力都白費了（未遮罩的像素反正會被夾回去）。`diffusers` 的 `StableDiffusionInpaintPipeline` 不管三七二十一都跑完整個 U-Net；只有 9 通道的正規修補變體才會善用遮罩來省算力。
- **Flux-Kontext 是 2025 年的答案。** 對 `(source_image, instruction)` 只跑一次前向傳播 —— 不需要另外的遮罩，不需要掃 SDEdit 的雜訊強度。在 H100 上約 1.5 秒就交出一次編輯。這裡的架構課題是：把階段折疊起來。

## 延伸閱讀

- [Lugmayr et al. (2022). RePaint: Inpainting using Denoising Diffusion Probabilistic Models](https://arxiv.org/abs/2201.09865) —— 免訓練的修補。
- [Meng et al. (2022). SDEdit: Guided Image Synthesis and Editing with Stochastic Differential Equations](https://arxiv.org/abs/2108.01073) —— SDEdit。
- [Brooks, Holynski, Efros (2023). InstructPix2Pix](https://arxiv.org/abs/2211.09800) —— 文字指令式編輯。
- [Kirillov et al. (2023). Segment Anything](https://arxiv.org/abs/2304.02643) —— SAM，遮罩的來源。
- [Ravi et al. (2024). SAM 2: Segment Anything in Images and Videos](https://arxiv.org/abs/2408.00714) —— 影片版 SAM。
- [Hertz et al. (2022). Prompt-to-Prompt Image Editing with Cross-Attention Control](https://arxiv.org/abs/2208.01626) —— 注意力層級的編輯。
- [Black Forest Labs (2024). Flux.1-Fill and Flux.1-Kontext](https://blackforestlabs.ai/flux-1-tools/) —— 2024 年的工具組。
