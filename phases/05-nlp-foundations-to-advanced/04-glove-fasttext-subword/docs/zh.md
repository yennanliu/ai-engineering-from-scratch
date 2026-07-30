# GloVe、FastText 與子詞嵌入

> Word2Vec 為每個詞訓練一個嵌入。GloVe 分解共現矩陣。FastText 把詞的組成部件也嵌入進去。BPE 則接上了 transformer 時代。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 03（從零打造 Word2Vec）
**時間：** 約 45 分鐘

## 問題所在

Word2Vec 留下了兩個未解的問題。

第一，當時有另一條研究路線（LSA、HAL）直接分解共現矩陣，而不是做線上的 skip-gram 更新。Word2Vec 的迭代式做法真的本質上更好，還是兩種方法之間的差距只是計數處理方式不同所造成的假象？**GloVe** 回答了這件事：只要損失函式選得夠周全，矩陣分解就能追平甚至勝過 Word2Vec，而且訓練成本更低。

第二，這兩種方法對於沒見過的詞都沒有未知詞處理的說法。`Zoomer-approved`、`dogecoin`、上週才被造出來的任何專有名詞、罕見詞根的每一種屈折變化。**FastText** 用嵌入字元 n-gram 解掉了這一題：一個詞是它各個部件的總和，其中包含詞素，所以即使是詞彙表外的詞也能拿到一個合理的向量。

第三，等 transformer 出現後，問題又變了。詞層級的詞彙表上限大約在一百萬條左右；真實語言比這開放得多。**位元組對編碼（BPE）**與它的親戚們學出一份由高頻子詞單位組成的詞彙表，把所有情況都涵蓋進去，藉此解決了這個問題。現代每一個 LLM 所用的每一個分詞器，都是子詞分詞器。

本單元把三者走過一遍，然後說明什麼時候該伸手拿哪一個。

## 核心概念

**GloVe（Global Vectors）。** 建出詞與詞的共現矩陣 `X`，其中 `X[i][j]` 是詞 `j` 出現在詞 `i` 脈絡中的次數。訓練向量使得 `v_i · v_j + b_i + b_j ≈ log(X[i][j])`。對損失做加權，讓高頻詞對不會獨占全局。這樣就完成了。

**FastText。** 一個詞是它的字元 n-gram 加上詞本身的總和。`where` 會變成 `<wh, whe, her, ere, re>, <where>`。詞向量就是這些組成向量的總和。訓練方式和 Word2Vec 一樣。好處是：沒見過的詞（`whereupon`）可以由已知的 n-gram 組合出來。

**BPE（位元組對編碼）。** 從一份由個別位元組（或字元）組成的詞彙表開始。統計語料中每一個相鄰的配對。把出現頻率最高的配對合併成一個新詞元。重複 `k` 次。結果是一份 `k + 256` 個詞元的詞彙表，其中高頻序列（`ing`、`tion`、`the`）是單一詞元，罕見詞則被切成熟悉的部件。任何句子都能被分出詞元來。

## 動手實作

### GloVe：分解共現矩陣

```python
import numpy as np
from collections import Counter


def build_cooccurrence(docs, window=5):
    pair_counts = Counter()
    vocab = {}
    for doc in docs:
        for token in doc:
            if token not in vocab:
                vocab[token] = len(vocab)
    for doc in docs:
        indexed = [vocab[t] for t in doc]
        for i, center in enumerate(indexed):
            for j in range(max(0, i - window), min(len(indexed), i + window + 1)):
                if i != j:
                    distance = abs(i - j)
                    pair_counts[(center, indexed[j])] += 1.0 / distance
    return vocab, pair_counts


def glove_train(vocab, pair_counts, dim=16, epochs=100, lr=0.05, x_max=100, alpha=0.75, seed=0):
    n = len(vocab)
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 0.1, size=(n, dim))
    W_tilde = rng.normal(0, 0.1, size=(n, dim))
    b = np.zeros(n)
    b_tilde = np.zeros(n)

    for epoch in range(epochs):
        for (i, j), x_ij in pair_counts.items():
            weight = (x_ij / x_max) ** alpha if x_ij < x_max else 1.0
            diff = W[i] @ W_tilde[j] + b[i] + b_tilde[j] - np.log(x_ij)
            coef = weight * diff

            grad_W_i = coef * W_tilde[j]
            grad_W_tilde_j = coef * W[i]
            W[i] -= lr * grad_W_i
            W_tilde[j] -= lr * grad_W_tilde_j
            b[i] -= lr * coef
            b_tilde[j] -= lr * coef

    return W + W_tilde
```

