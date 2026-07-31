# 文字處理 —— 分詞、字幹提取、詞形還原

> 語言是連續的，模型是離散的。前處理就是兩者之間的橋。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 2 · 14（單純貝氏）
**時間：** 約 45 分鐘

## 問題所在

模型讀不懂 "The cats were running."，它讀的是整數。

每個 NLP 系統開場都會遇到同樣的三個問題。一個詞從哪裡開始。詞的字根是什麼。什麼時候該把 "run"、"running"、"ran" 當成同一個東西（因為這樣有幫助），什麼時候又該當成不同的東西（因為這樣沒幫助）。

分詞做錯，模型就只能從垃圾裡學。如果你的分詞器把 `don't` 切成一個詞元、卻把 `do n't` 切成兩個，訓練分布就分裂了。如果你的字幹提取器把 `organization` 和 `organ` 收斂到同一個字幹，主題模型就完蛋了。如果你的詞形還原器需要詞性脈絡、而你沒有傳進去，動詞就會被當成名詞處理。

本單元從零打造這三個前處理步驟，接著示範 NLTK 與 spaCy 怎麼做同一件事，讓你看清其中的取捨。

## 核心概念

三個操作。每一個都有自己的職責，也有自己的失效模式。

**分詞（tokenization）** 把字串切成詞元。「詞元」這個說法刻意含糊，因為合適的粒度取決於任務。傳統 NLP 用詞層級。Transformer 用子詞。沒有空白分隔的語言用字元。

**字幹提取（stemming）** 用規則砍掉字尾。快、粗暴、笨。`running -> run`。`organization -> organ`。第二個例子就是它的失效模式。

**詞形還原（lemmatization）** 借助文法知識把詞還原成字典形式。慢、準確，需要一張查找表或一個構詞分析器。`ran -> run`（得知道 "ran" 是 "run" 的過去式）。`better -> good`（得知道比較級的形式）。

實務原則。速度要緊、又能容忍雜訊時做字幹提取（搜尋索引、粗略分類）。語意要緊時做詞形還原（問答、語意搜尋，以及任何會被使用者讀到的東西）。

```figure
edit-distance
```

## 動手實作

### 步驟 1：一個 regex 詞層級分詞器

最簡單堪用的分詞器會在非英數字元處切開，同時把標點保留成獨立的詞元。不完美，也不是最終版，但一行就跑得起來。

```python
import re

def tokenize(text):
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+|[^\sA-Za-z0-9]", text)
```

三個模式依優先順序排列。帶可選內部撇號的詞（`don't`、`it's`）。純數字。任何單一個非空白、非英數的字元作為獨立詞元（標點）。

```python
>>> tokenize("The cats weren't running at 3pm.")
['The', 'cats', "weren't", 'running', 'at', '3', 'pm', '.']
```

要留意的失效模式。`3pm` 被切成 `['3', 'pm']`，因為我們是在字母串與數字串之間交替匹配。對多數任務來說夠用了。URL、電子郵件、hashtag 全都會壞掉。要上生產環境，就在通用模式之前補上專用模式。

### 步驟 2：一個 Porter 字幹提取器（只做 step 1a）

完整的 Porter 演算法有五個階段的規則。單靠 step 1a 就涵蓋了英文最常見的字尾，也足以說明整套模式的做法。

```python
def stem_step_1a(word):
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s") and len(word) > 1:
        return word[:-1]
    return word
```

```python
>>> [stem_step_1a(w) for w in ["caresses", "ponies", "caress", "cats"]]
['caress', 'poni', 'caress', 'cat']
```

規則要從上往下讀。`ies -> i` 這條規則就是 `ponies -> poni`（而不是 `pony`）的原因。真正的 Porter 還有 step 1b 會把它修好。規則之間會互相競爭，先出現的規則贏。順序比任何單一條規則都更重要。

### 步驟 3：一個查表式詞形還原器

正統的詞形還原需要構詞學。一個好教學、又做得動的版本是用一張小型的詞根表加上一條退路。

