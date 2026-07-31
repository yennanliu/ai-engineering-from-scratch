# 情感分析

> NLP 的經典任務。關於古典文字分類，你需要知道的大部分東西都會在這裡現身。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 02（詞袋模型 + TF-IDF）、階段 2 · 14（單純貝氏）
**時間：** 約 75 分鐘

## 問題所在

"The food was not great." 正面還是負面？

情感聽起來很簡單。評論者說他喜歡或不喜歡某個東西，把句子標記起來就好。它之所以成為 NLP 的經典任務，是因為每一個看起來簡單的案例，背後都藏著一個難的。否定會把意思翻轉。反諷會把它反過來。"Not bad at all" 明明有兩個負面調性的詞，卻是正面的。表情符號帶的訊號比周圍的文字還多。領域詞彙也有影響（音樂評論裡的 `tight` 和時尚評論裡的 `tight` 不是同一回事）。

情感分析是古典 NLP 的一個實作實驗室。如果你能理解為什麼每一個看似天真的基準線都有一個特定的失效模式，你就理解了為什麼每一個更豐富的模型會被發明出來。這個單元會從零打造一個單純貝氏基準線，加上邏輯迴歸，並點名那些讓生產環境的情感分析變成合規等級難題的陷阱。

## 核心概念

古典情感分析是一份兩步驟的食譜。

1. **表示。** 把文字轉成特徵向量。詞袋模型、TF-IDF，或 n-gram。
2. **分類。** 在有標註的樣本上訓練一個線性模型（單純貝氏、邏輯迴歸、SVM）。

單純貝氏是「能用的模型裡最笨的那一個」。假設在給定標籤的條件下每個特徵都互相獨立。從計數估出 `P(word | positive)` 和 `P(word | negative)`。推論時把機率乘起來。那個「單純」的獨立假設錯得可笑，可是結果強得驚人。原因在於：面對稀疏的文字特徵與中等規模的資料，分類器在意的是每個詞往哪一邊傾，而不是傾得多用力。

邏輯迴歸修掉了獨立假設。它替每個特徵學一個權重，包含負權重。`not good` 作為一個 bigram 特徵會拿到負權重。對於從沒被標註過的 bigram，單純貝氏做不到這件事。

```figure
sentiment-logits
```

## 動手實作

### 步驟 1：一份真的迷你資料集

```python
POSITIVE = [
    "absolutely loved this movie",
    "beautiful cinematography and a great story",
    "one of the best films of the year",
    "brilliant acting from the lead",
    "heartwarming and funny",
]

NEGATIVE = [
    "boring and far too long",
    "not worth your time",
    "the plot made no sense",
    "terrible acting, awful script",
    "i want my two hours back",
]
```

刻意做得很小。真實工作用的是幾萬個樣本（IMDb、SST-2、Yelp polarity）。數學是一模一樣的。

### 步驟 2：從零實作多項式單純貝氏

```python
import math
from collections import Counter


def train_nb(docs_by_class, vocab, alpha=1.0):
    class_priors = {}
    class_word_probs = {}
    total_docs = sum(len(d) for d in docs_by_class.values())

    for cls, docs in docs_by_class.items():
        class_priors[cls] = len(docs) / total_docs
        counts = Counter()
        for doc in docs:
            for token in doc:
                counts[token] += 1
        total = sum(counts.values()) + alpha * len(vocab)
        class_word_probs[cls] = {
            w: (counts[w] + alpha) / total for w in vocab
        }
    return class_priors, class_word_probs


def predict_nb(doc, class_priors, class_word_probs):
    scores = {}
    for cls in class_priors:
        s = math.log(class_priors[cls])
        for token in doc:
            if token in class_word_probs[cls]:
                s += math.log(class_word_probs[cls][token])
        scores[cls] = s
    return max(scores, key=scores.get)
```

加法平滑（alpha=1.0）就是拉普拉斯平滑。少了它，一個在某個類別裡沒出現過的詞機率會是零，取 log 就爆掉。實務上 `alpha=0.01` 很常見。`alpha=1.0` 是教學用的預設值。

### 步驟 3：從零實作邏輯迴歸

