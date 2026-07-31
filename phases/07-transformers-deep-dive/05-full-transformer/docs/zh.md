# 完整的 Transformer —— 編碼器 + 解碼器

> 注意力機制是主角。其他一切 —— 殘差連接、正規化、前饋網路、交叉注意力 —— 都是讓你能把它疊得很深的鷹架。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 02（自注意力）、階段 7 · 03（多頭注意力）、階段 7 · 04（位置編碼）
**時間：** 約 75 分鐘

## 問題所在

單一注意力層是特徵抽取器，不是模型。每層一次矩陣乘法，對語言來說容量遠遠不夠。你需要深度 —— 而缺了正確的管線，深度就會壞掉。

2017 年 Vaswani 那篇論文把六個設計決策打包起來，讓一個注意力層變成可堆疊的區塊。此後每個 Transformer —— 只有編碼器的（BERT）、只有解碼器的（GPT）、編碼器解碼器的（T5）—— 都繼承了同一副骨架。到了 2026 年，區塊內部經過不少改良（RMSNorm、SwiGLU、pre-norm、RoPE），但骨架完全一樣。

本單元講的就是這副骨架。接下來的單元各自把它特化：06 講編碼器，07 講解碼器，08 講編碼器解碼器。

## 核心概念

![編碼器與解碼器區塊的內部構造與接線](../assets/full-transformer.svg)

### 六個組件

1. **嵌入 + 位置訊號。** 詞元 → 向量。位置資訊由 RoPE（現代做法）或正弦函數（經典做法）注入。
2. **自注意力。** 每個位置都關注其他每個位置。在解碼器中會被遮罩。
3. **前饋網路（FFN）。** 逐位置的兩層 MLP：`W_2 · activation(W_1 · x)`。擴張比預設為 4×。
4. **殘差連接。** `x + sublayer(x)`。少了這個，梯度過了約 6 層就會消失。
5. **層正規化。** `LayerNorm` 或 `RMSNorm`（現代做法）。穩定殘差流。
6. **交叉注意力（僅解碼器）。** 查詢來自解碼器，鍵與值來自編碼器輸出。

看著一個向量流過一個區塊：注意力在各位置之間混合資訊，殘差連接把它往前送，前饋網路對它做變換，正規化則讓這道流保持穩定。

```figure
transformer-block
```

### 編碼器區塊（BERT、T5 編碼器採用）

```
x → LN → MHA(self) → + → LN → FFN → + → out
                     ^              ^
                     |              |
                     └── residual ──┘
```

編碼器是雙向的。沒有遮罩。所有位置都看得到所有位置。

### 解碼器區塊（GPT、T5 解碼器採用）

```
x → LN → MHA(masked self) → + → LN → MHA(cross to encoder) → + → LN → FFN → + → out
```

解碼器每個區塊有三個子層。中間那個 —— 交叉注意力 —— 是資訊從編碼器流向解碼器的唯一通道。在純粹只有解碼器的架構（GPT）中，交叉注意力被省略，只剩下遮罩自注意力 + 前饋網路。

### pre-norm 與 post-norm

原始論文的兩種寫法：`x + sublayer(LN(x))` 對比 `LN(x + sublayer(x))`。post-norm 大約在 2019 年失寵 —— 沒有仔細設計的 warmup，它很難訓練得深。pre-norm（`LN` 放在子層*之前*）是 2026 年的預設：Llama、Qwen、GPT-3 以後、Mistral 全都採用。

### 2026 年的現代化區塊

Vaswani 2017 交付的是 LayerNorm + ReLU。現代的技術堆疊把兩者都換掉了。生產環境的區塊實際上長這樣：

| 組件 | 2017 | 2026 |
|-----------|------|------|
| 正規化 | LayerNorm | RMSNorm |
| 前饋網路激活函數 | ReLU | SwiGLU |
| 前饋網路擴張比 | 4× | 2.6×（SwiGLU 用三個矩陣，總參數量相當） |
| 位置 | 正弦絕對位置 | RoPE |
| 注意力 | 完整 MHA | GQA（或 MLA） |
| 偏差項 | 有 | 無 |

RMSNorm 捨棄了 LayerNorm 的減去均值步驟（少一次減法），省下運算量，而經驗上至少一樣穩定。在 Llama、PaLM 與 Qwen 的論文裡，SwiGLU（`Swish(W1 x) ⊙ W3 x`）在困惑度上都穩定勝過 ReLU／GELU 前饋網路約 0.5 點。

### 參數量

對一個 `d_model = d`、前饋網路擴張比為 `r` 的區塊：

- MHA：`4 · d²`（Q、K、V、O 投影）
- 前饋網路（SwiGLU）：`3 · d · (r · d)` ≈ `3rd²`
- 各正規化層：可忽略

在 `d = 4096, r = 2.6, layers = 32`（大致是 Llama 3 8B）的設定下，總計：`32 · (4·4096² + 3·2.6·4096²) ≈ 32 · (16 + 32) M = ~1.5B parameters per layer × 32 ≈ 7B`（再加上嵌入層與輸出頭）。與公布的參數量相符。

## 動手實作

### 步驟 1：建構元件

使用單元 03 那個極小的 `Matrix` 類別（為了讓本檔案自成一體而複製過來）：

- `layer_norm(x, eps=1e-5)` —— 減去均值，除以標準差。
- `rms_norm(x, eps=1e-6)` —— 除以 RMS。不減均值。
- `gelu(x)` 以及 `silu(x) * W3 x`（SwiGLU）。
- `ffn_swiglu(x, W1, W2, W3)`。
- `encoder_block(x, params)` 與 `decoder_block(x, enc_out, params)`。

