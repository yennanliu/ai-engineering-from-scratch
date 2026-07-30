# 詞嵌入 —— 從零實作 Word2Vec

> 一個詞就是它身邊那群詞。拿這個想法去訓練一個淺層網路，幾何結構就自己長出來了。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 02（BoW + TF-IDF）、階段 3 · 03（從零實作反向傳播）
**時間：** 約 75 分鐘

## 問題所在

TF-IDF 知道 `dog` 和 `puppy` 是兩個不同的詞，卻不知道它們的意思幾乎一樣。在 `dog` 上訓練出來的分類器，沒辦法推廣到一篇講 `puppy` 的評論。你可以列一份同義詞表把這件事遮過去，但碰到罕見詞、領域術語，以及每一種你沒預料到的語言，這招就失效了。

你想要的是這樣一種表示法：`dog` 和 `puppy` 在空間中落得很近；`king - man + woman` 落在 `queen` 附近；在 `dog` 上訓練的模型，能免費把一部分訊號轉移到 `puppy` 上。

Word2Vec 給了我們那個空間。兩層神經網路、兆級詞元的訓練規模，2013 年發表。架構簡單到近乎令人難為情，結果卻重塑了接下來十年的 NLP。

## 核心概念

**分布假說**（Firth, 1957）：「觀其伴，知其詞。」如果兩個詞出現在相似的上下文裡，它們的意思大概也相似。

Word2Vec 有兩種形式，兩者都在榨取這個想法。

- **Skip-gram。** 給定中心詞，預測周圍的詞。上下文視窗大小為 2 時，`cat -> (the, sat, on)`。
- **CBOW（continuous bag of words，連續詞袋）。** 給定周圍的詞，預測中心詞。`(the, sat, on) -> cat`。

Skip-gram 訓練比較慢，但對罕見詞處理得更好，於是成了預設選擇。

這個網路只有一層隱藏層，而且沒有非線性。輸入是詞彙表上的 one-hot 向量，輸出是詞彙表上的 softmax。訓練完成後，你把輸出層丟掉，隱藏層的權重就是詞嵌入。

```
one-hot(center) ── W ──▶ hidden (d-dim) ── W' ──▶ softmax(vocab)
                          ^
                          this is the embedding
```

訣竅在這裡：對 10 萬個詞做 softmax 貴到不可行。Word2Vec 用**負取樣**把它變成一個二元分類任務：預測「這個上下文詞有沒有出現在這個中心詞附近，是或不是」。每一組訓練配對只抽幾個負樣本（沒有共現的詞），而不是對整個詞彙表算 softmax。

```figure
word-vector-arithmetic
```

## 動手實作

### 步驟 1：從語料產生訓練配對

```python
def skipgram_pairs(docs, window=2):
    pairs = []
    for doc in docs:
        for i, center in enumerate(doc):
            for j in range(max(0, i - window), min(len(doc), i + window + 1)):
                if i == j:
                    continue
                pairs.append((center, doc[j]))
    return pairs
```

```python
>>> skipgram_pairs([["the", "cat", "sat", "on", "mat"]], window=2)
[('the', 'cat'), ('the', 'sat'),
 ('cat', 'the'), ('cat', 'sat'), ('cat', 'on'),
 ('sat', 'the'), ('sat', 'cat'), ('sat', 'on'), ('sat', 'mat'),
 ...]
```

一個上下文視窗裡的每一組（中心詞, 上下文詞）配對，都是一個正樣本訓練例。

### 步驟 2：嵌入矩陣

兩個矩陣。`W` 是中心詞的嵌入矩陣（你要留下來的那個），`W'` 是上下文詞的嵌入矩陣（通常丟掉，有時會跟 `W` 取平均）。

```python
import numpy as np


def init_embeddings(vocab_size, dim, seed=0):
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 0.1, size=(vocab_size, dim))
    W_prime = rng.normal(0, 0.1, size=(vocab_size, dim))
    return W, W_prime
```

小幅度的隨機初始化。詞彙量 10k、維度 100 是實務上合理的設定；教學用途上，50 個詞 x 16 維就足以看出幾何結構。

### 步驟 3：負取樣的目標函式

對每一組正配對 `(center, context)`，從詞彙表隨機抽 `k` 個詞當負樣本。訓練模型，讓內積 `W[center] · W'[context]` 對正樣本高、對負樣本低。

