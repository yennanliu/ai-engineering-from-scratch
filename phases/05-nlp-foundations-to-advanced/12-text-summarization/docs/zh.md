# 文字摘要

> 抽取式系統告訴你文件說了什麼，生成式系統告訴你作者想說什麼。不同的任務，不同的陷阱。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 02（BoW + TF-IDF）、階段 5 · 11（機器翻譯）
**時間：** 約 75 分鐘

## 問題所在

一篇 2,000 字的新聞落進你的資訊流。你需要用 120 個字把它講完。你可以從文章裡挑出最重要的三個句子（抽取式摘要），也可以用自己的話把內容重寫一遍（生成式摘要）。兩者都叫做摘要，但它們是完全不同的問題。

抽取式摘要是一個排序問題。替每個句子打分，回傳前 `k` 名。輸出一定合乎語法，因為它是逐字搬過來的。風險在於漏掉散落在全文各處的內容。

生成式摘要是一個生成問題。Transformer 以輸入為條件產生新的文字。輸出流暢、壓縮比高，但可能幻覺出來源裡沒有的事實。風險在於自信地編造。

本單元把兩者都做出來，連同各自專屬的失效模式。

## 核心概念

![抽取式 TextRank 與生成式 transformer 的對比](../assets/summarization.svg)

**抽取式。** 把文章看成一張圖：節點是句子，邊是相似度。在這張圖上跑 PageRank（或類似的東西），依據每個句子跟其他所有句子連結得多緊密來打分。分數最高的句子就是摘要。經典實作是 **TextRank**（Mihalcea and Tarau, 2004）。

**生成式。** 拿文件與摘要的配對，去微調一個 transformer 編碼器解碼器（BART、T5、Pegasus）。推論時，模型讀進文件，透過交叉注意力逐個詞元生成摘要。Pegasus 特別採用了 gap-sentence 的預訓練目標，讓它不需要太多微調就很擅長摘要。

評估用 **ROUGE**（Recall-Oriented Understudy for Gisting Evaluation）。ROUGE-1 與 ROUGE-2 計算 unigram 與 bigram 的重疊，ROUGE-L 計算最長共同子序列。分數越高越好，但 ROUGE-L 到 40 算「不錯」，到 50 算「非常突出」。每篇論文都會把三個一起報出來。用 `rouge-score` 這個套件。

## 動手實作

### 步驟 1：TextRank（抽取式）

```python
import math
import re
from collections import Counter


def sentence_split(text):
    return re.split(r"(?<=[.!?])\s+", text.strip())


def similarity(s1, s2):
    w1 = Counter(s1.lower().split())
    w2 = Counter(s2.lower().split())
    intersection = sum((w1 & w2).values())
    denom = math.log(len(w1) + 1) + math.log(len(w2) + 1)
    if denom == 0:
        return 0.0
    return intersection / denom


def textrank(text, top_k=3, damping=0.85, iterations=50, epsilon=1e-4):
    sentences = sentence_split(text)
    n = len(sentences)
    if n <= top_k:
        return sentences

    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                sim[i][j] = similarity(sentences[i], sentences[j])

    scores = [1.0] * n
    for _ in range(iterations):
        new_scores = [1 - damping] * n
        for i in range(n):
            total_out = sum(sim[i]) or 1e-9
            for j in range(n):
                if sim[i][j] > 0:
                    new_scores[j] += damping * sim[i][j] / total_out * scores[i]
        if max(abs(s - ns) for s, ns in zip(scores, new_scores)) < epsilon:
            scores = new_scores
            break
        scores = new_scores

    ranked = sorted(range(n), key=lambda k: scores[k], reverse=True)[:top_k]
    ranked.sort()
    return [sentences[i] for i in ranked]
```

有兩件事值得點名。相似度函式用的是經過對數正規化的詞重疊，這是 TextRank 最原始的版本；改用 TF-IDF 向量的餘弦相似度也行。阻尼係數 0.85 與迭代次數都沿用 PageRank 的預設值。

