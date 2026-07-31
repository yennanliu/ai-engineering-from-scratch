# 注意力機制 —— 那個突破

> 解碼器不再瞇著眼盯著一份壓縮過的摘要，而是開始直接看整段原文。這之後的一切，都是注意力加上工程。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 09（Sequence-to-Sequence 模型）
**時間：** 約 45 分鐘

## 問題所在

單元 09 收在一次量測得出的失敗上。一個 GRU 編碼器－解碼器在玩具複製任務上訓練，長度 5 時準確率 89%，長度 80 時掉到接近亂猜。原因是結構性的，不是訓練出了 bug：編碼器蒐集到的每一分資訊，都得塞進一個固定大小的隱藏狀態裡，而解碼器除此之外什麼也看不到。

Bahdanau、Cho 與 Bengio 在 2014 年發表了一個三行的修法。別只把最後一個編碼器狀態交給解碼器，而是把每一個編碼器狀態都留著。在每一個解碼步驟，計算編碼器狀態的加權平均，權重代表「解碼器此刻需要看編碼器位置 `i` 多少？」那個加權平均就是上下文，而且它每一個解碼步驟都在變。

整個想法就這樣。Transformer 把它擴展開來。自注意力把它用在單一序列上。多頭注意力把它平行地跑好幾份。但 2014 年的版本已經打破了瓶頸，一旦你掌握了它，轉向 Transformer 就只是工程，不再是觀念上的躍進。

## 核心概念

![Bahdanau 注意力：解碼器對所有編碼器狀態發出 query](../assets/attention.svg)

在每一個解碼步驟 `t`：

1. 把前一個解碼器隱藏狀態 `s_{t-1}` 當成 **query**。
2. 拿它去對每一個編碼器隱藏狀態 `h_1, ..., h_T` 打分。每個編碼器位置得到一個純量。
3. 對這些分數取 softmax，得到總和為 1 的注意力權重 `α_{t,1}, ..., α_{t,T}`。
4. 上下文向量 `c_t = Σ α_{t,i} * h_i`。編碼器狀態的加權平均。
5. 解碼器接收 `c_t` 加上前一個輸出詞元，產生下一個詞元。

重點在那個加權平均。當解碼器需要把「Je」譯成「I」時，它會把「Je」上頭的編碼器狀態權重拉高，其餘壓低。當它需要「not」時，就把「pas」的權重拉高。上下文向量每一步都重新塑形。

## 形狀（每個人都被咬過的地方）

這是每一份注意力實作第一次寫都會出錯的地方。慢慢讀。

| 項目 | 形狀 | 備註 |
|-------|-------|-------|
| 編碼器隱藏狀態 `H` | `(T_enc, d_h)` | 若是 BiLSTM，`d_h = 2 * d_hidden` |
| 解碼器隱藏狀態 `s_{t-1}` | `(d_s,)` | 單一向量 |
| 注意力分數 `e_{t,i}` | 純量 | 每個編碼器位置一個 |
| 注意力權重 `α_{t,i}` | 純量 | 對所有 `i` 取 softmax 之後 |
| 上下文向量 `c_t` | `(d_h,)` | 與一個編碼器狀態同形狀 |

**Bahdanau（加性）分數。** `e_{t,i} = v_α^T * tanh(W_a * s_{t-1} + U_a * h_i)`。

- `s_{t-1}` 的形狀是 `(d_s,)`，`h_i` 的形狀是 `(d_h,)`。
- `W_a` 的形狀是 `(d_attn, d_s)`。`U_a` 的形狀是 `(d_attn, d_h)`。
- tanh 裡面那個和的形狀是 `(d_attn,)`。
- `v_α` 的形狀是 `(d_attn,)`。與 `v_α` 做內積就塌縮成一個純量。**`v_α` 做的就是這件事。** 它不是什麼魔法，它就是把一個注意力維度的向量投影成純量分數的那道投影。

**Luong（乘性）分數。** 三種變體：

- `dot`：`e_{t,i} = s_t^T * h_i`。要求 `d_s == d_h`。這是硬限制。如果你的編碼器是雙向的，就跳過它。
- `general`：`e_{t,i} = s_t^T * W * h_i`，`W` 的形狀是 `(d_s, d_h)`。解除了維度必須相等的限制。
- `concat`：本質上就是 Bahdanau 的形式。很少用，因為前兩者更便宜。