```python
def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def train_pair(W, W_prime, center_idx, context_idx, negative_indices, lr):
    v_c = W[center_idx]
    u_pos = W_prime[context_idx]
    u_negs = W_prime[negative_indices]

    pos_score = sigmoid(v_c @ u_pos)
    neg_scores = sigmoid(u_negs @ v_c)

    grad_center = (pos_score - 1) * u_pos
    for i, u in enumerate(u_negs):
        grad_center += neg_scores[i] * u

    W[context_idx] = W[context_idx]
    W_prime[context_idx] -= lr * (pos_score - 1) * v_c
    for i, neg_idx in enumerate(negative_indices):
        W_prime[neg_idx] -= lr * neg_scores[i] * v_c
    W[center_idx] -= lr * grad_center
```

關鍵的那道公式：正配對上的 logistic 損失（希望 sigmoid 接近 1），加上負配對上的 logistic 損失（希望 sigmoid 接近 0）。梯度會同時流進兩個嵌入矩陣。完整推導在原始論文裡；想真的把它記牢，就拿紙筆自己推一次。

### 步驟 4：在玩具語料上訓練

```python
def train(docs, dim=16, window=2, k_neg=5, epochs=100, lr=0.05, seed=0):
    vocab = build_vocab(docs)
    vocab_size = len(vocab)
    rng = np.random.default_rng(seed)
    W, W_prime = init_embeddings(vocab_size, dim, seed=seed)
    pairs = skipgram_pairs(docs, window=window)

    for epoch in range(epochs):
        rng.shuffle(pairs)
        for center, context in pairs:
            c_idx = vocab[center]
            ctx_idx = vocab[context]
            negs = rng.integers(0, vocab_size, size=k_neg)
            negs = [n for n in negs if n != ctx_idx and n != c_idx]
            train_pair(W, W_prime, c_idx, ctx_idx, negs, lr)
    return vocab, W
```

在大語料上跑足夠多的 epoch 之後，共享上下文的詞會得到相似的中心詞嵌入。在玩具語料上，這個效果只看得到淡淡的影子；在數十億詞元上，它明顯到誇張。

### 步驟 5：類比的把戲

```python
def nearest(vocab, W, target_vec, topk=5, exclude=None):
    exclude = exclude or set()
    inv_vocab = {i: w for w, i in vocab.items()}
    norms = np.linalg.norm(W, axis=1, keepdims=True) + 1e-9
    W_norm = W / norms
    target = target_vec / (np.linalg.norm(target_vec) + 1e-9)
    sims = W_norm @ target
    order = np.argsort(-sims)
    out = []
    for i in order:
        if i in exclude:
            continue
        out.append((inv_vocab[i], float(sims[i])))
        if len(out) == topk:
            break
    return out


def analogy(vocab, W, a, b, c, topk=5):
    v = W[vocab[b]] - W[vocab[a]] + W[vocab[c]]
    return nearest(vocab, W, v, topk=topk, exclude={vocab[a], vocab[b], vocab[c]})
```

在預訓練的 300 維 Google News 詞向量上：

```python
>>> analogy(vocab, W, "man", "king", "woman")
[('queen', 0.71), ('monarch', 0.62), ('princess', 0.59), ...]
```

`king - man + woman = queen`。這不是因為模型知道王室是什麼，而是因為向量 `(king - man)` 抓住了某種類似「王室」的東西，把它加到 `woman` 上，就落在「王室女性」那一區附近。詞向量算術能成立，就是這個道理。

## 框架應用

從零寫 Word2Vec 是為了學。生產環境的 NLP 用 `gensim`。

```python
from gensim.models import Word2Vec

sentences = [
    ["the", "cat", "sat", "on", "the", "mat"],
    ["the", "dog", "ran", "across", "the", "room"],
]

model = Word2Vec(
    sentences,
    vector_size=100,
    window=5,
    min_count=1,
    sg=1,
    negative=5,
    workers=4,
    epochs=30,
)

print(model.wv["cat"])
print(model.wv.most_similar("cat", topn=3))
```

真要做事的時候，你幾乎不會自己訓練 Word2Vec，而是下載預訓練好的詞向量。

- **GloVe** —— Stanford 那套分解共現矩陣的做法。有 50 維、100 維、200 維、300 維的權重檔。一般領域的覆蓋度不錯。單元 04 會專門講 GloVe。
- **fastText** —— Facebook 對 Word2Vec 的擴充，會把字元 n-gram 也嵌入進來。靠組合子詞來處理詞彙表外的詞。單元 04。
- **在 Google News 上預訓練的 Word2Vec** —— 300 維、300 萬詞的詞彙表，2013 年發表。到今天每天還是有人下載。

### Word2Vec 在 2026 年依然勝出的場合