有兩個活動的零件值得點名。這是一個以全域統計為目標的加權最小平方問題：加權函式 `f(x) = (x/x_max)^alpha` 會壓低極高頻詞對（例如 `(the, and)`）的權重，讓它們不會獨占損失。最終的嵌入是 `W`（中心詞）與 `W_tilde`（脈絡詞）兩張表的和。把兩者相加是論文裡提過的一個小技巧，通常會比只用其中一張表更好。

### FastText：帶子詞資訊的嵌入

```python
def char_ngrams(word, n_min=3, n_max=6):
    wrapped = f"<{word}>"
    grams = {wrapped}
    for n in range(n_min, n_max + 1):
        for i in range(len(wrapped) - n + 1):
            grams.add(wrapped[i:i + n])
    return grams
```

```python
>>> char_ngrams("where")
{'<where>', '<wh', 'whe', 'her', 'ere', 're>', '<whe', 'wher', 'here', 'ere>', '<wher', 'where', 'here>'}
```

每個詞都由它的 n-gram 集合來表示（通常是 3 到 6 個字元）。詞嵌入就是這些 n-gram 嵌入的總和。要做 skip-gram 訓練時，把它接到原本 Word2Vec 使用單一向量的位置上就行。

```python
def fasttext_vector(word, ngram_table):
    grams = char_ngrams(word)
    vecs = [ngram_table[g] for g in grams if g in ngram_table]
    if not vecs:
        return None
    return np.sum(vecs, axis=0)
```

對於沒見過的詞，只要它有部分 n-gram 是已知的，你仍然拿得到一個向量。`whereupon` 和 `where` 共用了 `<wh`、`her`、`ere` 與 `<where`，所以兩者會落在彼此附近。

### BPE：學出來的子詞詞彙表

```python
def learn_bpe(corpus, k_merges):
    vocab = Counter()
    for word, freq in corpus.items():
        tokens = tuple(word) + ("</w>",)
        vocab[tokens] = freq

    merges = []
    for _ in range(k_merges):
        pair_freq = Counter()
        for tokens, freq in vocab.items():
            for a, b in zip(tokens, tokens[1:]):
                pair_freq[(a, b)] += freq
        if not pair_freq:
            break
        best = pair_freq.most_common(1)[0][0]
        merges.append(best)

        new_vocab = Counter()
        for tokens, freq in vocab.items():
            new_tokens = []
            i = 0
            while i < len(tokens):
                if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) == best:
                    new_tokens.append(tokens[i] + tokens[i + 1])
                    i += 2
                else:
                    new_tokens.append(tokens[i])
                    i += 1
            new_vocab[tuple(new_tokens)] = freq
        vocab = new_vocab
    return merges


def apply_bpe(word, merges):
    tokens = list(word) + ["</w>"]
    for a, b in merges:
        new_tokens = []
        i = 0
        while i < len(tokens):
            if i + 1 < len(tokens) and tokens[i] == a and tokens[i + 1] == b:
                new_tokens.append(a + b)
                i += 2
            else:
                new_tokens.append(tokens[i])
                i += 1
        tokens = new_tokens
    return tokens
```

```python
>>> corpus = Counter({"low": 5, "lower": 2, "newest": 6, "widest": 3})
>>> merges = learn_bpe(corpus, k_merges=10)
>>> apply_bpe("lowest", merges)
['low', 'est</w>']
```

第一次迭代會合併最常出現的相鄰配對。迭代次數足夠之後，高頻子字串（`low`、`est`、`tion`）就成了單一詞元，罕見詞也能被乾淨地切開。

真實的 GPT／BERT／T5 分詞器會學 3 萬到 10 萬次合併。結果是：任何文字都能被分成一串長度有界、且都是已知 ID 的序列，永遠不會出現 OOV。

## 框架應用

實務上你很少自己訓練這其中任何一個。你載入的是預訓練好的檢查點。

```python
import fasttext.util
fasttext.util.download_model("en", if_exists="ignore")
ft = fasttext.load_model("cc.en.300.bin")
print(ft.get_word_vector("whereupon").shape)
print(ft.get_word_vector("zoomerapproved").shape)
```

在 transformer 時代要做 BPE 風格的子詞分詞：