```python
LEMMA_TABLE = {
    ("running", "VERB"): "run",
    ("ran", "VERB"): "run",
    ("runs", "VERB"): "run",
    ("better", "ADJ"): "good",
    ("best", "ADJ"): "good",
    ("cats", "NOUN"): "cat",
    ("cat", "NOUN"): "cat",
    ("were", "VERB"): "be",
    ("was", "VERB"): "be",
    ("is", "VERB"): "be",
}

def lemmatize(word, pos):
    key = (word.lower(), pos)
    if key in LEMMA_TABLE:
        return LEMMA_TABLE[key]
    if pos == "VERB" and word.endswith("ing"):
        return word[:-3]
    if pos == "NOUN" and word.endswith("s"):
        return word[:-1]
    return word.lower()
```

```python
>>> lemmatize("running", "VERB")
'run'
>>> lemmatize("cats", "NOUN")
'cat'
>>> lemmatize("better", "ADJ")
'good'
>>> lemmatize("watched", "VERB")
'watched'
```

最後一個例子才是關鍵的教學時刻。`watched` 不在我們的表裡，而我們的退路只處理 `ing`。真正的詞形還原要涵蓋 `ed`、不規則動詞、比較級形容詞，以及會變音的複數（`children -> child`）。這正是生產系統會採用 WordNet、spaCy 的 morphologizer，或一個完整構詞分析器的原因。

### 步驟 4：串成一條管線

```python
def preprocess(text, pos_tagger=None):
    tokens = tokenize(text)
    stems = [stem_step_1a(t.lower()) for t in tokens]
    tags = pos_tagger(tokens) if pos_tagger else [(t, "NOUN") for t in tokens]
    lemmas = [lemmatize(word, pos) for word, pos in tags]
    return {"tokens": tokens, "stems": stems, "lemmas": lemmas}
```

缺的那一塊是詞性標註器。階段 5 · 07（詞性標註）會做一個出來。目前先把所有詞都預設成 `NOUN`，並承認這個限制。

## 框架應用

NLTK 與 spaCy 直接附上了生產級的版本。各自幾行就搞定。

### NLTK

```python
import nltk
nltk.download("punkt_tab")
nltk.download("wordnet")
nltk.download("averaged_perceptron_tagger_eng")

from nltk.tokenize import word_tokenize
from nltk.stem import PorterStemmer, WordNetLemmatizer
from nltk import pos_tag

text = "The cats were running."
tokens = word_tokenize(text)
stems = [PorterStemmer().stem(t) for t in tokens]
lemmatizer = WordNetLemmatizer()
tagged = pos_tag(tokens)


def nltk_pos_to_wordnet(tag):
    if tag.startswith("V"):
        return "v"
    if tag.startswith("J"):
        return "a"
    if tag.startswith("R"):
        return "r"
    return "n"


lemmas = [lemmatizer.lemmatize(t, nltk_pos_to_wordnet(tag)) for t, tag in tagged]
```

`word_tokenize` 會處理縮寫、Unicode，以及你的 regex 漏掉的邊界情況。`PorterStemmer` 跑完全部五個階段。`WordNetLemmatizer` 需要把詞性標記從 NLTK 的 Penn Treebank 體系轉譯成 WordNet 的縮寫集合。上面那段轉譯的接線，正是多數教學會跳過的部分。

### spaCy

```python
import spacy

nlp = spacy.load("en_core_web_sm")
doc = nlp("The cats were running.")

for token in doc:
    print(token.text, token.lemma_, token.pos_)
```

```
The      the     DET
cats     cat     NOUN
were     be      AUX
running  run     VERB
.        .       PUNCT
```

spaCy 把整條管線都藏在 `nlp(text)` 後面。分詞、詞性標註、詞形還原全部跑完。規模一大就比 NLTK 快，開箱的準確度也更高。代價是你很難單獨替換其中某個元件。

### 什麼時候選哪一個

| 情境 | 選擇 |
|-----------|------|
| 教學、研究、需要替換元件 | NLTK |
| 生產環境、多語言、速度要緊 | spaCy |
| Transformer 管線（反正你會用模型自己的分詞器分詞） | 用 `tokenizers` / `transformers`，跳過傳統前處理 |