```python
import numpy as np


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def train_lr(X, y, epochs=500, lr=0.05, l2=0.01):
    n_features = X.shape[1]
    w = np.zeros(n_features)
    b = 0.0
    for _ in range(epochs):
        logits = X @ w + b
        preds = sigmoid(logits)
        err = preds - y
        grad_w = X.T @ err / len(y) + l2 * w
        grad_b = err.mean()
        w -= lr * grad_w
        b -= lr * grad_b
    return w, b


def predict_lr(X, w, b):
    return (sigmoid(X @ w + b) >= 0.5).astype(int)
```

L2 正則化在這裡很關鍵。文字特徵是稀疏的；沒有 L2，模型會把訓練樣本背下來。從 `0.01` 開始，再調。

### 步驟 4：處理否定（那個失效模式）

想想 "not good" 和 "not bad"。一個詞袋模型分類器看到的是 `{not, good}` 和 `{not, bad}`，然後從訓練時哪一組出現得多來學。一個 bigram 分類器看到的是 `not_good` 和 `not_bad`，會把它們當成兩個不同的特徵來學。這樣通常就夠了。

還有一個更粗糙、但在你沒有 bigram 時仍然管用的補法：**否定範圍界定（negation scoping）**。把否定詞之後的詞元一路加上 `NOT_` 前綴，直到遇到下一個標點符號。

```python
NEGATION_WORDS = {"not", "no", "never", "nor", "none", "nothing", "neither"}
NEGATION_TERMINATORS = {".", "!", "?", ",", ";"}


def apply_negation(tokens):
    out = []
    negate = False
    for token in tokens:
        if token in NEGATION_TERMINATORS:
            negate = False
            out.append(token)
            continue
        if token in NEGATION_WORDS:
            negate = True
            out.append(token)
            continue
        out.append(f"NOT_{token}" if negate else token)
    return out
```

```python
>>> apply_negation(["not", "good", "at", "all", ".", "but", "funny"])
['not', 'NOT_good', 'NOT_at', 'NOT_all', '.', 'but', 'funny']
```

現在 `good` 和 `NOT_good` 是兩個不同的特徵，分類器可以給它們相反的權重。三行前處理，在情感分析的基準測試上換到一個量得出來的準確率跳升。

### 步驟 5：真正重要的評估指標

如果類別不平衡，光看準確率會誤導。真實的情感語料庫通常有 70-80% 是正面、或 70-80% 是負面；一個永遠猜多數類別的分類器能拿到 80% 準確率，卻毫無價值。下面每一項都要回報：

- **各類別的精確率與召回率。** 每個類別一組。做 macro 平均，得到一個尊重類別平衡的單一數字。
- **Macro-F1（不平衡資料的主要指標）。** 各類別 F1 分數的平均，等權重。類別不平衡時，用它取代準確率。
- **Weighted-F1（另一個選擇）。** 和 macro 一樣，但按類別頻率加權。當不平衡本身帶有業務意義時，和 macro-F1 一起回報。
- **混淆矩陣。** 原始計數。在你相信任何純量指標之前都先看它；它會告訴你模型把哪一對類別搞混了。
- **各類別的錯誤樣本。** 每個類別抽 5 個預測錯的出來，讀過去。沒有東西能取代真的去讀那些錯誤。

對於嚴重不平衡的資料（超過 95-5 的比例），回報 **AUROC** 和 **AUPRC**，而不是準確率。AUPRC 對少數類別更敏感，而少數類別通常正是你在意的那一邊（垃圾訊息、詐欺、罕見情感）。

**要避開的常見錯誤。** 在不平衡資料上回報 micro-F1 而不是 macro-F1，會給出一個看起來很高的數字，因為它被多數類別主導了。Macro-F1 會逼你正面看到少數類別的表現。

```python
def evaluate(y_true, y_pred):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": precision, "recall": recall, "f1": f1}
```

## 框架應用

scikit-learn 用六行做完，而且做對。

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

