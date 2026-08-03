# 資訊檢索與搜尋

> BM25 精準但脆弱。稠密檢索網撒得寬，卻抓不到關鍵字。混合檢索是 2026 年的預設答案。其餘都只是調參。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 02（BoW + TF-IDF）、階段 5 · 04（GloVe、FastText 與子詞）
**時間：** 約 75 分鐘

## 問題所在

使用者輸入「what happens if someone lies to get money」，期待找到真正涵蓋這件事的法條：「Section 420 IPC」。關鍵字搜尋完全找不到（沒有共用的詞彙）。語意搜尋也會漏掉，只要嵌入模型沒在法律文本上訓練過。真實的搜尋必須同時處理這兩種情況。

資訊檢索是每一套 RAG 系統、每一個搜尋框、每個文件網站模糊查詢底下的那條流水線。2026 年真正能上生產環境的架構不是單一方法，而是一連串互補的方法串起來，每一環都接住上一環漏掉的失敗。

這個單元會逐一實作每個環節，並點明各自接住的是哪一類失敗。

## 核心概念

![混合檢索：BM25 + 稠密檢索 + RRF + cross-encoder 重排序](../assets/retrieval.svg)

四層。挑你需要的那幾層。

1. **稀疏檢索（BM25）。** 快、在完全比對上很精準、在語意上很糟糕。跑在倒排索引上。數百萬份文件也能做到每次查詢 10ms 以內。法條編號、產品代碼、錯誤訊息、具名實體都靠它抓對。
2. **稠密檢索。** 把查詢與文件編碼成向量，做最近鄰搜尋。抓得到換句話說與語意相似度。會漏掉只差一個字元的完全關鍵字比對。用 FAISS 或向量資料庫的話，每次查詢 50-200ms。
3. **融合。** 把稀疏與稠密各自的排序清單合併起來。Reciprocal Rank Fusion（RRF）是最省事的預設選擇，因為它不看原始分數（兩邊的分數尺度根本不同），只看排名位置。當你明確知道某個訊號在你的領域裡佔主導地位時，加權融合也是一個選項。
4. **cross-encoder 重排序。** 取融合後的前 30 名，跑一個 cross-encoder（查詢與文件一起送進去，對每個配對評分），只留前 5 名。cross-encoder 每個配對的速度比 bi-encoder 慢得多，但準確率高得多。只在前 30 名上跑，成本就攤平了。

三路檢索（BM25 + 稠密檢索 + SPLADE 這類學習式稀疏檢索）在 2026 年的基準測試上勝過兩路，但需要有學習式稀疏索引的基礎設施。對多數團隊來說，兩路加上 cross-encoder 重排序才是甜蜜點。

```figure
gx-hybrid-retrieval
```

## 動手實作

### 步驟 1：從零實作 BM25

```python
import math
import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text):
    return TOKEN_RE.findall(text.lower())


class BM25:
    def __init__(self, corpus, k1=1.5, b=0.75):
        if not corpus:
            raise ValueError("corpus must not be empty")
        self.corpus = [tokenize(d) for d in corpus]
        self.k1 = k1
        self.b = b
        self.n_docs = len(self.corpus)
        self.avg_dl = sum(len(d) for d in self.corpus) / self.n_docs
        self.df = Counter()
        for doc in self.corpus:
            for term in set(doc):
                self.df[term] += 1

    def idf(self, term):
        n = self.df.get(term, 0)
        return math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5))

    def score(self, query, doc_idx):
        q_tokens = tokenize(query)
        doc = self.corpus[doc_idx]
        dl = len(doc)
        freq = Counter(doc)
        score = 0.0
        for term in q_tokens:
            f = freq.get(term, 0)
            if f == 0:
                continue
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
            score += self.idf(term) * numerator / denominator
        return score

    def rank(self, query, top_k=10):
        scored = [(self.score(query, i), i) for i in range(self.n_docs)]
        scored.sort(reverse=True)
        return scored[:top_k]
```

有兩個參數值得認識。`k1=1.5` 控制詞頻飽和；值越高，詞的重複出現就越有份量。`b=0.75` 控制長度正規化；0 表示完全不管文件長度，1 表示完全正規化。這兩個預設值是原始論文裡 Robertson 的建議，很少需要調。

### 步驟 2：用 bi-encoder 做稠密檢索

```python
from sentence_transformers import SentenceTransformer
import numpy as np


def build_dense_index(corpus, model_id="sentence-transformers/all-MiniLM-L6-v2"):
    encoder = SentenceTransformer(model_id)
    embeddings = encoder.encode(corpus, normalize_embeddings=True)
    return encoder, embeddings


def dense_search(encoder, embeddings, query, top_k=10):
    q_emb = encoder.encode([query], normalize_embeddings=True)
    sims = (embeddings @ q_emb.T).flatten()
    order = np.argsort(-sims)[:top_k]
    return [(float(sims[i]), int(i)) for i in order]
```