### 步驟 2：用 BART 做生成式摘要

```python
from transformers import pipeline

summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

article = """(long news article text)"""

summary = summarizer(article, max_length=120, min_length=60, do_sample=False)
print(summary[0]["summary_text"])
```

BART-large-CNN 是在 CNN/DailyMail 語料上微調出來的，開箱就能產出新聞風格的摘要。換到其他領域（科學論文、對話、法律），請改用對應的 Pegasus checkpoint，或在你自己的目標資料上微調。

### 步驟 3：ROUGE 評估

```python
from rouge_score import rouge_scorer

scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
scores = scorer.score(reference_summary, generated_summary)
print({k: round(v.fmeasure, 3) for k, v in scores.items()})
```

一定要開啟詞幹還原。少了它，"running" 和 "run" 會被當成不同的詞，ROUGE 就會低估分數。

### 超越 ROUGE（2026 年的摘要評估）

ROUGE 當了二十年摘要評估的主流指標，但在 2026 年單靠它已經不夠。一份針對 NLG 論文的大規模統合分析顯示：

- **BERTScore**（脈絡化嵌入之間的相似度）在 2023 年之前逐步普及，現在多數摘要論文都會把它與 ROUGE 並列報告。
- **BARTScore** 把評估當成生成問題：以來源為條件，看一個預訓練好的 BART 給這份摘要多高的機率，那就是它的分數。
- **MoverScore**（在脈絡化嵌入上計算 Earth Mover's Distance）在 2025 年的摘要基準上登上第一，因為它比 ROUGE 更能捕捉語意層面的重疊。
- **FactCC** 與**基於問答的忠實度**評估在 2021 至 2023 年間很常見，現在多半被 **G-Eval** 取代（一條 GPT-4 提示詞鏈，用思維鏈推理來評分連貫性、一致性、流暢度與相關性）。
- **G-Eval** 這類「LLM 當評審」的做法，在評分準則設計得好的情況下，大約 80% 的時候與人工判斷一致。

生產環境的建議：ROUGE-L 留著跟舊結果比較，BERTScore 看語意重疊，G-Eval 看連貫性與事實正確性。再拿 50 到 100 份經過人工評估的摘要來校準。

### 步驟 4：事實正確性的問題

生成式摘要很容易產生幻覺。抽取式摘要的幻覺風險低得多，因為輸出是從來源逐字搬過來的 —— 不過如果來源句子被剝離了脈絡、內容已經過時，或是引用順序被打亂，它一樣可能誤導讀者。這正是生產系統在與法規遵循相關的內容上，至今仍偏好抽取式方法的最大原因。

值得替它們取名的幻覺類型：

- **實體置換。** 來源寫 "John Smith"，摘要寫 "John Brown"。
- **數字漂移。** 來源寫 "25,000"，摘要寫 "25 million"。
- **極性翻轉。** 來源寫 "rejected the offer"，摘要寫 "accepted the offer"。
- **憑空造事實。** 來源根本沒提到執行長，摘要卻說執行長批准了。

行得通的評估做法：

- **FactCC。** 一個二元分類器，訓練來判斷來源句與摘要句之間是否成立蘊涵關係，輸出「符合事實／不符合事實」。
- **基於問答的事實查核。** 拿答案就在來源裡的問題去問一個問答模型。如果摘要支持的是別的答案，就標記出來。
- **實體層級 F1。** 比對來源與摘要中的命名實體。只出現在摘要裡的實體就是可疑對象。

任何面向使用者、而且事實正確性要緊的場景（新聞、醫療、法律、金融），抽取式都是比較安全的預設選擇。生成式則需要在流程裡放一道忠實度檢查。

## 框架應用

2026 年的技術堆疊：

