# 多頭注意力

> 一個注意力頭一次只學會一種關係。八個頭就學八種。頭是不要錢的，那就多拿幾個。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 02（從零打造自注意力）
**時間：** 約 75 分鐘

## 問題所在

單一個自注意力頭只算出一個注意力矩陣。那個矩陣捕捉一種關係 —— 通常是在當下訓練訊號下最能降低損失的那一種。如果你的資料裡主謂一致、指代關係、長距離篇章結構和句法分塊全糾纏在一起，單一個頭會把它們全抹進同一個 softmax 分布，然後丟掉一半的訊號。

2017 年 Vaswani 論文給的解法：平行跑好幾個注意力函式，每個都有自己的 Q、K、V 投影，再把輸出串接起來。每個注意力頭在維度為 `d_model / n_heads` 的較小子空間中運作。總參數量不變，表達能力上升。

多頭注意力是 2026 年每一個 Transformer 出廠的預設配置。唯一還在爭論的是頭要*幾個*，以及 key 和 value 是否共用投影（分組查詢注意力 GQA、多查詢注意力 MQA、多頭潛在注意力 MLA）。

## 核心概念

![多頭注意力的切分、注意與串接](../assets/multi-head-attention.svg)

**切分。** 拿形狀為 `(N, d_model)` 的 `X`。投影成各為 `(N, d_model)` 的 Q、K、V。重塑為 `(N, n_heads, d_head)`，其中 `d_head = d_model / n_heads`。再轉置成 `(n_heads, N, d_head)`。

**平行注意。** 在每個注意力頭內部跑縮放點積注意力。每個頭產出 `(N, d_head)`。這些頭在嵌入的不同子空間上運作，而且在注意力計算本身的過程中從不互通。

**串接並投影。** 把各頭疊回 `(N, d_model)`，再乘上形狀為 `(d_model, d_model)` 的可學習輸出矩陣 `W_o`。`W_o` 才是各頭互相混合的地方。

**為什麼有效。** 每個頭都能各自專精，不必和其他頭爭搶表示能力的預算。2019 到 2024 年的探測研究顯示出各種明確的頭角色：位置頭、專門注意前一個詞元的頭、複製頭、命名實體頭、歸納頭（in-context learning 的底層機制）。

**2026 年的變體家譜：**

| 變體 | Q 頭數 | K/V 頭數 | 使用者 |
|---------|---------|-----------|---------|
| 多頭（MHA） | N | N | GPT-2、BERT、T5 |
| 多查詢（MQA） | N | 1 | PaLM、Falcon |
| 分組查詢（GQA） | N | G（例如 N/8） | Llama 2 70B、Llama 3+、Qwen 2+、Mistral |
| 多頭潛在（MLA） | N | 壓縮成低秩 | DeepSeek-V2、V3 |

GQA 是現代的預設選擇，因為它把 KV 快取記憶體砍掉 `N/G` 倍，同時幾乎完整保住品質。MLA 走得更遠，把 K/V 壓進一個潛在空間，計算時再投影回來 —— 花掉 FLOP，換來省下更多記憶體。

```figure
multihead-split
```

## 動手實作

### 步驟 1：從我們已有的單頭注意力切出多頭

拿單元 02 的 `SelfAttention`，用一組切分／串接包起來。numpy 實作請看 `code/main.py`，邏輯是：

```python
def split_heads(X, n_heads):
    n, d = X.shape
    d_head = d // n_heads
    return X.reshape(n, n_heads, d_head).transpose(1, 0, 2)  # (heads, n, d_head)

def combine_heads(H):
    h, n, d_head = H.shape
    return H.transpose(1, 0, 2).reshape(n, h * d_head)
```

一次重塑加一次轉置。沒有迴圈。PyTorch 的 `nn.MultiheadAttention` 底下做的就是這件事。

### 步驟 2：每個頭各跑一次縮放點積注意力

每個頭拿到自己那一片 Q、K、V。注意力於是變成一次批次矩陣乘法：

```python
def mha_forward(X, W_q, W_k, W_v, W_o, n_heads):
    Q = X @ W_q
    K = X @ W_k
    V = X @ W_v
    Qh = split_heads(Q, n_heads)         # (heads, n, d_head)
    Kh = split_heads(K, n_heads)
    Vh = split_heads(V, n_heads)
    scores = Qh @ Kh.transpose(0, 2, 1) / np.sqrt(Qh.shape[-1])
    weights = softmax(scores, axis=-1)
    out = weights @ Vh                    # (heads, n, d_head)
    concat = combine_heads(out)
    return concat @ W_o, weights
```

在真實硬體上，`Qh @ Kh.transpose(...)` 就是一次 `bmm`。GPU 看到的是單一次形狀為 `(heads, N, d_head) × (heads, d_head, N) -> (heads, N, N)` 的批次矩陣乘法。加頭是不花錢的。

### 步驟 3：分組查詢注意力變體

只有 key 與 value 的投影會變。Q 拿到 `n_heads` 組；K 和 V 拿到 `n_kv_heads < n_heads` 組，再重複到數量對上：