### 沒人會提醒你的兩個失效模式

多數教學只教演算法就收尾。有兩件事會真的咬到一條上線的前處理管線，而它們幾乎從來沒被提過。

**可重現性漂移。** NLTK 與 spaCy 會在版本之間改動分詞與詞形還原的行為。在 spaCy 2.x 產生 `['do', "n't"]` 的輸入，到 3.x 可能變成 `["don't"]`。你的模型是在某一個分布上訓練的，推論卻跑在另一個分布上。準確度悄悄下滑，而沒人知道為什麼。請在 `requirements.txt` 裡鎖定函式庫版本。寫一個前處理的迴歸測試，把 20 個範例句子的預期分詞結果凍結下來。每次升級都跑一次。

**訓練／推論不一致。** 訓練時用了很激進的前處理（大小寫轉換、移除停用詞、字幹提取），部署時卻直接餵原始的使用者輸入，然後看著效果崩掉。這是生產環境 NLP 最常見的單一失效原因。如果你在訓練時做了前處理，推論時就必須跑一模一樣的函式。請把前處理當成模型套件裡的一個函式一起交付，而不是留成一格筆記本程式碼、讓服務團隊自己重寫一遍。

## 產出交付

一個可重複使用的提示詞，讓工程師不必讀三本教科書就能挑出前處理策略。

存成 `outputs/prompt-preprocessing-advisor.md`：

```markdown
---
name: preprocessing-advisor
description: Recommends a tokenization, stemming, and lemmatization setup for an NLP task.
phase: 5
lesson: 01
---

You advise on classical NLP preprocessing. Given a task description, you output:

1. Tokenization choice (regex, NLTK word_tokenize, spaCy, or transformer tokenizer). Explain why.
2. Whether to stem, lemmatize, both, or neither. Explain why.
3. Specific library calls. Name the functions. Quote the POS-tag translation if NLTK is involved.
4. One failure mode the user should test for.

Refuse to recommend stemming for user-visible text. Refuse to recommend lemmatization without POS tags. Flag non-English input as needing a different pipeline.
```

## 練習

1. **簡單。** 擴充 `tokenize`，讓 URL 保持成單一個詞元。測試：`tokenize("Visit https://example.com today.")` 應該產生一個 URL 詞元。
2. **中等。** 實作 Porter 的 step 1b。如果一個詞含有母音、且以 `ed` 或 `ing` 結尾，就把字尾去掉。要處理雙寫子音的規則（`hopping -> hop`，而不是 `hopp`）。
3. **困難。** 打造一個詞形還原器，以 WordNet 作為查找表，但在 WordNet 查不到時退回你自己的 Porter 字幹提取器。在一份帶詞性標記的語料上量測準確度，並與純 WordNet、純 Porter 互相比較。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 詞元 | 「一個詞」 | 模型消耗的任何單位。可以是詞、子詞、字元或位元組。 |
| 字幹 | 「一個詞的字根」 | 用規則剝除字尾之後的結果。不一定是個真的詞。 |
| 詞根（lemma） | 「字典形式」 | 你會拿去查字典的那個形式。要正確算出來需要文法脈絡。 |
| 詞性標記（POS tag） | 「詞類」 | 像 NOUN、VERB、ADJ 這樣的類別。要準確做詞形還原就少不了它。 |
| 構詞學 | 「詞形變化的規則」 | 一個詞會依時態、數、格而改變形式的方式。詞形還原就依賴這些規則。 |

## 延伸閱讀

- [Porter, M. F. (1980). An algorithm for suffix stripping](https://tartarus.org/martin/PorterStemmer/def.txt) —— 原始論文，五頁，至今仍是最清楚的說明。
- [spaCy 101 — linguistic features](https://spacy.io/usage/linguistic-features) —— 一條真實的管線是怎麼接起來的。
- [NLTK book, chapter 3](https://www.nltk.org/book/ch03.html) —— 你還沒想到的那些分詞邊界情況。