| 使用場景 | 建議做法 |
|---------|-------------|
| 新聞、3 到 5 句的摘要、英文 | `facebook/bart-large-cnn` |
| 科學論文 | `google/pegasus-pubmed` 或調校過的 T5 |
| 多文件、長文件處理 | 任何脈絡長度 32k 以上的 LLM，用提示詞驅動 |
| 對話摘要 | `philschmid/bart-large-cnn-samsum` |
| 抽取式，結構上就幾乎沒有幻覺風險 | TextRank 或 `sumy` 的 LSA／LexRank |

在 2026 年，只要運算資源不是限制，長脈絡的 LLM 常常打贏專用模型。代價是成本與可重現性；專用模型的輸出比較一致。

## 產出交付

存成 `outputs/skill-summary-picker.md`：

```markdown
---
name: summary-picker
description: Pick extractive or abstractive, named library, factuality check.
version: 1.0.0
phase: 5
lesson: 12
tags: [nlp, summarization]
---

Given a task (document type, compliance requirement, length, compute budget), output:

1. Approach. Extractive or abstractive. Explain in one sentence why.
2. Starting model / library. Name it. `sumy.TextRankSummarizer`, `facebook/bart-large-cnn`, `google/pegasus-pubmed`, or an LLM prompt.
3. Evaluation plan. ROUGE-1, ROUGE-2, ROUGE-L (use rouge-score with stemming). Plus factuality check if abstractive.
4. One failure mode to probe. Entity swap is the most common in abstractive news summarization; flag samples where source entities do not appear in summary.

Refuse abstractive summarization for medical, legal, financial, or regulated content without a factuality gate. Flag input over the model's context window as needing chunked map-reduce summarization (not just truncation).
```

## 練習

1. **簡單。** 對 5 篇新聞跑 TextRank。把前三名的句子跟參考摘要比對，量測 ROUGE-L。在 CNN/DailyMail 風格的文章上，你應該會看到 30 到 45 的 ROUGE-L。
2. **中等。** 實作實體層級的事實查核：從來源與摘要中抽出命名實體（用 spaCy），計算來源實體在摘要中的召回率，以及摘要實體對照來源的精確率。精確率高、召回率低代表安全但過於精簡；精確率低則代表有幻覺出來的實體。
3. **困難。** 在 50 篇 CNN/DailyMail 文章上，把 BART-large-CNN 跟一個 LLM（Claude 或 GPT-4）比一比。報告 ROUGE-L、忠實度（以實體 F1 衡量）以及每份摘要的成本。記錄下各自贏在哪裡。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 抽取式摘要 | 「挑句子」 | 從來源逐字回傳句子。永遠不會幻覺。 |
| 生成式摘要 | 「重寫一遍」 | 以來源為條件生成新的文字。可能會幻覺。 |
| ROUGE | 「摘要的指標」 | 系統輸出與參考摘要之間的 n-gram／LCS 重疊程度。 |
| TextRank | 「基於圖的抽取式方法」 | 在句子相似度圖上跑 PageRank。 |
| 忠實度 | 「它到底對不對」 | 摘要中的主張是否有來源支持。 |
| 幻覺 | 「編出來的內容」 | 摘要裡出現、但來源並不支持的內容。 |

## 延伸閱讀

- [Mihalcea and Tarau (2004). TextRank: Bringing Order into Texts](https://aclanthology.org/W04-3252/) —— 抽取式摘要的經典論文。
- [Lewis et al. (2019). BART: Denoising Sequence-to-Sequence Pre-training](https://arxiv.org/abs/1910.13461) —— BART 論文。
- [Zhang et al. (2019). PEGASUS: Pre-training with Extracted Gap-sentences](https://arxiv.org/abs/1912.08777) —— Pegasus 與 gap-sentence 目標。
- [Lin (2004). ROUGE: A Package for Automatic Evaluation of Summaries](https://aclanthology.org/W04-1013/) —— ROUGE 論文。
- [Maynez et al. (2020). On Faithfulness and Factuality in Abstractive Summarization](https://arxiv.org/abs/2005.00661) —— 談忠實度全景的論文。
