# 用於文字的 CNN 與 RNN

> 卷積學的是 n-gram。循環結構會記東西。兩者都被注意力機制取代了。在受限硬體上，兩者都還是重要的。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 3 · 11（PyTorch 入門）、階段 5 · 03（詞嵌入 Word2Vec）、階段 4 · 02（從零實作卷積）
**時間：** 約 75 分鐘

## 問題所在

TF-IDF 與 Word2Vec 產生的是忽略詞序的扁平向量。建在它們之上的分類器，分不出 `dog bites man` 和 `man bites dog`。而詞序有時就是訊號本身。

在 Transformer 出現之前，有兩類架構填補了這個缺口。

**用於文字的卷積網路（TextCNN）。** 在詞嵌入序列上做一維卷積。寬度 3 的濾波器就是一個可學習的 trigram 偵測器：它跨過三個詞，輸出一個分數。把不同寬度（2、3、4、5）疊在一起，就能偵測多種尺度的樣態。再用最大池化壓成固定大小的表示。扁平、可平行、快。

**循環神經網路（RNN、LSTM、GRU）。** 一次處理一個詞元，並維護一個把資訊往前帶的隱藏狀態。序列式、帶記憶、輸入長度可變。從 2014 到 2017 年主宰序列建模，然後注意力機制就來了。

本單元把兩者都實作出來，再點名那個催生注意力機制的失敗之處。

## 核心概念

**TextCNN**（Kim, 2014）。詞元先做嵌入。寬度為 `k` 的一維卷積把濾波器滑過連續的 `k`-gram 嵌入，產生一張特徵圖。對這張圖做全域最大池化，挑出最強的激活值。把好幾種濾波器寬度的池化結果串接起來，餵進分類頭。

它為什麼行得通。一個濾波器就是一個可學習的 n-gram。最大池化與位置無關，所以 "not good" 不管出現在評論的開頭還是中間，觸發的都是同一個特徵。三種濾波器寬度、每種 100 個濾波器，就給你 300 個學出來的 n-gram 偵測器。訓練是平行的，沒有序列上的依賴。

**RNN。** 在每個時間步 `t`，隱藏狀態 `h_t = f(W * x_t + U * h_{t-1} + b)`。`W`、`U`、`b` 跨時間共用。時間 `T` 的隱藏狀態就是整段前綴的摘要。要做分類，就對 `h_1 ... h_T` 做池化（最大、平均，或取最後一個）。

單純的 RNN 有梯度消失的問題。**LSTM** 加上門控機制，決定要遺忘什麼、要存下什麼、要輸出什麼，讓梯度穿過長序列時仍然穩定。**GRU** 把 LSTM 簡化成兩個門；參數更少，表現相當。

**雙向 RNN** 跑一個往前的 RNN 和另一個往後的 RNN，再把隱藏狀態串接起來。每個詞元的表示都同時看到左側與右側的脈絡。做標註任務時不可或缺。

```figure
rnn-unroll
```

## 動手實作

### 步驟 1：用 PyTorch 實作 TextCNN

```python
import torch
import torch.nn as nn
import torch.nn.functional as F


class TextCNN(nn.Module):
    def __init__(self, vocab_size, embed_dim, n_classes, filter_widths=(2, 3, 4), n_filters=64, dropout=0.3):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.convs = nn.ModuleList([
            nn.Conv1d(embed_dim, n_filters, kernel_size=k)
            for k in filter_widths
        ])
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(n_filters * len(filter_widths), n_classes)

    def forward(self, token_ids):
        x = self.embed(token_ids).transpose(1, 2)
        pooled = []
        for conv in self.convs:
            c = F.relu(conv(x))
            p = F.max_pool1d(c, c.size(2)).squeeze(2)
            pooled.append(p)
        h = torch.cat(pooled, dim=1)
        return self.fc(self.dropout(h))
```