把嵌入做 L2 正規化，內積就等於餘弦相似度。`all-MiniLM-L6-v2` 是 384 維、速度快，對多數英文檢索已經夠強。要做多語言就用 `paraphrase-multilingual-MiniLM-L12-v2`。要頂級準確率就用 `bge-large-en-v1.5` 或 `e5-large-v2`。

### 步驟 3：Reciprocal Rank Fusion

```python
def reciprocal_rank_fusion(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, (_, doc_idx) in enumerate(ranking):
            scores[doc_idx] = scores.get(doc_idx, 0.0) + 1.0 / (k + rank + 1)
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(score, doc_idx) for doc_idx, score in fused]
```

`k=60` 這個常數來自 RRF 的原始論文。`k` 越大，排名差異的貢獻就越被壓平；`k` 越小，頂端排名就越主導結果。60 是論文公布的預設值，很少需要調。

### 步驟 4：混合檢索 + 重排序

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def hybrid_search(query, bm25, encoder, dense_embeddings, corpus, top_k=5, pool_size=30, reranker=reranker):
    sparse_ranking = bm25.rank(query, top_k=pool_size)
    dense_ranking = dense_search(encoder, dense_embeddings, query, top_k=pool_size)
    fused = reciprocal_rank_fusion([sparse_ranking, dense_ranking])[:pool_size]

    pairs = [(query, corpus[doc_idx]) for _, doc_idx in fused]
    scores = reranker.predict(pairs)
    reranked = sorted(zip(scores, [doc_idx for _, doc_idx in fused]), reverse=True)
    return reranked[:top_k]
```

三個階段組起來。BM25 找出字面比對。稠密檢索找出語意比對。RRF 把兩份排序合併，不需要校正分數。cross-encoder 把查詢與文件成對送進去，替前 30 名重新評分，抓回 bi-encoder 漏掉的細粒度相關性。留前 5 名。

### 步驟 5：評估

| 指標 | 意義 |
|--------|---------|
| 召回率@k | 在正確文件確實存在的查詢中，它有多常出現在前 k 名裡？ |
| MRR（平均倒數排名） | 第一份相關文件排名倒數 1/rank 的平均值。 |
| nDCG@k | 把相關性的分級也算進去，而不只是相關／不相關的二元判斷。 |

專門就 RAG 而言，檢索器的 **召回率@k** 是最重要的那個數字。正確的段落沒進到檢索結果裡，你的閱讀模型就答不出來。

除錯訣竅：對失敗的查詢，把稀疏與稠密的排序拿來對比。如果一邊找到了正確文件、另一邊沒找到，那你碰上的是詞彙不匹配（解法：把缺的那一半補上），或是語意歧義（解法：換更好的嵌入模型，或加一個重排序器）。

## 框架應用

2026 年的技術堆疊：

| 規模 | 堆疊 |
|-------|-------|
| 1k-100k 份文件 | 記憶體內的 BM25 + `all-MiniLM-L6-v2` 嵌入 + RRF。不需要獨立的資料庫。 |
| 100k-10M 份文件 | 稠密檢索用 FAISS 或 pgvector + BM25 用 Elasticsearch／OpenSearch。平行跑。 |
| 10M+ 份文件 | 支援混合檢索的 Qdrant／Weaviate／Vespa／Milvus。在前 30 名上做 cross-encoder 重排序。 |
| 追求最佳品質的前沿做法 | 三路（BM25 + 稠密檢索 + SPLADE）+ ColBERT 後期互動重排序 |

不管你選哪一套，都要為評估留預算。先把檢索召回率量出基準，再去量端到端的 RAG 準確率。檢索器漏掉的東西，閱讀模型補不回來。

### 2026 年生產環境 RAG 的血淚教訓

- **80% 的 RAG 失敗可以追溯到資料匯入與分塊，而不是模型。** 團隊花好幾週換 LLM、調提示詞，同時檢索每三次查詢就悄悄回傳錯誤的脈絡。先修分塊。
- **分塊策略比區塊大小更重要。** 固定大小的切分會切壞表格、程式碼與嵌套標題。以句子為界是預設做法；技術文件與產品手冊則值得用語意或 LLM 式的分塊。
- **父文件模式。** 檢索小的「子」區塊以求精準。當同一個父段落底下有多個子區塊同時命中時，就換成整個父區塊，把脈絡保留下來。這個做法不用重新訓練就能穩定拉高答案品質。
- **`k_rerank=3` 通常是最佳值。** 超過這個數的每一個區塊都在增加詞元成本與生成延遲，卻沒讓答案品質變好。如果對你來說 k=8 還是比 k=3 好，那是重排序器表現不夠力。
- **HyDE／查詢擴展。** 從查詢生成一個假設性答案，把它嵌入，再拿去檢索。這座橋接起了短問題與長文件之間的措辭落差。不用訓練就能免費換到精準度。
- **脈絡預算控制在 8K 詞元以內。** 老是頂到這個上限，代表重排序器的門檻放得太鬆。
- **所有東西都要版本控管。** 提示詞、分塊規則、嵌入模型、重排序器。任何漂移都會悄悄破壞答案品質。把 CI 閘門設在忠實度、脈絡精確率與答不出來的比率上，能在使用者看到之前就攔住回歸。
- **三路檢索（BM25 + 稠密檢索 + SPLADE 這類學習式稀疏檢索）勝過兩路**，這是 2026 年基準測試的結果，在專有名詞與語意混雜的查詢上尤其明顯。等基礎設施撐得起 SPLADE 索引就上線它。

依 2026 年的業界量測，把檢索設計做對可以讓幻覺減少 70-90%。RAG 的效能進步大多來自更好的檢索，而不是模型微調。

## 產出交付

存成 `outputs/skill-retrieval-picker.md`：

```markdown
---
name: retrieval-picker
description: Pick a retrieval stack for a given corpus and query pattern.
version: 1.0.0
phase: 5
lesson: 14
tags: [nlp, retrieval, rag, search]
---

