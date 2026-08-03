# 評估 —— FID、CLIP score、人類偏好

> 每一份生成模型排行榜都會引用 FID、CLIP score，以及來自人類偏好競技場的勝率。每一個數字都有一種失效模式，一個夠執著的研究者就能拿來作弊。不知道這些失效模式，你就分不出哪些是真的進步、哪些只是刷分。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 8 · 01（分類體系）、階段 2 · 04（評估指標）
**時間：** 約 45 分鐘

## 問題所在

一個生成模型的好壞看兩件事：*樣本品質*與*條件貼合度*。兩者都沒有閉合形式的量測方法。你的模型得畫出 10,000 張影像；得有東西幫它們打上數字；而你還得相信這些數字能跨模型家族、跨解析度、跨架構地拿來比較。撐過 2014 到 2026 這場考驗的有三個評估指標：

- **FID（Fréchet Inception Distance）。** 在 Inception 網路的特徵空間裡，量測真實與生成這兩個分布之間的距離。越低越好。
- **CLIP score。** 生成影像的 CLIP 影像嵌入與提示詞的 CLIP 文字嵌入之間的餘弦相似度。越高越好。量的是提示詞貼合度。
- **人類偏好評估。** 讓兩個模型在同一個提示詞上正面對決，由人類（或一個 GPT-4 等級的模型）挑出比較好的那個，再彙總成 Elo 分數。

你也會看到：IS（inception score，大致上已經退役）、KID、CMMD、ImageReward、PickScore、HPSv2、MJHQ-30k。每一個都在修正前一個的某項缺陷。

## 核心概念

![FID、CLIP 與偏好：三條軸線，各自不同的失效模式](../assets/evaluation.svg)

### FID —— 樣本品質

Heusel 等人（2017）。步驟：

1. 為 N 張真實影像與 N 張生成影像抽取 Inception-v3 特徵（2048 維）。
2. 對每一組特徵擬合一個高斯分布：算出平均值 `μ_r, μ_g` 與共變異數 `Σ_r, Σ_g`。
3. FID = `||μ_r - μ_g||² + Tr(Σ_r + Σ_g - 2 · (Σ_r · Σ_g)^0.5)`。

解讀方式：特徵空間裡兩個多變量高斯分布之間的 Fréchet 距離。越低 = 兩個分布越相似。

失效模式：
- **小 N 有偏誤。** FID 是在特徵分布上取均方，N 太小會低估共變異數，給出假性偏低的 FID。一律用 N ≥ 10,000。
- **依賴 Inception。** Inception-v3 是在 ImageNet 上訓練的。離 ImageNet 很遠的領域（人臉、藝術、文字影像）算出來的 FID 沒有意義。改用該領域專屬的特徵抽取器。
- **可以刷分。** 對 Inception 的先驗過度擬合，就能在視覺品質毫無改善的情況下拿到低 FID。用 CMMD（見下文）來壓制這件事。

### CLIP score —— 提示詞貼合度

Radford 等人（2021）。對一張生成影像加上一段提示詞：

```
clip_score = cos_sim( CLIP_image(x_gen), CLIP_text(prompt) )
```

在 30k 張生成影像上取平均 → 得到一個可以在模型之間互相比較的純量。

失效模式：
- **CLIP 自己的盲點。** CLIP 的組合式推理能力很弱（「藍色球體上的紅色立方體」常常失敗）。模型可以在 CLIP score 上排得很前面，卻沒有真的遵循複雜的提示詞。
- **短提示詞偏誤。** 短提示詞在野外資料裡有更多 CLIP 影像可以對上。長提示詞的 CLIP score 會機械性地偏低。
- **提示詞刷分。** 在提示詞裡塞「high quality, 4k, masterpiece」會灌水 CLIP score，卻沒有改善圖文之間的綁定。

CMMD（Jayasumana 等人，2024）修掉了其中一部分問題：改用 CLIP 特徵而非 Inception，改用最大平均差異（MMD）而非 Fréchet 距離。在偵測細微品質差異上更好。

### 人類偏好評估 —— 真正的基準

挑一組提示詞。用模型 A 與模型 B 各生成一份。把成對的結果拿給人類（或一個夠強的 LLM 評審）看。把勝負彙總成 Elo 或 Bradley-Terry 分數。基準測試集：