`transpose(1, 2)` 把 `[batch, seq_len, embed_dim]` 重塑成 `[batch, embed_dim, seq_len]`，因為 `nn.Conv1d` 把中間那一軸當成通道。不管輸入多長，池化後的輸出都是固定大小。

### 步驟 2：LSTM 分類器

```python
class LSTMClassifier(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_dim, n_classes, bidirectional=True, dropout=0.3):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True, bidirectional=bidirectional)
        factor = 2 if bidirectional else 1
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim * factor, n_classes)

    def forward(self, token_ids):
        x = self.embed(token_ids)
        out, _ = self.lstm(x)
        pooled = out.max(dim=1).values
        return self.fc(self.dropout(pooled))
```

這裡是對整段序列做最大池化，不是取最後狀態來池化。做分類時，最大池化通常勝過拿最後一個隱藏狀態，因為長序列尾端的資訊往往會主宰最後那個狀態。

### 步驟 3：梯度消失示範（建立直覺）

沒有門控機制的單純 RNN 學不到長距離依賴。想一個玩具任務：預測詞元 `A` 有沒有在序列裡的任何位置出現過。如果 `A` 在位置 1，而序列長 100 個詞元，損失算出的梯度就得一路往回穿過 99 次循環權重的乘法。權重小於 1，梯度就消失；大於 1，梯度就爆炸。

```python
def vanishing_gradient_sim(seq_len, recurrent_weight=0.9):
    import math
    return math.pow(recurrent_weight, seq_len)


# At weight=0.9 over 100 steps:
#   0.9 ^ 100 ≈ 2.7e-5
# The gradient from step 100 to step 1 is effectively zero.
```

LSTM 用一條**記憶單元狀態（cell state）**修掉這件事：它貫穿整個網路，途中只有加法互動（遺忘門會對它做乘法縮放，但梯度仍然沿著這條「高速公路」流動）。GRU 用更少的參數做了類似的事。兩者都讓你能在 100 步以上的序列上穩定訓練。

### 步驟 4：為什麼這樣還是不夠

就算有了 LSTM，三個問題還在。

1. **序列瓶頸。** 在長度 1000 的序列上訓練 RNN，需要 1000 次串連的前向傳播與反向傳遞。無法在時間軸上平行化。
2. **編碼器—解碼器架構裡固定大小的脈絡向量。** 解碼器只看到編碼器最後那個隱藏狀態，整段輸入都被壓縮在裡面。輸入一長，細節就丟了。單元 09 會直接處理這件事。
3. **長距離依賴的準確度天花板。** LSTM 勝過單純的 RNN，但要把特定資訊傳過 200 步以上仍然吃力。

注意力機制一次解決了這三個。Transformer 則徹底丟掉了循環結構。單元 10 就是那個轉折點。

## 框架應用

PyTorch 的 `nn.LSTM`、`nn.GRU` 與 `nn.Conv1d` 都是生產級的。訓練程式碼就是標準寫法。

Hugging Face 提供預訓練嵌入，可以直接插進來當輸入層：

```python
from transformers import AutoModel

encoder = AutoModel.from_pretrained("bert-base-uncased")
for param in encoder.parameters():
    param.requires_grad = False


class BertCNN(nn.Module):
    def __init__(self, n_classes, filter_widths=(2, 3, 4), n_filters=64):
        super().__init__()
        self.encoder = encoder
        self.convs = nn.ModuleList([nn.Conv1d(768, n_filters, kernel_size=k) for k in filter_widths])
        self.fc = nn.Linear(n_filters * len(filter_widths), n_classes)

    def forward(self, input_ids, attention_mask):
        with torch.no_grad():
            out = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        x = out.transpose(1, 2)
        pooled = [F.max_pool1d(F.relu(conv(x)), kernel_size=conv(x).size(2)).squeeze(2) for conv in self.convs]
        return self.fc(torch.cat(pooled, dim=1))
```

「條件對上了就用它」的檢查清單。

