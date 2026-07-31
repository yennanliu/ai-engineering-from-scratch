# 序列到序列模型

> 兩個 RNN 假扮成一台翻譯機。它們撞上的那道瓶頸，就是注意力機制存在的理由。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 08（用於文字的 CNN 與 RNN）、階段 3 · 11（PyTorch 入門）
**時間：** 約 75 分鐘

## 問題所在

分類是把一個變長序列映射到單一標籤。翻譯是把一個變長序列映射到另一個變長序列。輸入與輸出活在不同的詞彙表裡，可能是不同語言，長度也不保證一致。

序列到序列（seq2seq）架構（Sutskever, Vinyals, Le, 2014）用一套刻意簡單的配方破了這個題。兩個 RNN。一個讀來源句子，產生一個固定大小的上下文向量。另一個讀這個向量，逐個詞元生成目標句子。程式碼和你在單元 08 寫的一樣，只是黏法不同。

這件事值得研究，有兩個理由。第一，上下文向量的瓶頸是 NLP 裡教學價值最高的一次失敗。注意力機制與 Transformer 擅長的一切，動機都來自它。第二，這套訓練配方（teacher forcing、scheduled sampling、推論時用 beam search）到今天仍適用於每一個現代生成系統，包括 LLM。

## 核心概念

**編碼器。** 一個讀來源句子的 RNN。它最後的隱藏狀態就是**上下文向量** —— 整段輸入的固定大小摘要。理論上，除了來源本身，什麼都沒漏掉。

**解碼器。** 另一個 RNN，用上下文向量初始化。每一步它接收上一個生成的詞元作為輸入，輸出目標詞彙表上的一個機率分布。用取樣或 argmax 挑出下一個詞元，再餵回去。重複到產生 `<EOS>` 詞元或碰到最大長度為止。

**訓練：** 每個解碼器步驟算交叉熵損失，沿序列加總。兩個網路都走標準的隨時間反向傳播。

**Teacher forcing。** 訓練期間，解碼器在第 `t` 步的輸入是位置 `t-1` 的*真實*詞元，而不是解碼器自己上一步的預測。這能穩定訓練；少了它，早期的錯誤會層層放大，模型永遠學不起來。推論時你只能用模型自己的預測，所以訓練與推論之間永遠存在分布落差。這道落差叫做**曝光偏差**。

**瓶頸。** 編碼器對來源學到的一切，都得壓進那一個上下文向量裡。長句子會流失細節。罕見詞會被模糊掉。語序重排（chat noir 對 black cat）只能靠記憶，不能靠計算。

注意力機制（單元 10）直接修掉這件事：讓解碼器看得到*每一個*編碼器隱藏狀態，而不只是最後一個。整套賣點就是這樣。

```figure
lstm-gates
```

## 動手實作

### 步驟 1：一個編碼器

```python
import torch
import torch.nn as nn


class Encoder(nn.Module):
    def __init__(self, src_vocab_size, embed_dim, hidden_dim):
        super().__init__()
        self.embed = nn.Embedding(src_vocab_size, embed_dim, padding_idx=0)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)

    def forward(self, src):
        e = self.embed(src)
        outputs, hidden = self.gru(e)
        return outputs, hidden
```

`outputs` 的形狀是 `[batch, seq_len, hidden_dim]` —— 每個輸入位置一個隱藏狀態。`hidden` 的形狀是 `[1, batch, hidden_dim]` —— 最後一步。單元 08 說的是「做分類時對 outputs 池化」。這裡我們把最後的隱藏狀態留下來當上下文向量，忽略逐步的 outputs。

### 步驟 2：一個解碼器

```python
class Decoder(nn.Module):
    def __init__(self, tgt_vocab_size, embed_dim, hidden_dim):
        super().__init__()
        self.embed = nn.Embedding(tgt_vocab_size, embed_dim, padding_idx=0)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, tgt_vocab_size)

    def forward(self, token, hidden):
        e = self.embed(token)
        out, hidden = self.gru(e, hidden)
        logits = self.fc(out)
        return logits, hidden
```

解碼器一次只呼叫一步。輸入：一批單一詞元，以及當前的隱藏狀態。輸出：下一個詞元的詞彙表 logits，以及更新後的隱藏狀態。