完整接線請看 `code/main.py`。

### 步驟 2：接出一個 2 層編碼器與一個 2 層解碼器

把它們疊起來。把編碼器輸出餵給每一層解碼器的交叉注意力。在輸出投影之前加上最後一層 LN。

```python
def encode(tokens, params):
    x = embed(tokens, params.emb) + sinusoidal(len(tokens), params.d)
    for block in params.encoder_blocks:
        x = encoder_block(x, block)
    return x

def decode(target_tokens, encoder_out, params):
    x = embed(target_tokens, params.emb) + sinusoidal(len(target_tokens), params.d)
    for block in params.decoder_blocks:
        x = decoder_block(x, encoder_out, block)
    return x
```

### 步驟 3：在一個玩具範例上跑前向傳播

餵進一個 6 個詞元的來源序列與一個 5 個詞元的目標序列。驗證輸出形狀是 `(5, vocab)`。不做訓練 —— 本單元談的是架構，不是損失函式。

### 步驟 4：換成 RMSNorm + SwiGLU

把 LayerNorm 與 ReLU 前饋網路換成 RMSNorm 與 SwiGLU。確認形狀依然對得上。這就是 2026 年的現代化，只需替換一個函式。

## 框架應用

PyTorch／TF 的參考實作：`nn.TransformerEncoderLayer`、`nn.TransformerDecoderLayer`。但 2026 年大多數生產程式碼都自己寫區塊，原因是：

- Flash Attention 是在注意力內部呼叫的，不是透過 `nn.MultiheadAttention`。
- GQA／MLA 不在標準參考實作裡。
- RoPE、RMSNorm、SwiGLU 都不是 PyTorch 的預設。

HF `transformers` 有幾份乾淨的參考區塊值得一讀：`modeling_llama.py` 是 2026 年只有解碼器架構的典範區塊。約 500 行，值得完整走過一次。

**編碼器、解碼器、編碼器解碼器 —— 該怎麼選：**

| 需求 | 選擇 | 範例 |
|------|------|---------|
| 分類、嵌入、對文本做問答 | 只有編碼器 | BERT、DeBERTa、ModernBERT |
| 文字生成、聊天、程式碼、推理 | 只有解碼器 | GPT、Llama、Claude、Qwen |
| 結構化輸入 → 結構化輸出（翻譯、摘要） | 編碼器解碼器 | T5、BART、Whisper |

只有解碼器的架構贏下了語言這一局，因為它擴展起來最乾淨，而且理解與生成都能處理。當輸入具有明確的「來源序列」身分時（翻譯、語音辨識、結構化任務），編碼器解碼器仍是最佳選擇。

## 產出交付

請看 `outputs/skill-transformer-block-reviewer.md`。這項技能會拿 2026 年的預設做法檢視一份新的 Transformer 區塊實作，並標出缺漏的部分（pre-norm、RoPE、RMSNorm、GQA、前饋網路擴張比）。

## 練習

1. **簡單。** 計算你的 encoder_block 在 `d_model=512, n_heads=8, ffn_expansion=4, swiglu=True` 下的參數量。實作該區塊並用 `sum(p.numel() for p in block.parameters())` 驗證。
2. **中等。** 從 post-norm 改成 pre-norm。兩者都初始化，並在隨機輸入上量測疊了 12 層之後的激活值範數。post-norm 的激活值應該會爆掉；pre-norm 應該維持有界。
3. **困難。** 在一個玩具複製任務上（把 `x` 反轉後複製）實作一個 4 層的編碼器解碼器。訓練 100 步。報告損失。再換成 RMSNorm + SwiGLU + RoPE —— 損失有下降嗎？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 區塊 | 「一層 Transformer」 | 正規化 + 注意力 + 正規化 + 前饋網路的組合，外面包上殘差連接。 |
| 殘差 | 「跳接」 | 輸出為 `x + f(x)`；讓梯度能穿過很深的堆疊。 |
| pre-norm | 「正規化放前面，不放後面」 | 現代做法：`x + sublayer(LN(x))`。不必玩 warmup 特技就能訓練得更深。 |
| RMSNorm | 「不減均值的 LayerNorm」 | 除以 RMS；少一個運算，經驗上一樣穩定。 |
| SwiGLU | 「大家都換過去的那個前饋網路」 | `Swish(W1 x) ⊙ W3 x → W2`。在語言模型困惑度上勝過 ReLU／GELU。 |
| 交叉注意力 | 「解碼器怎麼看見編碼器」 | Q 來自解碼器、K／V 來自編碼器輸出的 MHA。 |
| 前饋網路擴張比 | 「中間那層 MLP 有多寬」 | 隱藏層維度對 d_model 的比值，通常是 4（LayerNorm）或 2.6（SwiGLU）。 |
| 無偏差項 | 「把 +b 項去掉」 | 現代堆疊在線性層省略偏差項；困惑度略有改善，模型也更小。 |

## 延伸閱讀

- [Vaswani et al. (2017). Attention Is All You Need](https://arxiv.org/abs/1706.03762) —— 原始的區塊規格。
- [Xiong et al. (2020). On Layer Normalization in the Transformer Architecture](https://arxiv.org/abs/2002.04745) —— 為什麼在深層網路裡 pre-norm 勝過 post-norm。
- [Zhang, Sennrich (2019). Root Mean Square Layer Normalization](https://arxiv.org/abs/1910.07467) —— RMSNorm。
- [Shazeer (2020). GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202) —— SwiGLU 那篇論文。
- [HuggingFace `modeling_llama.py`](https://github.com/huggingface/transformers/blob/main/src/transformers/models/llama/modeling_llama.py) —— 2026 年只有解碼器架構的典範區塊。