- **邊緣／裝置端推論。** 搭配 GloVe 嵌入的 TextCNN 比 Transformer 小 10 到 100 倍。如果部署目標是手機，就是這一套。
- **串流／線上分類。** RNN 一次處理一個詞元；Transformer 需要整段序列。對即時進來的文字，LSTM 仍然贏。
- **當基準線用的小模型。** 在新任務上快速迭代。在 CPU 上 5 分鐘就訓好一個 TextCNN。
- **標註資料有限的序列標註。** 面對 1k 到 10k 句標註資料，BiLSTM-CRF（單元 06）仍是生產級的 NER 架構。

其他情況都交給 Transformer。

## 產出交付

存成 `outputs/prompt-text-encoder-picker.md`：

```markdown
---
name: text-encoder-picker
description: Pick a text encoder architecture for a given constraint set.
phase: 5
lesson: 08
---

Given constraints (task, data volume, latency budget, deploy target, compute budget), output:

1. Encoder architecture: TextCNN, BiLSTM, BiLSTM-CRF, transformer fine-tune, or "use a pretrained transformer as a frozen encoder + small head".
2. Embedding input: random init, GloVe / fastText frozen, or contextualized transformer embeddings.
3. Training recipe in 5 lines: optimizer, learning rate, batch size, epochs, regularization.
4. One monitoring signal. For RNN/CNN models: attention mechanism absence means they miss long-range deps; check per-length accuracy. For transformers: fine-tuning collapse if LR too high; check train loss.

Refuse to recommend fine-tuning a transformer when data is under ~500 labeled examples without showing that a TextCNN / BiLSTM baseline has plateaued. Flag edge deployment as needing architecture-before-everything.
```

## 練習

1. **簡單。** 在一個 3 類的玩具資料集上訓練 TextCNN（資料你自己造）。驗證濾波器寬度 (2, 3, 4) 的平均 F1 勝過單一寬度 (3)。
2. **中等。** 為 LSTM 分類器實作最大池化、平均池化與最後狀態池化。在一個小資料集上比較；記錄哪一種池化勝出，並提出你對原因的假設。
3. **困難。** 做一個 BiLSTM-CRF 的 NER 標註器（把單元 06 與本單元結合起來）。在 CoNLL-2003 上訓練。與單元 06 的純 CRF 基準線、以及 BERT 微調做比較。回報訓練時間、記憶體用量與 F1。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| TextCNN | 「文字版的 CNN」 | 在詞嵌入上疊一組一維卷積，再加全域最大池化。Kim (2014)。 |
| RNN | 「循環網路」 | 每個時間步更新一次的隱藏狀態：`h_t = f(W x_t + U h_{t-1})`。 |
| LSTM | 「加了門的 RNN」 | 多了輸入門／遺忘門／輸出門，再加一條記憶單元狀態。能穿過長序列穩定訓練。 |
| GRU | 「簡化版 LSTM」 | 兩個門而不是三個。準確度相當，參數更少。 |
| 雙向 | 「兩個方向都跑」 | 往前與往後的 RNN 串接起來。每個詞元都看得到脈絡的兩側。 |
| 梯度消失 | 「訓練訊號死掉了」 | 單純的 RNN 裡反覆乘上小於 1 的權重，讓早期時間步的梯度實質上變成零。 |

## 延伸閱讀

- [Kim, Y. (2014). Convolutional Neural Networks for Sentence Classification](https://arxiv.org/abs/1408.5882) —— TextCNN 那篇論文。八頁。好讀。
- [Hochreiter, S. and Schmidhuber, J. (1997). Long Short-Term Memory](https://www.bioinf.jku.at/publications/older/2604.pdf) —— LSTM 原始論文。意外地清楚。
- [Olah, C. (2015). Understanding LSTM Networks](https://colah.github.io/posts/2015-08-Understanding-LSTMs/) —— 讓 LSTM 對所有人都變得好懂的那組示意圖。