### 步驟 3：帶 teacher forcing 的訓練迴圈

```python
def train_batch(encoder, decoder, src, tgt, bos_id, optimizer, teacher_forcing_ratio=0.9):
    optimizer.zero_grad()
    _, hidden = encoder(src)
    batch_size, tgt_len = tgt.shape
    input_token = torch.full((batch_size, 1), bos_id, dtype=torch.long)
    loss = 0.0
    loss_fn = nn.CrossEntropyLoss(ignore_index=0)

    for t in range(tgt_len):
        logits, hidden = decoder(input_token, hidden)
        step_loss = loss_fn(logits.squeeze(1), tgt[:, t])
        loss += step_loss
        use_teacher = torch.rand(1).item() < teacher_forcing_ratio
        if use_teacher:
            input_token = tgt[:, t].unsqueeze(1)
        else:
            input_token = logits.argmax(dim=-1)

    loss.backward()
    optimizer.step()
    return loss.item() / tgt_len
```

有兩個旋鈕值得點名。`ignore_index=0` 讓填補詞元不計入損失。`teacher_forcing_ratio` 是每一步採用真實詞元（而非模型預測）的機率。從 1.0 開始（完整的 teacher forcing），在訓練過程中逐步退火到大約 0.5，用來收斂曝光偏差造成的落差。

### 步驟 4：推論迴圈（貪婪解碼）

```python
@torch.no_grad()
def greedy_decode(encoder, decoder, src, bos_id, eos_id, max_len=50):
    _, hidden = encoder(src)
    batch_size = src.shape[0]
    input_token = torch.full((batch_size, 1), bos_id, dtype=torch.long)
    output_ids = []
    for _ in range(max_len):
        logits, hidden = decoder(input_token, hidden)
        next_token = logits.argmax(dim=-1)
        output_ids.append(next_token)
        input_token = next_token
        if (next_token == eos_id).all():
            break
    return torch.cat(output_ids, dim=1)
```

貪婪解碼在每一步都挑機率最高的詞元。它可能一路走偏：一旦你認定了某個詞元，就沒辦法收回。**Beam search** 會同時保留分數最高的 `k` 條部分序列，最後挑出分數最高的完整序列。beam 寬度 3-5 是標準做法。

### 步驟 5：把瓶頸示範出來

拿一個玩具複製任務來訓練模型：來源 `[a, b, c, d, e]`，目標 `[a, b, c, d, e]`。逐步加長序列。觀察準確率。

```
seq_len=5   copy accuracy: 98%
seq_len=10  copy accuracy: 91%
seq_len=20  copy accuracy: 62%
seq_len=40  copy accuracy: 23%
```

單一個 GRU 隱藏狀態沒辦法無損記住一段 40 個詞元的輸入。資訊在每個編碼器步驟都存在，但解碼器只看到最後一個狀態。注意力機制直接解決了這點。

## 框架應用

PyTorch 有 `nn.Transformer`，也有基於 `nn.LSTM` 的 seq2seq 樣板。Hugging Face 的 `transformers` 函式庫則直接提供在數十億詞元上訓練好的完整編碼器解碼器模型（BART、T5、mBART、NLLB）。

```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

tok = AutoTokenizer.from_pretrained("facebook/bart-base")
model = AutoModelForSeq2SeqLM.from_pretrained("facebook/bart-base")

src = tok("Translate this to French: Hello, how are you?", return_tensors="pt")
out = model.generate(**src, max_new_tokens=50, num_beams=4)
print(tok.decode(out[0], skip_special_tokens=True))
```

現代的編碼器解碼器已經棄用 RNN，換成 Transformer。但高層形狀（編碼器、解碼器、逐詞元生成）和 2014 年那篇 seq2seq 論文一模一樣。不同的是每個區塊內部的機制。

### 什麼時候還會去找基於 RNN 的 seq2seq

新專案幾乎不會。少數例外：

- 串流翻譯：一次消耗一個輸入詞元，記憶體有上限。
- 裝置端文字生成：Transformer 的記憶體成本高到不可接受。
- 教學。想懂 Transformer 為什麼贏，最快的路就是先懂編碼器解碼器的瓶頸。