- **PartiPrompts（Google）**：1,600 個多樣化提示詞，12 個類別。
- **HPSv2**：107k 筆人類標註，被廣泛當成自動化的代理指標。
- **ImageReward**：137k 組提示詞—影像偏好配對，MIT 授權。
- **PickScore**：在 Pick-a-Pic 的 2.6M 筆偏好上訓練。
- **Chatbot-Arena 風格的影像競技場**：https://imagearena.ai/ 之類的。

失效模式：
- **評審變異。** 非專家的偏好跟專家不一樣。兩邊都要用。
- **提示詞分布。** 精挑細選過的提示詞會偏袒某個家族。一定要寫清楚。
- **LLM 評審的獎勵駭客。** GPT-4 評審會被「漂亮但錯誤」的輸出騙過去。用人類評估來三角驗證。

## 搭配使用

一份生產級的評估報告應該包含：

1. 在 10 到 30k 個樣本上，對照一份留出的真實分布算 FID（樣本品質）。
2. 在同一批樣本上，對照它們的提示詞算 CLIP score／CMMD（貼合度）。
3. 在盲測競技場裡對上前一版模型的勝率（整體偏好）。
4. 失效模式分析：隨機抽 50 個輸出，標記出已知問題（手部結構、文字渲染、物件數量是否一致）。

任何單一評估指標都是謊言。三個互相佐證的指標 + 質性審視，才算一個主張。

```figure
gx-fid-distributions
```

## 動手實作

`code/main.py` 在合成的「特徵向量」上實作 FID、類 CLIP score 與 Elo 彙總（我們用 4 維向量來替代 Inception 特徵）。你會看到：

- 小 N 與大 N 之下的 FID 計算 —— 也就是那個偏誤。
- 用特徵組之間的餘弦相似度來當「CLIP score」。
- 從一串合成偏好資料流出發的 Elo 更新規則。

### 步驟 1：四行寫完 FID

```python
def fid(real_features, gen_features):
    mu_r, cov_r = mean_and_cov(real_features)
    mu_g, cov_g = mean_and_cov(gen_features)
    mean_diff = sum((a - b) ** 2 for a, b in zip(mu_r, mu_g))
    trace_term = trace(cov_r) + trace(cov_g) - 2 * sqrt_cov_product(cov_r, cov_g)
    return mean_diff + trace_term
```

### 步驟 2：CLIP 風格的餘弦相似度

```python
def clip_like(image_feat, text_feat):
    dot = sum(a * b for a, b in zip(image_feat, text_feat))
    norm = math.sqrt(dot_self(image_feat) * dot_self(text_feat))
    return dot / max(norm, 1e-8)
```

### 步驟 3：Elo 彙總

```python
def elo_update(r_a, r_b, winner, k=32):
    expected_a = 1 / (1 + 10 ** ((r_b - r_a) / 400))
    actual_a = 1.0 if winner == "a" else 0.0
    r_a_new = r_a + k * (actual_a - expected_a)
    r_b_new = r_b - k * (actual_a - expected_a)
    return r_a_new, r_b_new
```

## 常見陷阱

- **N=1000 的 FID。** 經驗上 N 低於 10k 就不可靠。回報低 N FID 的論文是在刷分。
- **跨解析度比較 FID。** Inception 的 299×299 縮放會改變特徵分布。只在解析度一致的情況下比較。
- **只報一個種子。** 至少跑 3 個種子。附上標準差。
- **用負向提示詞灌水 CLIP score。** 有些管線靠過度擬合提示詞來拉高 CLIP。檢查畫面是否過飽和。
- **提示詞重疊造成的 Elo 偏誤。** 如果兩個模型在訓練時都看過某個基準提示詞，Elo 就沒有意義。用留出的提示詞集。
- **付費群眾外包的人類評估偏斜。** Prolific、MTurk 的標註者偏年輕、偏親科技。混入招募來的藝術／設計專家。

## 框架應用

2026 年的生產級評估流程：

| 支柱 | 最低要求 | 建議做法 |
|--------|---------|-------------|
| 樣本品質 | 對照留出真實資料在 10k 上算 FID | 再加上 5k 的 CMMD + 每個類別子集的 FID |
| 提示詞貼合度 | 在 30k 上算 CLIP score | 再加上 HPSv2 + ImageReward + VQA 式問答 |
| 偏好 | 對照基準線的 200 組盲測配對 | 再加上 2000 組人類配對 + LLM 評審 + Chatbot Arena |
| 失效分析 | 50 個人工標記 | 500 個人工標記 + 自動化安全分類器 |