- 輕量的領域專用檢索。在筆電上花一小時訓練醫學摘要，就能拿到通用模型抓不到的專門詞向量。
- 類比式的特徵工程。`gender_vector = mean(man - woman pairs)`，把它從其他詞減掉，就得到一條性別中立的軸。公平性研究至今還在用。
- 可解釋性。100 維小到可以用 PCA 或 t-SNE 畫出來，真的看見群集成形。
- 任何必須在裝置端、沒有 GPU 的情況下做推論的地方。Word2Vec 的查表就只是取出一列而已。

### Word2Vec 失效的地方

一詞多義那道牆。`bank` 只有一個向量，`river bank` 和 `financial bank` 共用它；`table`（試算表對家具）也共用它。下游的分類器沒辦法從這個向量裡分出不同的義項。

上下文式嵌入（ELMo、BERT，以及此後每一個 transformer）解決了這件事：它們依照周圍的上下文，為每一次出現的詞產生不同的向量。這就是從 Word2Vec 到 BERT 的那一跳 —— 從靜態到上下文式。transformer 這一半在階段 7 講。

詞彙表外問題是另一種失效。如果 `Zoomer-approved` 不在訓練資料裡，Word2Vec 就從沒見過它，也沒有任何退路。fastText 用子詞組合修掉了這一點（單元 04）。

## 產出交付

存成 `outputs/skill-embedding-probe.md`：

```markdown
---
name: embedding-probe
description: Inspect a word2vec model. Run analogies, find neighbors, diagnose quality.
version: 1.0.0
phase: 5
lesson: 03
tags: [nlp, embeddings, debugging]
---

You probe trained word embeddings to verify they are working. Given a `gensim.models.KeyedVectors` object and a vocabulary, you run:

1. Three canonical analogy tests. `king : man :: queen : woman`. `paris : france :: tokyo : japan`. `walking : walked :: swimming : ?`. Report the top-1 result and its cosine.
2. Five nearest-neighbor tests on domain-specific words the user supplies. Print top-5 neighbors with cosines.
3. One symmetry check. `similarity(a, b) == similarity(b, a)` to within float precision.
4. One degenerate check. If any embedding has a norm below 0.01 or above 100, the model has a training bug. Flag it.

Refuse to declare a model good on analogy accuracy alone. Analogy benchmarks are gameable and do not transfer to downstream tasks. Recommend intrinsic + downstream evaluation together.
```

## 練習

1. **簡單。** 在一個很小的語料（20 句關於貓和狗的句子）上跑訓練迴圈。200 個 epoch 之後，驗證 `nearest(vocab, W, W[vocab["cat"]])` 的前 3 名裡出現 `dog`。如果沒有，就把 epoch 數或詞彙量往上加。
2. **中等。** 加上高頻詞的子取樣。頻率高於 `10^-5` 的詞，以與其頻率成正比的機率從訓練配對中丟掉。量測這對罕見詞的語意相似度有什麼影響。
3. **困難。** 在 20 Newsgroups 語料上訓練一個模型。算出兩條偏誤軸：`he - she` 與 `doctor - nurse`。把職業詞投影到這兩條軸上，回報哪些職業的偏誤落差最大。這正是公平性研究者在用的那種探測手法。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 詞嵌入 | 「把詞變成向量」 | 從上下文學出來的稠密向量、低維（通常 100–300 維）表示。 |
| Skip-gram | 「Word2Vec 的把戲」 | 從中心詞預測上下文詞。比 CBOW 慢，但對罕見詞更好。 |
| 負取樣 | 「訓練的捷徑」 | 把整個詞彙表上的 softmax 換成對 `k` 個隨機詞的二元分類。 |
| 靜態嵌入 | 「一個詞一個向量」 | 不管上下文都是同一個向量。碰到一詞多義就失效。 |
| 上下文式嵌入 | 「隨上下文而變的向量」 | 依周圍的詞，為每一次出現各產生一個不同的向量。transformer 產出的就是這種。 |
| OOV | 「詞彙表外」 | 訓練時沒見過的詞。Word2Vec 沒辦法為它們產生向量。 |

## 延伸閱讀

- [Mikolov et al. (2013). Distributed Representations of Words and Phrases and their Compositionality](https://arxiv.org/abs/1310.4546) —— 負取樣那篇論文。短而好讀。
- [Rong, X. (2014). word2vec Parameter Learning Explained](https://arxiv.org/abs/1411.2738) —— 如果原始論文的數學讀起來太密，這份的梯度推導最清楚。
- [gensim Word2Vec tutorial](https://radimrehurek.com/gensim/models/word2vec.html) —— 真的能用的生產訓練設定。