### 曝光偏差與它的緩解手段

- **Scheduled sampling。** 在訓練過程中對 teacher forcing 比例做退火，讓模型學會從自己的錯誤中恢復。
- **最小風險訓練。** 用句子層級的 BLEU 分數取代詞元層級的交叉熵來訓練。更接近你真正想要的東西。
- **強化學習微調。** 用一個指標去獎勵序列生成器。現代 LLM 的 RLHF 就是這樣做的。

這三招在基於 Transformer 的生成上同樣適用。

## 產出交付

存成 `outputs/prompt-seq2seq-design.md`：

```markdown
---
name: seq2seq-design
description: Design a sequence-to-sequence pipeline for a given task.
phase: 5
lesson: 09
---

Given a task (translation, summarization, paraphrase, question rewrite), output:

1. Architecture. Pretrained transformer encoder-decoder (BART, T5, mBART, NLLB) is the default. RNN-based seq2seq only for specific constraints.
2. Starting checkpoint. Name it (`facebook/bart-base`, `google/flan-t5-base`, `facebook/nllb-200-distilled-600M`). Match the checkpoint to task and language coverage.
3. Decoding strategy. Greedy for deterministic output, beam search (width 4-5) for quality, sampling with temperature for diversity. One sentence justification.
4. One failure mode to verify before shipping. Exposure bias manifests as generation drift on longer outputs; sample 20 outputs at the 90th-percentile length and eyeball.

Refuse to recommend training a seq2seq from scratch for under a million parallel examples. Flag any pipeline that uses greedy decoding for user-facing content as fragile (greedy repeats and loops).
```

## 練習

1. **簡單。** 實作那個玩具複製任務。在「目標等於來源」的輸入輸出配對上訓練一個 GRU seq2seq。量測長度 5、10、20 時的準確率。把瓶頸重現出來。
2. **中等。** 加上 beam 寬度 3 的 beam search 解碼。在一個小型平行語料上量測 BLEU，與貪婪解碼比較。記錄 beam search 在哪裡勝出（通常是最後幾個詞元），又在哪裡毫無差別。
3. **困難。** 用一個一萬組配對的改寫資料集微調 `facebook/bart-base`。在保留的輸入上，比較微調後模型的 beam-4 輸出與基礎模型的輸出。回報 BLEU，並挑出 10 個定性的例子。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 編碼器 | 「輸入端的 RNN」 | 讀來源。產生逐步的隱藏狀態，以及最後的上下文向量。 |
| 解碼器 | 「輸出端的 RNN」 | 用上下文向量初始化。一次生成一個目標詞元。 |
| 上下文向量 | 「那個摘要」 | 編碼器最後的隱藏狀態。固定大小。注意力機制要解決的那道瓶頸。 |
| Teacher forcing | 「訓練時用真實詞元」 | 訓練期間餵入真正的前一個詞元。讓學習穩定下來。 |
| 曝光偏差 | 「訓練與測試的落差」 | 模型是用真實詞元訓練的，從沒練習過怎麼從自己的錯誤中恢復。 |
| Beam search | 「更好的解碼方式」 | 每一步同時保留分數最高的 k 條部分序列，而不是貪婪地認定一條。 |

## 延伸閱讀

- [Sutskever, Vinyals, Le (2014). Sequence to Sequence Learning with Neural Networks](https://arxiv.org/abs/1409.3215) —— 最初的 seq2seq 論文。四頁。
- [Cho et al. (2014). Learning Phrase Representations using RNN Encoder-Decoder for Statistical Machine Translation](https://arxiv.org/abs/1406.1078) —— 提出了 GRU 與編碼器解碼器的框架。
- [Bahdanau, Cho, Bengio (2014). Neural Machine Translation by Jointly Learning to Align and Translate](https://arxiv.org/abs/1409.0473) —— 注意力機制那篇論文。讀完本單元請立刻接著讀。
- [PyTorch NLP from Scratch tutorial](https://pytorch.org/tutorials/intermediate/seq2seq_translation_tutorial.html) —— 可實際建置的 seq2seq + 注意力機制程式碼。