pipe = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words=None)),
    ("clf", LogisticRegression(C=1.0, max_iter=1000)),
])
pipe.fit(X_train, y_train)
print(pipe.score(X_test, y_test))
```

有三件事要注意。`stop_words=None` 把否定詞留下來。`ngram_range=(1, 2)` 加入 bigram，於是 `not_good` 成為一個特徵。`sublinear_tf=True` 壓抑重複出現的詞。在 SST-2 上，這三個旗標就是「75% 準確率的基準線」和「85% 準確率的基準線」之間的差別。

### 什麼時候該伸手去拿 transformer

- 反諷偵測。古典模型在這裡就是不行。就這樣。
- 情感在文件中途轉向的長篇評論。
- 面向情感分析。"Camera was great but battery was terrible." 你得把情感歸屬到各個面向上。只有 transformer 或結構化輸出模型能做。
- 非英語、低資源語言。多語 BERT 免費送你一個 zero-shot 基準線。

如果你需要上面任何一項，直接跳到階段 7（Transformer 深入探討）。否則，在 TF-IDF 加 bigram 加否定處理上跑單純貝氏或邏輯迴歸，就是你 2026 年的生產基準線。

### 可重現性陷阱（又一次）

重新訓練情感模型是例行工作。重新評估它們卻不是。論文裡回報的準確率數字用的是特定的切分、特定的前處理、特定的分詞器。如果你不用一模一樣的流程就把新模型和某個基準線比較，你得到的差值會誤導你。永遠在你自己的流程上重新產生基準線，而不是拿論文的數字來用。

## 產出交付

存成 `outputs/prompt-sentiment-baseline.md`：

```markdown
---
name: sentiment-baseline
description: Design a sentiment analysis baseline for a new dataset.
phase: 5
lesson: 05
---

Given a dataset description (domain, language, size, label granularity, latency budget), you output:

1. Feature extraction recipe. Specify tokenizer, n-gram range, stopword policy (usually keep), negation handling (scoped prefix or bigrams).
2. Classifier. Naive Bayes for baseline, logistic regression for production, transformer only if the domain needs sarcasm / aspects / cross-lingual.
3. Evaluation plan. Report precision, recall, F1, confusion matrix, and per-class error samples (not just scalars).
4. One failure mode to monitor post-deployment. Domain drift and sarcasm are the top two.

Refuse to recommend dropping stopwords for sentiment tasks. Refuse to report accuracy as the sole metric when classes are imbalanced (e.g., 90% positive). Flag subword-rich languages as needing FastText or transformer embeddings over word-level TF-IDF.
```

## 練習

1. **簡單。** 把 `apply_negation` 加進 scikit-learn 流程當作一個前處理步驟，並在一個小型情感資料集上量出 F1 的變化量。
2. **中等。** 實作類別加權的邏輯迴歸（傳 `class_weight="balanced"` 給 scikit-learn，或自己推導梯度）。在一個人造的 90-10 類別不平衡上量出效果。
3. **困難。** 用情感模型的殘差訓練第二個分類器，做出一個反諷偵測器。把你的實驗設定記錄下來。當你的準確率低於隨機猜測時，要提醒讀者（2 類反諷的隨機水準大約是 50%，而大多數第一次嘗試都落在那裡）。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 極性（Polarity） | 「正面或負面」 | 二元標籤；有時擴充成中性，或更細的分級（5 星）。 |
| 面向情感分析 | 「每個面向各自的極性」 | 把情感歸屬到文字裡提到的特定實體或屬性上。 |
| 否定範圍界定 | 「把附近的詞元反過來」 | 在 "not" 之後的詞元加上 `NOT_` 前綴，直到遇到標點符號。 |
| 拉普拉斯平滑 | 「計數加 1」 | 防止單純貝氏出現機率為零的特徵。 |
| L2 正則化 | 「把權重縮小」 | 在損失函式上加 `lambda * sum(w^2)`。對稀疏文字特徵來說不可或缺。 |

## 延伸閱讀

- [Pang and Lee (2008). Opinion Mining and Sentiment Analysis](https://www.cs.cornell.edu/home/llee/opinion-mining-sentiment-analysis-survey.html) —— 奠基性的綜述。很長，但前四節就涵蓋了所有古典的內容。
- [Wang and Manning (2012). Baselines and Bigrams: Simple, Good Sentiment and Topic Classification](https://aclanthology.org/P12-2018/) —— 這篇論文證明了在短文本上，bigram 加單純貝氏很難被打敗。
- [scikit-learn text feature extraction docs](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction) —— `CountVectorizer`、`TfidfVectorizer` 以及你會調的每一個旋鈕的參考文件。