```python
def gqa_project(X, W, n_kv_heads, n_heads):
    kv = split_heads(X @ W, n_kv_heads)       # (kv_heads, n, d_head)
    repeat = n_heads // n_kv_heads
    return np.repeat(kv, repeat, axis=0)      # (n_heads, n, d_head)
```

推論時這能省記憶體，因為 KV 快取裡活著的只有 `n_kv_heads` 份副本，而不是 `n_heads` 份。Llama 3 70B 用 64 個 query 頭搭配 8 個 KV 頭 —— 快取縮小 8 倍。

### 步驟 4：探測每個頭學到了什麼

拿一個短句用 4 個頭跑一次 MHA。為每個頭印出 `(N, N)` 的注意力矩陣。你會看到即使是隨機初始化，不同的頭仍挑出了不同的結構 —— 這一部分是真訊號，一部分是子空間裡的旋轉對稱性。

## 框架應用

在 PyTorch 裡，一行版：

```python
import torch.nn as nn

mha = nn.MultiheadAttention(embed_dim=512, num_heads=8, batch_first=True)
```

PyTorch 2.5+ 起的 GQA：

```python
from torch.nn.functional import scaled_dot_product_attention

# scaled_dot_product_attention auto-dispatches Flash Attention on CUDA.
# For GQA, pass Q of shape (B, n_heads, N, d_head) and K,V of shape
# (B, n_kv_heads, N, d_head). PyTorch handles the repeat.
out = scaled_dot_product_attention(q, k, v, is_causal=True, enable_gqa=True)
```

**要幾個頭？** 出自 2026 年生產模型的經驗法則：

| 模型規模 | d_model | n_heads | d_head |
|------------|---------|---------|--------|
| 小型（約 125M） | 768 | 12 | 64 |
| 基礎（約 350M） | 1024 | 16 | 64 |
| 大型（約 1B） | 2048 | 16 | 128 |
| 前沿（約 70B） | 8192 | 64 | 128 |

`d_head` 幾乎總是落在 64 或 128。它是「一個頭能看多少」的計量單位。掉到 32 以下，各頭就開始跟縮放因子 `sqrt(d_head)` 打架；超過 256，你就失去了「很多個小專家」帶來的好處。

## 產出交付

請看 `outputs/skill-mha-configurator.md`。這項技能會在給定參數預算、序列長度與部署目標的條件下，為一個新的 Transformer 建議頭數、KV 頭數與投影策略。

## 練習

1. **簡單。** 拿 `code/main.py` 裡的 MHA，固定 `d_model=64`，把 `n_heads` 從 1 改到 16。在一個合成的複製任務上，畫出單層小模型的損失。頭多了是有幫助、持平，還是有害？
2. **中等。** 實作 MQA（所有 query 頭共用一個 KV 頭）。量測參數量相較於完整 MHA 掉了多少。計算在 N=2048 推論時 KV 快取大小縮小了多少。
3. **困難。** 實作一個迷你版的多頭潛在注意力：把 K、V 壓成秩為 `r` 的潛在表示，KV 快取裡存這個潛在表示，注意時再解壓。`r` 要多小，快取記憶體才會低於完整 MHA 的 1/8，同時驗證困惑度的品質仍在 1 bit 之內？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 注意力頭 | 「單一條注意力電路」 | 一組維度為 `d_head = d_model / n_heads` 的 Q/K/V 投影，帶有自己的注意力矩陣。 |
| d_head | 「頭的維度」 | 每個頭的隱藏寬度；在生產環境中幾乎總是 64 或 128。 |
| 切分／串接 | 「重塑的把戲」 | 圍繞注意力的 `(N, d_model) ↔ (n_heads, N, d_head)` 重塑加轉置。 |
| W_o | 「輸出投影」 | 串接各頭之後施加的 `(d_model, d_model)` 矩陣；各頭在此混合。 |
| MQA | 「只有一個 KV 頭」 | 多查詢注意力：單一份共用的 K/V 投影。KV 快取最小，品質略有損失。 |
| GQA | 「Llama 2 之後的預設」 | 分組查詢注意力，`n_kv_heads < n_heads`；重複以對上 Q 的數量。 |
| MLA | 「DeepSeek 的招數」 | 多頭潛在注意力：K、V 壓成低秩潛在表示，注意時再解壓。 |
| 歸納頭 | 「in-context learning 背後的電路」 | 一對能偵測先前出現過的片段、並複製其後續內容的注意力頭。 |

## 延伸閱讀

- [Vaswani et al. (2017). Attention Is All You Need §3.2.2](https://arxiv.org/abs/1706.03762) —— 最初的多頭規格。
- [Shazeer (2019). Fast Transformer Decoding: One Write-Head is All You Need](https://arxiv.org/abs/1911.02150) —— MQA 論文。
- [Ainslie et al. (2023). GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/abs/2305.13245) —— 如何在訓練後把 MHA 轉成 GQA。
- [DeepSeek-AI (2024). DeepSeek-V2 Technical Report](https://arxiv.org/abs/2405.04434) —— MLA，以及它為何在快取記憶體上勝過 MHA／GQA。
- [Olsson et al. (2022). In-context Learning and Induction Heads](https://transformer-circuits.pub/2022/in-context-learning-and-induction-heads/index.html) —— 從機制角度看各頭究竟在做什麼。
