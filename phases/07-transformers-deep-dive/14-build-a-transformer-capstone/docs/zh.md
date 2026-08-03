# 從零打造一個 Transformer —— 總結專案

> 十三個單元。一個模型。沒有捷徑。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 01 至 13（從「為什麼要用 Transformer」到「縮放律」），別跳過。
**時間：** 約 120 分鐘

## 問題所在

論文你都讀過了。注意力、多頭切分、位置編碼、編碼器與解碼器區塊、BERT 與 GPT 的損失、MoE、KV 快取，你也都實作過了。現在要讓它們在一個真實任務上一起運作。

這個總結專案：端到端訓練一個小型的僅解碼器 transformer，做字元級語言建模。它讀莎士比亞，然後生成新的莎士比亞。它小到能在筆電上 10 分鐘內訓練完，也正確到只要換上更大的資料集、訓練更久，就能得到一個真正的語言模型。

這是本課程的「nanoGPT」。它並不原創 —— Karpathy 2023 年的 nanoGPT 教學，是每個學生至少會親手寫一次的參考實作。我們沿用它的骨架，再依我們涵蓋過的內容重新配裝。

## 核心概念

![從零打造 Transformer 的架構方塊圖](../assets/capstone.svg)

架構，附註解：

```
input tokens (B, N)
   │
   ▼
token embedding + positional embedding  ◀── Lesson 04 (RoPE option)
   │
   ▼
┌──── block × L ────────────────────┐
│  RMSNorm                          │  ◀── Lesson 05
│  MultiHeadAttention (causal)      │  ◀── Lesson 03 + 07 (causal mask)
│  residual                         │
│  RMSNorm                          │
│  SwiGLU FFN                       │  ◀── Lesson 05
│  residual                         │
└────────────────────────────────── ┘
   │
   ▼
final RMSNorm
   │
   ▼
lm_head (tied to token embedding)
   │
   ▼
logits (B, N, V)
   │
   ▼
shift-by-one cross-entropy            ◀── Lesson 07
```

### 我們會交付什麼

- `GPTConfig` —— 所有超參數集中在一個地方設定。
- `MultiHeadAttention` —— 因果、批次化，並提供可選的 Flash 風格路徑（PyTorch 的 `scaled_dot_product_attention`）。
- `SwiGLUFFN` —— 現代版的前饋網路。
- `Block` —— 前置正規化，注意力 + FFN 都包在殘差裡。
- `GPT` —— 嵌入層、堆疊的區塊、LM head、generate()。
- 訓練迴圈：AdamW、cosine 學習率、梯度裁剪。
- 針對莎士比亞文本的字元級分詞器。

### 我們不會交付什麼

- RoPE —— 概念上已在單元 04 實作過。這裡為了簡單，改用學習式的位置嵌入。練習會要你換成 RoPE。
- 生成時的 KV 快取 —— 每一步生成都對整段前綴重算注意力。比較慢，但比較單純。練習會要你加上 KV 快取。
- Flash Attention —— PyTorch 2.0+ 在輸入條件符合時會自動分派；我們用 `F.scaled_dot_product_attention`。
- MoE —— 每個區塊只有一個 FFN。MoE 你已經在單元 11 看過了。

### 目標指標

在一台 Mac M2 筆電上，一個 4 層、4 個頭、d_model=128 的 GPT，在 `tinyshakespeare.txt` 上訓練 2,000 步：

- 訓練損失在大約 6 分鐘內，從約 4.2（隨機初始）收斂到約 1.5。
- 取樣輸出長得有莎士比亞的形狀：古語詞彙、換行，以及像「ROMEO:」這樣的人名開始出現。
- 驗證損失（保留最後 10% 的文本）緊跟著訓練損失；在這個規模與預算下不會過度擬合。

```figure
n5-block-stack
```

## 動手實作

本單元使用 PyTorch。請安裝 `torch`（CPU 版即可）。請看 `code/main.py`。這支腳本會處理：

- 若 `tinyshakespeare.txt` 不存在就下載它（或讀取本機副本）。
- 位元組層級的字元分詞器。
- 訓練／驗證以 90/10 切分。
- 在支援的硬體上以 bf16 autocast 執行訓練迴圈。
- 訓練結束後取樣。

### 步驟 1：資料

```python
text = open("tinyshakespeare.txt").read()
chars = sorted(set(text))
stoi = {c: i for i, c in enumerate(chars)}
itos = {i: c for c, i in stoi.items()}
encode = lambda s: [stoi[c] for c in s]
decode = lambda xs: "".join(itos[x] for x in xs)
```

65 個不重複字元。詞彙表極小，4 個位元組的 vocab_size 就裝得下。沒有 BPE，也沒有分詞器的那些麻煩。

### 步驟 2：模型

