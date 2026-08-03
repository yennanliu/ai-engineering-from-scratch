# 專家混合（MoE）

> 一個稠密的 700 億參數 transformer，每個詞元都要動用全部參數。一個 6,710 億參數的 MoE 每個詞元只激活 370 億，卻在每一項基準上贏過它。稀疏激活是這十年最重要的擴展想法。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 05（完整的 Transformer）、階段 7 · 07（GPT）
**時間：** 約 45 分鐘

## 問題所在

稠密 transformer 在推論時的 FLOPs 等於它的參數量（前向傳播再乘 2）。把稠密模型放大，每個詞元都要付全額帳單。到了 2024 年，前沿已經撞上一道算力牆：要顯著變聰明，每個詞元就得付出指數成長的 FLOPs。

專家混合把這個連動關係打斷。把每個 FFN 換成 `E` 個獨立專家，外加一個路由器替每個詞元挑 `k` 個專家。總參數量 = `E × FFN_size`。每個詞元的激活參數量 = `k × FFN_size`。2026 年的典型配置：`E=256`、每詞元專家數 `k=8`。儲存空間隨 `E` 成長，運算量隨 `k` 成長。

2026 年的前沿幾乎清一色是 MoE：DeepSeek-V3（總計 6,710 億／激活 370 億）、Mixtral 8×22B、Qwen2.5-MoE、Llama 4、Kimi K2、gpt-oss。在 Artificial Analysis 的獨立排行榜上，前 10 名的開源模型全都是 MoE。

## 核心概念

![MoE 層：路由器替每個詞元從 E 個專家中挑出 k 個](../assets/moe.svg)

### 把 FFN 換掉

稠密的 transformer 區塊：

```
h = x + attn(norm(x))
h = h + FFN(norm(h))
```

MoE 區塊：

```
h = x + attn(norm(x))
scores = router(norm(h))              # (N_tokens, E)
top_k = argmax_k(scores)              # pick k of E per token
h = h + sum_{e in top_k}(
        gate(scores[e]) * Expert_e(norm(h))
    )
```

每個專家都是一個獨立的 FFN（通常是 SwiGLU）。路由器只是單一個線性層。每個詞元自己挑 `k` 個專家，拿到的是它們輸出經門控網路加權後的混合。

### 負載平衡的問題

如果路由器把 90% 的詞元都送進專家 3，其他專家就會餓死。有三種解法被試過：

1. **輔助負載平衡損失**（Switch Transformer、Mixtral）。加一個與專家使用率變異數成正比的懲罰項。有效，但多了一個超參數與第二道梯度訊號。
2. **專家容量 + 丟棄詞元**（早期的 Switch）。每個專家最多處理 `C × N/E` 個詞元（容量因子就是 `C`）；超出的詞元直接跳過這一層。會傷品質。
3. **免輔助損失的平衡**（DeepSeek-V3）。為每個專家加上一個學習出來的偏置，用它去移動路由器的 top-k 選擇。偏置在訓練損失之外更新。主目標函式上沒有任何懲罰項。這是 2024 年的重大解放。

DeepSeek-V3 的做法：每個訓練步之後，逐一檢查每個專家的使用率是高於還是低於目標值。把偏置推動 `±γ`。選擇時用 `scores + bias`。而用於門控的專家機率仍然是原始的 `scores`，不做改動。這讓路由與表達彼此解耦。

### 共享專家

DeepSeek-V2/V3 還把專家分成*共享*與*路由*兩類。每個詞元都會經過所有共享專家。路由專家則由 top-k 挑選。共享專家承接通用知識；路由專家負責專精。V3 用 1 個共享專家，加上 256 個路由專家中的 top-8。

### 細粒度專家

經典 MoE（GShard、Switch）：每個專家跟完整的 FFN 一樣寬。`E` 很小（8 到 64），`k` 也很小（1 到 2）。

現代的細粒度 MoE（DeepSeek-V3、Qwen-MoE）：每個專家更窄（FFN 大小的 1/8）。`E` 很大（256 以上），`k` 也更大（8 以上）。總參數量相同，但組合數成長快得多。`C(256, 8) = 400 trillion` —— 每個詞元有 400 兆種可能的「專家」。品質往上走，延遲維持不變。

### 成本輪廓

每個詞元、每一層：

| 配置 | 每詞元激活參數 | 總參數 |
|--------|-----------------------|--------------|
| Mixtral 8×22B | 約 390 億 | 1,410 億 |
| Llama 3 70B（稠密） | 700 億 | 700 億 |
| DeepSeek-V3 | 370 億 | 6,710 億 |
| Kimi K2（MoE） | 約 320 億 | 1 兆 |

DeepSeek-V3 幾乎在每一項基準上都贏過稠密的 Llama 3 70B，而且**每個詞元的激活 FLOPs 還更少**。參數越多 = 知識越多。激活 FLOPs 越多 = 每個詞元的運算越多。MoE 把這兩件事解耦了。

### 代價：記憶體

不管實際會觸發哪些專家，所有專家都得待在 GPU 上。一個 6,710 億參數的模型，光是 fp16 權重就要約 1.3 TB 的 VRAM。前沿 MoE 的部署需要專家並行 —— 把專家切分到多張 GPU 上，讓詞元穿過網路被路由。延遲的主導因素是那些 all-to-all 通訊，不是矩陣乘法。

```figure
expert-routing
```

## 動手實作

請看 `code/main.py`。一個用純標準函式庫寫成的精簡 MoE 層，包含：

- `n_experts=8` 個類 SwiGLU 專家（為了示範，每個只用一個線性層）
- top-k=2 的路由
- 經 softmax 正規化的門控權重
- 透過每專家偏置實現的免輔助損失平衡

