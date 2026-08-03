# 主題模型 —— LDA 與 BERTopic

> LDA：文件是主題的混合，主題是詞上的分布。BERTopic：文件在嵌入空間裡聚成群，群就是主題。目標相同，拆解方式不同。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 02（BoW + TF-IDF）、階段 5 · 03（Word2Vec）
**時間：** 約 45 分鐘

## 問題所在

你手上有 10,000 張客服工單、50,000 篇新聞報導，或 200,000 則推文。你需要在不讀完它們的前提下，知道這批資料在講什麼。你沒有標好的類別，甚至不知道到底有幾個類別。

主題模型不需要監督就能回答這件事。餵給它一份語料，它會回傳一小組彼此連貫的主題，以及每份文件在這些主題上的分布。

主流有兩個演算法家族。LDA（2003）把每份文件視為潛在主題的混合，把每個主題視為詞上的分布，推論走貝氏路線。當你需要混合歸屬的主題指派、以及可解釋的詞層級機率分布時，它至今仍活在生產環境裡。

BERTopic（2020）用 BERT 編碼文件、用 UMAP 降維、用 HDBSCAN 分群，再用 class-based TF-IDF 抽出主題詞。在短文本、社群媒體，以及任何語意相似度比字詞重疊更重要的場景裡，它會勝出。一份文件只會得到一個主題，這對長篇內容是個限制。

這個單元會建立對兩者的直覺，並說清楚面對某份語料時該挑哪一個。

## 核心概念

![LDA 混合模型與 BERTopic 分群的對照](../assets/topic-modeling.svg)

**LDA 的生成過程。** 每個主題是詞上的分布。每份文件是主題的混合。要在一份文件裡生成一個詞，先從該文件的主題分布抽出一個主題，再從那個主題的詞分布抽出一個詞。推論則是把這個過程倒推回去：給定觀察到的詞，反推每份文件的主題分布與每個主題的詞分布。這段數學由 collapsed Gibbs sampling 或變分貝氏來完成。

LDA 的關鍵輸出：

- `doc_topic`：文件-主題矩陣 `(n_docs, n_topics)`，每一橫列加總為 1（該文件的主題混合）。
- `topic_word`：主題-詞矩陣 `(n_topics, vocab_size)`，每一橫列加總為 1（該主題的詞分布）。

**BERTopic 管線。**

1. 用 sentence transformer（例如 `all-MiniLM-L6-v2`）編碼每份文件，得到 384 維向量。
2. 用 UMAP 把維度降到約 5 維。BERT 嵌入的維度對分群來說太高了。
3. 用 HDBSCAN 分群。它基於密度，會產生大小不一的群，還有一個「離群」標籤。
4. 對每個群，在該群的文件上計算 class-based TF-IDF，抽出排名最前的詞。

輸出是每份文件一個主題（外加一個 -1 的離群標籤）。也可以透過 HDBSCAN 的機率向量得到軟性的歸屬程度。

```figure
topic-drift
```

## 動手實作

### 步驟 1：用 scikit-learn 跑 LDA

```python
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import numpy as np


def fit_lda(documents, n_topics=5, max_features=1000):
    cv = CountVectorizer(
        max_features=max_features,
        stop_words="english",
        min_df=2,
        max_df=0.9,
    )
    X = cv.fit_transform(documents)
    lda = LatentDirichletAllocation(
        n_components=n_topics,
        random_state=42,
        max_iter=50,
        learning_method="online",
    )
    doc_topic = lda.fit_transform(X)
    feature_names = cv.get_feature_names_out()
    return lda, cv, doc_topic, feature_names


def print_top_words(lda, feature_names, n_top=10):
    for idx, topic in enumerate(lda.components_):
        top_idx = np.argsort(-topic)[:n_top]
        words = [feature_names[i] for i in top_idx]
        print(f"topic {idx}: {' '.join(words)}")
```

留意幾件事：停用詞被移除了；min_df 與 max_df 會篩掉太罕見與到處都出現的詞；用的是 CountVectorizer（不是 TfidfVectorizer），因為 LDA 要的是原始計數。

### 步驟 2：BERTopic（生產環境）

```python
from bertopic import BERTopic

topic_model = BERTopic(
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    min_topic_size=15,
    verbose=True,
)

topics, probs = topic_model.fit_transform(documents)
info = topic_model.get_topic_info()
print(info.head(20))
valid_topics = info[info["Topic"] != -1]["Topic"].tolist()
for topic_id in valid_topics[:5]:
    print(f"topic {topic_id}: {topic_model.get_topic(topic_id)[:10]}")
```

`Topic != -1` 這個篩選會丟掉 BERTopic 的離群桶（HDBSCAN 分不進任何群的文件）。`min_topic_size` 控制 HDBSCAN 的最小群大小；BERTopic 函式庫的預設值是 10，這個範例為了配合本單元的資料規模，明確設成 15。語料超過 10,000 份文件時，調到 50 或 100。

### 步驟 3：評估

兩種方法都會輸出主題詞。問題在於這些詞彼此連貫嗎。