四根支柱都在同一份報告裡 = 一個主張。只有其中一根 = 行銷話術。

## 產出交付

存成 `outputs/skill-eval-report.md`。這項技能吃一個新的模型檢查點加上一條基準線，輸出一份完整的評估計畫：樣本數、評估指標、失效模式探測、放行標準。

## 練習

1. **簡單。** 跑 `code/main.py`。在同樣的合成分布上比較 N=100 與 N=1000 的 FID。回報偏誤的大小。
2. **中等。** 從合成的 CLIP 風格特徵實作 CMMD（公式見 Jayasumana 等人，2024）。比較它與 FID 對品質差異的敏感度。
3. **困難。** 複現 HPSv2 的設定：從 Pick-a-Pic 的一個子集取 1000 組影像—提示詞配對，在這些偏好上微調一個小型的 CLIP 評分器，再量測它與留出集合的一致程度。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| FID | 「Fréchet Inception Distance」 | 對真實與生成的 Inception 特徵各擬合高斯分布，再算兩者的 Fréchet 距離。 |
| CLIP score | 「圖文相似度」 | CLIP 影像嵌入與文字嵌入之間的餘弦相似度。 |
| CMMD | 「FID 的接班人」 | CLIP 特徵上的 MMD；偏誤更小，不假設高斯分布。 |
| IS | 「Inception score」 | Exp KL(p(y\|x) \|\| p(y))；在現代模型上相關性很差，已退役。 |
| HPSv2 / ImageReward / PickScore | 「學出來的偏好代理指標」 | 在人類偏好上訓練的小模型；拿來當自動評審。 |
| Elo | 「西洋棋積分」 | 對成對勝負做 Bradley-Terry 彙總。 |
| PartiPrompts | 「那個基準提示詞集」 | Google 精選的 1,600 個提示詞，橫跨 12 個類別。 |
| FD-DINO | 「自監督版的替代品」 | 用 DINOv2 特徵算 FD；在 ImageNet 以外的領域表現更好。 |

## 產品筆記：評估本身也是一種推論工作負載

在 10k 個樣本上跑 FID，意味著要生成 10k 張影像。以單張 L4 上 1024² 的 50 步 SDXL base 來算，那是約 11 小時的單請求推論。評估預算是實打實的成本，而它的框架正好就是離線推論的情境（把吞吐量拉滿，別管 TTFT）：

- **用力批次，忘掉延遲。** 離線評估 = 在記憶體塞得下的最大尺寸下做靜態批次。在 80GB H100 上用 `num_images_per_prompt=8` 跑 `pipe(...).images`，牆鐘時間比單請求快 4 到 6 倍。
- **把真實特徵快取起來。** 對真實參考集做 Inception（FID）或 CLIP（CLIP score、CMMD）特徵抽取這件事只跑*一次*，存成 `.npz`。不要每次評估都重算。

CI／回歸把關的做法：每個 PR 在 500 個樣本的子集上跑 FID + CLIP score（約 30 分鐘）；每晚跑完整的 10k FID + HPSv2 + Elo。

## 延伸閱讀

- [Heusel et al. (2017). GANs Trained by a Two Time-Scale Update Rule Converge to a Local Nash Equilibrium (FID)](https://arxiv.org/abs/1706.08500) —— FID 那篇論文。
- [Jayasumana et al. (2024). Rethinking FID: Towards a Better Evaluation Metric for Image Generation (CMMD)](https://arxiv.org/abs/2401.09603) —— CMMD。
- [Radford et al. (2021). Learning Transferable Visual Models from Natural Language Supervision (CLIP)](https://arxiv.org/abs/2103.00020) —— CLIP。
- [Wu et al. (2023). HPSv2: A Comprehensive Human Preference Score](https://arxiv.org/abs/2306.09341) —— HPSv2。
- [Xu et al. (2023). ImageReward: Learning and Evaluating Human Preferences for Text-to-Image Generation](https://arxiv.org/abs/2304.05977) —— ImageReward。
- [Yu et al. (2023). Scaling Autoregressive Models for Content-Rich Text-to-Image Generation (Parti + PartiPrompts)](https://arxiv.org/abs/2206.10789) —— PartiPrompts。
- [Stein et al. (2023). Exposing flaws of generative model evaluation metrics](https://arxiv.org/abs/2306.04675) —— 失效模式綜述。