### 步驟 1：路由器

```python
def route(hidden, W_router, top_k, bias):
    scores = [sum(h * w for h, w in zip(hidden, W_router[e])) for e in range(len(W_router))]
    biased = [s + b for s, b in zip(scores, bias)]
    top_idx = sorted(range(len(biased)), key=lambda i: -biased[i])[:top_k]
    # softmax over ORIGINAL scores of the chosen experts
    chosen = [scores[i] for i in top_idx]
    m = max(chosen)
    exps = [math.exp(c - m) for c in chosen]
    s = sum(exps)
    gates = [e / s for e in exps]
    return top_idx, gates
```

偏置影響的是選擇，不是門控權重。這就是 DeepSeek-V3 的訣竅 —— 偏置修正負載不均，卻不去干擾模型的預測。

### 步驟 2：把 100 個詞元送過路由器

追蹤每個專家被觸發的頻率。沒有偏置時，使用率是偏斜的。加上偏置更新迴圈之後（過度使用的專家 `-γ`、使用不足的 `+γ`），使用率會在幾輪迭代內收斂到均勻分布。

### 步驟 3：參數量比較

印出一個 MoE 配置的「稠密等價量」。以 DeepSeek-V3 的形狀為例：256 個路由專家加 1 個共享專家、8 個激活、d_model=7168。總參數量看得人眼睛發直。而激活量只有稠密 Llama 3 70B 的七分之一。

## 框架應用

HuggingFace 的載入方式：

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
model = AutoModelForCausalLM.from_pretrained("mistralai/Mixtral-8x22B-v0.1")
```

2026 年的正式環境推論：vLLM 原生支援 MoE 路由。SGLang 有最快的專家並行路徑。兩者都會自動處理 top-k 選擇與專家並行。

**什麼時候該選 MoE：**
- 你想要前沿品質，同時降低每個詞元的推論成本。
- 你有足夠的 VRAM／專家並行基礎設施。
- 你的工作負載是詞元密集型（聊天、程式碼），而不是脈絡密集型（長文件）。

**什麼時候不該選 MoE：**
- 邊緣部署 —— 不管激活多少 FLOP，儲存空間都得付全額。
- 對延遲敏感的單使用者服務 —— 專家路由會帶來額外開銷。
- 小模型（低於 70 億）—— MoE 的品質優勢只在超過某個算力門檻（約 60 億激活參數）之後才出現。

## 產出交付

請看 `outputs/skill-moe-configurator.md`。這項技能會依參數預算、訓練詞元數與部署目標，替一個新的 MoE 挑選 E、k 與共享專家的佈局。

## 練習

1. **簡單。** 執行 `code/main.py`。觀察免輔助損失的偏置更新如何在 50 輪迭代內把專家使用率拉平。
2. **中等。** 把學習式路由器換成基於雜湊的路由器（決定性的，不學習）。比較品質與平衡度。為什麼學習式路由器比較好？
3. **困難。** 實作 GRPO 風格的「rollout 對齊路由」（DeepSeek-V3.2 的訣竅）：記錄推論期間觸發了哪些專家，在計算梯度時強制走同一套路由。在一個玩具級的策略梯度設定上量測它的效果。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 專家 | 「眾多 FFN 中的一個」 | 一個獨立的前饋網路；專屬於 FFN 運算中某個稀疏切片的參數。 |
| 路由器 | 「就是那個門控網路」 | 一個很小的線性層，替每個詞元對每個專家打分數；再做 top-k 選擇。 |
| Top-k routing | 「每個詞元 k 個激活專家」 | 每個詞元的 FFN 運算恰好經過 k 個專家，並依門控權重加權。 |
| 輔助損失 | 「負載平衡的懲罰項」 | 額外的損失項，用來懲罰偏斜的專家使用率。 |
| 免輔助損失 | 「DeepSeek-V3 的訣竅」 | 只在路由器的選擇端用每專家偏置來平衡；不引入額外梯度。 |
| 共享專家 | 「永遠開著」 | 額外的專家，每個詞元都會經過它；負責承接通用知識。 |
| 專家並行 | 「按專家切分」 | 把不同專家分配到不同 GPU；讓詞元穿過網路被路由。 |
| 稀疏性 | 「激活參數 < 總參數」 | 比值 `k × expert_size / (E × expert_size)`；DeepSeek-V3 是 37/671 ≈ 5.5%。 |

## 延伸閱讀

- [Shazeer et al. (2017). Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer](https://arxiv.org/abs/1701.06538) —— 這個想法的源頭。
- [Fedus, Zoph, Shazeer (2022). Switch Transformer: Scaling to Trillion Parameter Models with Simple and Efficient Sparsity](https://arxiv.org/abs/2101.03961) —— Switch，經典的 MoE。
- [Jiang et al. (2024). Mixtral of Experts](https://arxiv.org/abs/2401.04088) —— Mixtral 8×7B。
- [DeepSeek-AI (2024). DeepSeek-V3 Technical Report](https://arxiv.org/abs/2412.19437) —— MLA + 免輔助損失的 MoE + MTP。
- [Wang et al. (2024). Auxiliary-Loss-Free Load Balancing Strategy for Mixture-of-Experts](https://arxiv.org/abs/2408.15664) —— 基於偏置做平衡的那篇論文。
- [Dai et al. (2024). DeepSeekMoE: Towards Ultimate Expert Specialization in Mixture-of-Experts Language Models](https://arxiv.org/abs/2401.06066) —— 本單元路由器所採用的細粒度加共享專家拆分。
- [Kim et al. (2022). DeepSpeed-MoE: Advancing Mixture-of-Experts Inference and Training](https://arxiv.org/abs/2201.05596) —— 共享專家的原始論文。