- **主題連貫性（c_v）。** 它在滑動視窗的脈絡上計算排名最前的詞兩兩之間的 NPMI（normalized pointwise mutual information），把分數彙整成主題向量，再用餘弦相似度比較這些向量。越高越好。用 `gensim.models.CoherenceModel` 並設 `coherence="c_v"`。
- **主題多樣性。** 所有主題的前排詞裡不重複詞所佔的比例。越高越好（表示主題之間不重疊）。
- **人工檢視。** 把每個主題的前排詞讀一遍。它們有指向某個真實存在的東西嗎？人的判斷仍是最後一道防線。

## 該選哪一個

| 情境 | 選擇 |
|-----------|------|
| 短文本（推文、評論、標題） | BERTopic |
| 帶有主題混合的長文件 | LDA |
| 沒有 GPU／算力有限 | LDA 或 NMF |
| 需要文件層級的多主題分布 | LDA |
| 要整合 LLM 做主題標籤指派 | BERTopic（原生支援） |
| 資源受限的邊緣部署 | LDA |
| 追求最高的語意連貫性 | BERTopic |

實務上最重要的考量是文件長度。BERT 嵌入會截斷；LDA 的計數則不管長度多少都能算。文件長度超過嵌入模型的脈絡長度時，要嘛切塊再彙整，要嘛改用 LDA。

## 框架應用

2026 年的技術堆疊：

- **BERTopic。** 短文本以及任何看重語意的場景的預設選擇。
- **`gensim.models.LdaModel`。** 經典的 LDA，適合生產環境，成熟且久經考驗。
- **`sklearn.decomposition.LatentDirichletAllocation`。** 做實驗時最好上手的 LDA。
- **NMF。** 非負矩陣分解。比 LDA 快的替代方案，在短文本上品質相當。
- **Top2Vec。** 設計思路和 BERTopic 類似。社群較小，但在某些基準上表現不錯。
- **FASTopic。** 較新，在超大語料上比 BERTopic 快。
- **以 LLM 做標籤指派。** 先跑任何一種分群，再提示模型替每個群命名。

## 產出交付

存成 `outputs/skill-topic-picker.md`：

```markdown
---
name: topic-picker
description: Pick LDA or BERTopic for a corpus. Specify library, knobs, evaluation.
version: 1.0.0
phase: 5
lesson: 15
tags: [nlp, topic-modeling]
---

Given a corpus description (document count, avg length, domain, language, compute budget), output:

1. Algorithm. LDA / NMF / BERTopic / Top2Vec / FASTopic. One-sentence reason.
2. Configuration. Number of topics: `recommended = max(5, round(sqrt(n_docs)))`, clamped to 200 for corpora under 40,000 docs; permit >200 only when the corpus is genuinely large (>40k) and note the increased compute cost. `min_df` / `max_df` filters and embedding model for neural approaches also belong here.
3. Evaluation. Topic coherence (c_v) via `gensim.models.CoherenceModel`, topic diversity, and a 20-sample human read.
4. Failure mode to probe. For LDA, "junk topics" absorbing stopwords and frequent terms. For BERTopic, the -1 outlier cluster swallowing ambiguous documents.

Refuse BERTopic on documents longer than the embedding model's context window without a chunking strategy. Refuse LDA on very short text (tweets, reviews under 10 tokens) as coherence collapses. Flag any n_topics choice below 5 as likely wrong; flag >200 on corpora under 40k docs as likely over-splitting.
```

## 練習

1. **簡單。** 在 20 Newsgroups 資料集上用 5 個主題訓練 LDA。印出每個主題排名前 10 的詞。手動替每個主題標上名稱。演算法有找出真正的類別嗎？
2. **中等。** 在同一份 20 Newsgroups 子集上訓練 BERTopic。把找到的主題數量、前排詞，以及人工判斷的連貫程度拿來和 LDA 比較。哪一個把真正的類別呈現得更乾淨？
3. **困難。** 在你的語料上分別計算 LDA 與 BERTopic 的 c_v 連貫性。各用 5、10、20、50 個主題跑一次。把連貫性對主題數畫成圖。回報哪一種方法在不同主題數下更穩定。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 主題 | 「語料在講的某件事」 | 詞上的一個機率分布（LDA），或一群相似文件所成的群（BERTopic）。 |
| 混合歸屬 | 「一份文件同時屬於多個主題」 | LDA 會給每份文件一個涵蓋所有主題的分布。 |
| UMAP | 「降維」 | 保留局部結構的流形學習；BERTopic 用它。 |
| HDBSCAN | 「密度分群」 | 找出大小不一的群；為離群值產生「雜訊」標籤（-1）。 |
| c_v 連貫性 | 「主題品質指標」 | 主題前排詞在滑動視窗內的平均逐點互資訊。 |

## 延伸閱讀

- [Blei, Ng, Jordan (2003). Latent Dirichlet Allocation](https://www.jmlr.org/papers/volume3/blei03a/blei03a.pdf) —— LDA 的原始論文。
- [Grootendorst (2022). BERTopic: Neural topic modeling with a class-based TF-IDF procedure](https://arxiv.org/abs/2203.05794) —— BERTopic 的論文。
- [Röder, Both, Hinneburg (2015). Exploring the Space of Topic Coherence Measures](https://svn.aksw.org/papers/2015/WSDM_Topic_Evaluation/public.pdf) —— 提出 c_v 及其同族指標的論文。
- [BERTopic documentation](https://maartengr.github.io/BERTopic/) —— 生產環境的參考文件，範例極好。