```python
from transformers import AutoTokenizer

tok = AutoTokenizer.from_pretrained("gpt2")
print(tok.tokenize("unbelievably tokenized"))
```

```
['un', 'bel', 'iev', 'ably', 'Ġtoken', 'ized']
```

`Ġ` 前綴標記詞的邊界（GPT-2 的慣例）。現代每一個分詞器都是 BPE 的變體、WordPiece（BERT），或 SentencePiece（T5、LLaMA）。

### 什麼時候該選哪一個

| 情境 | 選擇 |
|-----------|------|
| 通用的預訓練詞向量，不需要容納 OOV | GloVe，嵌入維度 300 |
| 通用的預訓練詞向量，但必須處理拼錯字／新造詞／形態學豐富的語言 | FastText |
| 任何要送進 transformer 的東西（訓練或推論） | 模型隨附的那個分詞器。絕對不要換。 |
| 從零訓練自己的語言模型 | 先在你的語料上訓練一個 BPE 或 SentencePiece 分詞器 |
| 用線性模型做生產環境的文字分類 | 還是 TF-IDF。見單元 02。 |

## 產出交付

存成 `outputs/skill-embeddings-picker.md`：

```markdown
---
name: tokenizer-picker
description: Pick a tokenization approach for a new language model or text pipeline.
version: 1.0.0
phase: 5
lesson: 04
tags: [nlp, tokenization, embeddings]
---

Given a task and dataset description, you output:

1. Tokenization strategy (word-level, BPE, WordPiece, SentencePiece, byte-level). One-sentence reason.
2. Vocabulary size target (e.g., 32k for an English-only LM, 64k-100k for multilingual).
3. Library call with the exact training command. Name the library. Quote the arguments.
4. One reproducibility pitfall. Tokenizer-model mismatch is the single most common silent production bug; call out which pair must be used together.

Refuse to recommend training a custom tokenizer when the user is fine-tuning a pretrained LLM. Refuse to recommend word-level tokenization for any model targeting production inference. Flag non-English / multi-script corpora as needing SentencePiece with byte fallback.
```

## 練習

1. **簡單。** 執行 `char_ngrams("playing")` 與 `char_ngrams("played")`，計算兩個 n-gram 集合的 Jaccard 重疊度。你應該會看到相當多共用的部件（`pla`、`lay`、`play`），這就是 FastText 能在形態學變體之間良好遷移的原因。
2. **中等。** 擴充 `learn_bpe`，讓它追蹤詞彙表的成長。把「每個語料字元的詞元數」對「合併次數」畫成圖。你應該會看到一開始壓縮得很快，之後漸近到每個詞元約 2 到 3 個字元。
3. **困難。** 在莎士比亞全集上訓練一個 1k 次合併的 BPE。比較常見詞與罕見專有名詞的分詞結果。量測訓練前後的平均每詞詞元數。把讓你意外的地方寫下來。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 共現矩陣 | 「詞與詞的頻率表」 | `X[i][j]` = 詞 `j` 出現在詞 `i` 周圍視窗中的次數。 |
| 子詞 | 「詞的一小塊」 | 一個字元 n-gram（FastText），或一個學出來的詞元（BPE／WordPiece／SentencePiece）。 |
| BPE | 「位元組對編碼」 | 反覆合併出現頻率最高的相鄰配對，直到詞彙表達到目標大小。 |
| OOV | 「詞彙表外」 | 模型從未見過的詞。Word2Vec／GloVe 會失效。FastText 與 BPE 處理得來。 |
| 位元組層級 BPE | 「跑在原始位元組上的 BPE」 | GPT-2 的做法。詞彙表從 256 個位元組起步，所以永遠不會有東西是 OOV。 |

## 延伸閱讀

- [Pennington, Socher, Manning (2014). GloVe: Global Vectors for Word Representation](https://nlp.stanford.edu/pubs/glove.pdf) —— GloVe 論文，七頁，至今仍是那個損失函式最好的推導。
- [Bojanowski et al. (2017). Enriching Word Vectors with Subword Information](https://arxiv.org/abs/1607.04606) —— FastText。
- [Sennrich, Haddow, Birch (2016). Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909) —— 把 BPE 引進現代 NLP 的那篇論文。
- [Hugging Face tokenizer summary](https://huggingface.co/docs/transformers/tokenizer_summary) —— BPE、WordPiece 與 SentencePiece 在實務上究竟差在哪裡。