Given requirements (corpus size, query pattern, latency budget, quality bar, infra constraints), output:

1. Stack. BM25 only, dense only, hybrid (BM25 + dense + RRF), hybrid + cross-encoder rerank, or three-way (BM25 + dense + learned-sparse).
2. Dense encoder. Name the specific model. Match to language(s), domain, and context length.
3. Reranker. Name the specific cross-encoder model if used. Flag that rerank adds 30-100ms latency on top-30.
4. Evaluation plan. Recall@10 is the primary retriever metric. MRR for multi-answer. Baseline first, incremental improvements measured against it.

Refuse to recommend dense-only for corpora with named entities, error codes, or product SKUs unless the user has evidence dense handles exact matches. Refuse to skip reranking for high-stakes retrieval (legal, medical) where the final top-5 decides the user's answer.
```

## 練習

1. **簡單。** 在一個 500 份文件的語料庫上實作上面的 `hybrid_search`。測 20 個查詢。比較只用 BM25、只用稠密檢索、以及混合檢索三者在前 5 名的召回率。
2. **中等。** 加上 MRR 的計算。對每個已知正確文件的測試查詢，找出正確文件在 BM25、稠密檢索與混合檢索三份排序裡各排第幾名。分別回報三者的 MRR。
3. **困難。** 用 MultipleNegativesRankingLoss（Sentence Transformers）在你自己的領域上微調一個稠密編碼器。從 500 組查詢-文件配對建出訓練集。比較微調前後的召回率。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| BM25 | 「關鍵字搜尋」 | Okapi BM25。用詞頻、IDF 與長度來給文件評分。 |
| 稠密檢索 | 「向量搜尋」 | 把查詢與文件編碼成向量，找最近鄰。 |
| bi-encoder | 「嵌入模型」 | 分別獨立編碼查詢與文件。查詢時很快。 |
| cross-encoder | 「重排序模型」 | 把查詢與文件一起編碼。慢，但準。 |
| RRF | 「排序融合」 | 把 `1/(k + rank)` 加總起來，合併兩份排序。 |
| 召回率@k | 「檢索指標」 | 相關文件出現在前 k 名的查詢所佔的比例。 |

## 延伸閱讀

- [Robertson and Zaragoza (2009). The Probabilistic Relevance Framework: BM25 and Beyond](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf) —— BM25 最權威的完整論述。
- [Karpukhin et al. (2020). Dense Passage Retrieval for Open-Domain QA](https://arxiv.org/abs/2004.04906) —— DPR，bi-encoder 的正典。
- [Formal et al. (2021). SPLADE: Sparse Lexical and Expansion Model](https://arxiv.org/abs/2107.05720) —— 把差距追上稠密檢索的學習式稀疏檢索器。
- [Cormack, Clarke, Büttcher (2009). Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) —— RRF 論文。
- [Khattab and Zaharia (2020). ColBERT: Efficient and Effective Passage Search](https://arxiv.org/abs/2004.12832) —— 後期互動檢索。