**有一個 Bahdanau／Luong 的坑值得點名。** Bahdanau 用 `s_{t-1}`（產生當前詞*之前*的解碼器狀態）。Luong 用 `s_t`（*之後*的狀態）。搞混會產生細微錯誤的梯度，而且極難除錯。挑定一篇論文，就守著它的慣例。

```figure
attention-heatmap
```

## 動手實作

### 步驟 1：加性（Bahdanau）注意力

```python
import numpy as np


def additive_attention(decoder_state, encoder_states, W_a, U_a, v_a):
    projected_dec = W_a @ decoder_state
    projected_enc = encoder_states @ U_a.T
    combined = np.tanh(projected_enc + projected_dec)
    scores = combined @ v_a
    weights = softmax(scores)
    context = weights @ encoder_states
    return context, weights


def softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / e.sum()
```

拿上面那張表核對你的形狀。`encoder_states` 的形狀是 `(T_enc, d_h)`。`projected_enc` 的形狀是 `(T_enc, d_attn)`。`projected_dec` 的形狀是 `(d_attn,)`，會被廣播。`combined` 的形狀是 `(T_enc, d_attn)`。`scores` 的形狀是 `(T_enc,)`。`weights` 的形狀是 `(T_enc,)`。`context` 的形狀是 `(d_h,)`。可以出貨了。

### 步驟 2：Luong 的 dot 與 general

```python
def dot_attention(decoder_state, encoder_states):
    scores = encoder_states @ decoder_state
    weights = softmax(scores)
    return weights @ encoder_states, weights


def general_attention(decoder_state, encoder_states, W):
    projected = W.T @ decoder_state
    scores = encoder_states @ projected
    weights = softmax(scores)
    return weights @ encoder_states, weights
```

各三行。這就是 Luong 那篇論文站得住腳的原因。在大多數任務上準確率相同，程式碼少得多。

### 步驟 3：一個算過的數值範例

給定三個編碼器狀態（大致對應「cat」、「sat」、「mat」）以及一個與第一個最為對齊的解碼器狀態，注意力分布會集中在位置 0。如果把解碼器狀態改成與最後一個對齊，注意力就移到位置 2。上下文向量跟著跑。

```python
H = np.array([
    [1.0, 0.0, 0.2],
    [0.5, 0.5, 0.1],
    [0.1, 0.9, 0.3],
])

s_close_to_cat = np.array([0.9, 0.1, 0.2])
ctx, w = dot_attention(s_close_to_cat, H)
print("weights:", w.round(3))
```

```
weights: [0.464 0.305 0.231]
```

第一列勝出。接著把解碼器狀態移得靠近第三個編碼器狀態，看權重怎麼位移。就是這樣。注意力就是明確的對齊。

### 步驟 4：為什麼這是通往 Transformer 的橋

把上面那套語言翻成 Q/K/V：

- **Query** = 解碼器狀態 `s_{t-1}`
- **Key** = 編碼器狀態（我們拿來打分的對象）
- **Value** = 編碼器狀態（我們加權求和的對象）

在古典注意力裡，key 與 value 是同一個東西。自注意力把兩者分開：你可以讓一段序列對自己發出 query，而 K 與 V 各有不同的學習投影。多頭注意力則用不同的學習投影平行跑好幾份。Transformer 把整個階段堆疊許多次，並丟掉 RNN。

數學是一樣的。形狀是一樣的。從 Bahdanau 注意力跳到縮放點積注意力，教學上的落差主要只是符號。

## 框架應用

PyTorch 與 TensorFlow 都直接內建注意力。

```python
import torch
import torch.nn as nn

mha = nn.MultiheadAttention(embed_dim=128, num_heads=8, batch_first=True)
query = torch.randn(2, 5, 128)
key = torch.randn(2, 10, 128)
value = torch.randn(2, 10, 128)

output, weights = mha(query, key, value)
print(output.shape, weights.shape)
```

```
torch.Size([2, 5, 128]) torch.Size([2, 5, 10])
```

那就是一層 Transformer 注意力。query 這批有 5 個位置，key／value 這批有 10 個位置，各 128 維，8 個頭。`output` 是補進了上下文的新 query。`weights` 是那個 5x10 的對齊矩陣，可以拿來視覺化。