請看 `code/main.py`。區塊就是單元 05 的教科書版本 —— 前置正規化、RMSNorm、SwiGLU、因果多頭注意力。4/4/128 的參數量約為 80 萬。

### 步驟 3：訓練迴圈

隨機取一批長度 256 的詞元視窗。前向傳播。位移一格的交叉熵。反向傳遞。AdamW 更新一步。記錄。重複。

```python
for step in range(max_steps):
    x, y = get_batch("train")
    logits = model(x)
    loss = F.cross_entropy(logits.view(-1, vocab_size), y.view(-1))
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    opt.zero_grad()
```

### 步驟 4：取樣

給一段提示詞，反覆做前向傳播、從 top-p 的 logits 取樣、接到後面，然後繼續。生成 500 個詞元後停止。

### 步驟 5：讀輸出

跑完 2,000 步之後：

```
ROMEO:
Away and mild will not thy friend, that thou shalt wit:
The chief that well shame and hath been his friends,
...
```

不是莎士比亞。但有莎士比亞的形狀。對約 80 萬參數、筆電上 6 分鐘的訓練來說，這是明顯的勝利。

## 框架應用

這個總結專案是一份參考架構。要把它推到真正有用的東西，有三個延伸方向：

1. **換掉分詞器。** 改用 BPE（例如 `tiktoken.get_encoding("cl100k_base")`）。詞彙表大小從 65 跳到約 50,000，模型容量得跟著放大來補償。
2. **在更大的語料上訓練。** 用 `OpenWebText` 或 `fineweb-edu`（HuggingFace）。一個 1.25 億參數的 GPT，在單張 A100 上吃 100 億詞元約需 24 小時。
3. **加上 RoPE + KV 快取 + Flash Attention。** 下面的練習會一步步帶你做完。

這樣最後會得到一個 1.25 億參數、能生成通順英文的 GPT。它不是前沿模型。但同一條程式碼路徑 —— 只是規模放大 —— 就是 Karpathy、EleutherAI 與 Allen Institute 在 2026 年訓練研究檢查點時用的東西。

## 產出交付

請看 `outputs/skill-transformer-review.md`。這項技能會針對前面 13 個單元的所有要點，檢查一份從零打造的 transformer 實作是否正確。

## 練習

1. **簡單。** 執行 `code/main.py`。確認你訓練出的模型在最後一步的驗證損失低於 2.0。把 `max_steps` 從 2,000 改成 5,000 —— 驗證損失還會繼續下降嗎？
2. **中等。** 把學習式的位置嵌入換成 RoPE。在 `MultiHeadAttention` 內部對 Q 與 K 施加旋轉。訓練並確認驗證損失至少一樣低。
3. **中等。** 在取樣迴圈裡實作 KV 快取。分別在有快取與沒快取的情況下生成 500 個詞元。在筆電上牆鐘時間應該會改善 5 到 20 倍。
4. **困難。** 為模型加上第二個頭，用來預測「下一個的下一個」詞元（MTP —— 出自 DeepSeek-V3 的多詞元預測）。一起聯合訓練。這樣有幫助嗎？
5. **困難。** 把每個區塊裡單一的 FFN 換成 4 個專家的 MoE，加上路由器與 top-2 路由。在活躍參數量相同的條件下，看驗證損失怎麼變。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| nanoGPT | 「Karpathy 的教學儲存庫」 | 極簡的僅解碼器 transformer 訓練程式碼，約 300 行；標準參考實作。 |
| tinyshakespeare | 「標準的玩具語料」 | 約 1.1 MB 的文本；2015 年以來每一份字元級語言模型教學都用它。 |
| 綁定嵌入 | 「共用輸入／輸出矩陣」 | LM head 的權重 = 詞元嵌入矩陣的轉置；省參數，也提升品質。 |
| bf16 autocast | 「訓練精度的把戲」 | 前向與反向用 bf16 跑，最佳化器狀態留在 fp32；2021 年起的標準做法。 |
| 梯度裁剪 | 「壓住爆衝」 | 把全域梯度範數上限設在 1.0；避免訓練炸掉。 |
| cosine 學習率排程 | 「2020 年後的預設」 | 學習率先線性爬升（warmup），再以餘弦形狀衰減到峰值的 10%。 |
| MFU | 「模型 FLOP 利用率」 | 實際達到的 FLOPs／理論峰值；2026 年密集模型 40%、MoE 30% 算是很好。 |
| 驗證損失 | 「保留集上的損失」 | 在模型沒看過的資料上算交叉熵；過度擬合的偵測器。 |

## 延伸閱讀

- [The Annotated Transformer (Harvard NLP)](https://nlp.seas.harvard.edu/annotated-transformer/) —— 經典的逐段註解實作。