### 古典注意力何時仍然重要

- 教學。單頭、單層、以 RNN 為底的版本讓每個概念都看得見。
- 裝置端的序列任務，Transformer 塞不進去的場合。
- 2014 到 2017 年間的任何論文。不知道 Bahdanau 的慣例，你就會讀錯。
- 機器翻譯裡的細粒度對齊分析。即使在 Transformer 模型上，原始注意力權重仍是一種可解釋性工具，而要讀懂它們，得先知道它們是什麼。

### 「注意力權重當解釋」的陷阱

注意力權重看起來很可解釋。它們是跨位置總和為一的權重；你可以畫出來；數值高就代表「看了這裡」。審稿人很愛。

它們並沒有看起來那麼可解釋。Jain 與 Wallace（2019）指出，在某些任務上，注意力分布可以被置換、被任意替代方案取代，而模型預測毫無改變。沒有做過消融或反事實檢查之前，絕對不要把注意力權重當成推論過程的證據來報告。

## 產出交付

存成 `outputs/prompt-attention-shapes.md`：

```markdown
---
name: attention-shapes
description: Debug shape bugs in attention implementations.
phase: 5
lesson: 10
---

Given a broken attention implementation, you identify the shape mismatch. Output:

1. Which matrix has the wrong shape. Name the tensor.
2. What its shape should be, derived from (d_s, d_h, d_attn, T_enc, T_dec, batch_size).
3. One-line fix. Transpose, reshape, or project.
4. A test to catch regressions. Typically: assert `output.shape == (batch, T_dec, d_h)` and `weights.shape == (batch, T_dec, T_enc)` and `weights.sum(dim=-1) close to 1`.

Refuse to recommend fixes that silently broadcast. Broadcast-hiding bugs surface later as silent accuracy degradation, the worst kind of attention bug.

For Bahdanau confusion, insist the decoder input is `s_{t-1}` (pre-step state). For Luong, `s_t` (post-step state). For dot-product, flag dimension mismatch between query and key as the most common first-time error.
```

## 練習

1. **簡單。** 實作 `softmax` 遮罩，讓編碼器裡的填充詞元拿到的注意力權重為零。在一批長度不一的序列上測試。
2. **中等。** 為 Luong 的 `general` 形式加上多頭注意力。把 `d_h` 切成 `n_heads` 組，每個頭各跑一次注意力，再串接起來。驗證單頭的情況與你先前的實作結果相同。
3. **困難。** 在單元 09 的玩具複製任務上，訓練一個帶 Bahdanau 注意力的 GRU 編碼器－解碼器。畫出準確率對序列長度的曲線。與沒有注意力的基準線比較。你應該會看到差距隨長度增長而拉大，這印證了注意力解除了瓶頸。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 注意力 | 「去看東西」 | 對一串 value 取加權平均，權重由 query 與 key 的相似度算出。 |
| Query、Key、Value | QKV | 三道投影：Q 負責問，K 是拿來比對的東西，V 是要回傳的東西。 |
| 加性注意力 | Bahdanau | 前饋式的分數：`v^T tanh(W q + U k)`。 |
| 乘性注意力 | Luong 的 dot／general | 分數是 `q^T k` 或 `q^T W k`。更便宜，在大多數任務上準確率相同。 |
| 對齊矩陣 | 「那張漂亮的圖」 | 把注意力權重排成 `(T_dec, T_enc)` 的網格。讀它就能看出模型注意了什麼。 |

## 延伸閱讀

- [Bahdanau, Cho, Bengio (2014). Neural Machine Translation by Jointly Learning to Align and Translate](https://arxiv.org/abs/1409.0473) —— 就是那篇論文。
- [Luong, Pham, Manning (2015). Effective Approaches to Attention-based Neural Machine Translation](https://arxiv.org/abs/1508.04025) —— 三種分數變體及其比較。
- [Jain and Wallace (2019). Attention is not Explanation](https://arxiv.org/abs/1902.10186) —— 可解釋性的那道警告。
- [Dive into Deep Learning — Bahdanau Attention](https://d2l.ai/chapter_attention-mechanisms-and-transformers/bahdanau-attention.html) —— 可執行的 PyTorch 逐步導覽。
