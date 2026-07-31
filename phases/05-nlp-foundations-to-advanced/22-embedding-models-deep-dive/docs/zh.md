# 嵌入模型 —— 2026 深入解析

> Word2Vec 給你的是每個詞一個向量。現代嵌入模型給你的是每個段落一個向量，跨語言，同時具備稀疏、稠密與多向量三種視角，尺寸還能剪到剛好塞進你的索引。挑錯了，你的 RAG 就會檢索到錯的東西。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 03（Word2Vec）、階段 5 · 14（資訊檢索）
**時間：** 約 60 分鐘

## 問題所在

你的 RAG 系統有 40% 的機率檢索到錯的段落。兇手很少是向量資料庫或提示詞，而是嵌入模型。

在 2026 年挑一個嵌入模型，要在五個軸線上做選擇：

1. **稠密 vs 稀疏 vs 多向量。** 每個段落一個向量，或每個詞元一個向量，或一個帶權重的稀疏詞袋。
2. **語言覆蓋範圍。** 純英文模型在純英文任務上依然勝出。語料混雜時，多語言模型才贏。
3. **脈絡長度。** 512 詞元 vs 8,192 vs 32,768 —— 而真正的有效容量往往只有標稱上限的 60-70%。
4. **維度預算。** 3,072 個全精度浮點數 = 每個向量 12 KB。到了 1 億個向量，儲存成本就是每月 $1,300。Matryoshka 截斷可以把這個數字砍到四分之一。
5. **開源權重 vs 託管服務。** 開源權重意味著技術堆疊與資料都在你手上。託管服務則是用控制權換取「永遠是最新版」。

這個單元把各種取捨一一點名，讓你能靠證據來選，而不是靠上一季誰比較紅。

## 核心概念

![稠密、稀疏與多向量嵌入](../assets/embedding-modes.svg)

**稠密嵌入。** 每個段落一個向量（通常 384-3,072 維）。用餘弦相似度依語意距離替段落排序。OpenAI `text-embedding-3-large`、BGE-M3 的稠密模式、Voyage-3 都是這一類。預設選擇。

**稀疏嵌入。** SPLADE 這一路。一個 transformer 為詞彙表裡每個詞元預測一個權重，然後把大部分歸零。結果是一個長度為 |vocab| 的稀疏向量。它抓的是字面比對（像 BM25），但詞權重是學出來的。在關鍵字密集的查詢上很強。

**多向量（後期互動）。** ColBERTv2、Jina-ColBERT。每個詞元一個向量。用 MaxSim 評分：對每個查詢詞元，找出最相似的那個文件詞元，再把分數加總。儲存與評分都更貴，但在長查詢與領域專屬語料上勝出。

**BGE-M3：三種一次到位。** 同一個模型同時輸出稠密、稀疏與多向量三種表示。每一種都能獨立查詢，分數再用加權和融合。當你想從單一權重檔就拿到全部彈性時，這是 2026 年的預設答案。

**Matryoshka 表示學習。** 訓練方式讓向量的前 N 維自成一個好用的獨立嵌入。把 1,536 維的向量截斷到 256 維，用大約 1% 的準確率換來 6 倍的儲存節省。OpenAI text-3、Cohere v4、Voyage-4、Jina v5、Gemini Embedding 2、Nomic v1.5+ 都支援。

### MTEB 排行榜只說了一半的故事

Massive Text Embedding Benchmark —— 剛推出時（2022）是 8 種任務類型共 56 個任務，到 MTEB v2 擴增到 100 個以上。2026 年初，Gemini Embedding 2 在檢索項目居首（MTEB-R 67.71）。Cohere embed-v4 在綜合項目領先（MTEB 65.2）。BGE-M3 在開源權重多語言項目領先（63.0）。排行榜是必要條件，但不是充分條件 —— 永遠要在你自己的領域上跑基準測試。

### 三層式模式

| 使用情境 | 模式 |
|----------|---------|
| 快速的第一輪篩選 | 稠密 bi-encoder（BGE-M3、text-3-small） |
| 拉高召回率 | 稀疏（SPLADE、BGE-M3 稀疏模式）+ RRF 融合 |
| 前 50 名的精準率 | 多向量（ColBERTv2）或 cross-encoder 重排序器 |

多數生產環境的堆疊三層全用。

## 動手實作

### 步驟 1：基準線 —— 用 Sentence-BERT 做稠密嵌入

```python
from sentence_transformers import SentenceTransformer
import numpy as np

encoder = SentenceTransformer("BAAI/bge-small-en-v1.5")
corpus = [
    "The first iPhone launched in 2007.",
    "Apple released the iPod in 2001.",
    "Android is an operating system from Google.",
]
emb = encoder.encode(corpus, normalize_embeddings=True)

query = "When was the iPhone released?"
q_emb = encoder.encode([query], normalize_embeddings=True)[0]
scores = emb @ q_emb
print(sorted(enumerate(scores), key=lambda x: -x[1]))
```

`normalize_embeddings=True` 讓內積等於餘弦相似度。永遠要設。

### 步驟 2：Matryoshka 截斷

```python
def truncate(vectors, dim):
    out = vectors[:, :dim]
    return out / np.linalg.norm(out, axis=1, keepdims=True)

emb_256 = truncate(emb, 256)
emb_128 = truncate(emb, 128)
```

截斷後要重新正規化。Nomic v1.5、OpenAI text-3 與 Voyage-4 的訓練方式讓前幾階的維度縮減幾乎無損。非 Matryoshka 的模型（原版 Sentence-BERT）一被截斷就急遽退化。

### 步驟 3：BGE-M3 的多功能性

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

output = model.encode(
    corpus,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True,
)
# output["dense_vecs"]:    (n_docs, 1024)
# output["lexical_weights"]: list of dict {token_id: weight}
# output["colbert_vecs"]:  list of (n_tokens, 1024) arrays
```

三份索引，一次推論呼叫。分數融合：

```python
dense_score = ... # cosine over dense_vecs
sparse_score = model.compute_lexical_matching_score(q_lex, d_lex)
colbert_score = model.colbert_score(q_col, d_col)
final = 0.4 * dense_score + 0.2 * sparse_score + 0.4 * colbert_score
```

權重要在你自己的領域上調。

### 步驟 4：在自訂任務上跑 MTEB 評估

```python
from mteb import MTEB

tasks = ["ArguAna", "SciFact", "NFCorpus"]
evaluation = MTEB(tasks=tasks)
results = evaluation.run(encoder, output_folder="./mteb-results")
```

拿你的候選模型在一個*有代表性*的子集上跑。不要只信排行榜排名 —— 你的領域才是關鍵。

### 步驟 5：手工從零算餘弦相似度

見 `code/main.py`。用雜湊技巧（Hashing Trick）取平均得到的嵌入，只用標準函式庫。它比不上 transformer 嵌入，但把整個形狀攤了出來：分詞 → 向量 → 正規化 → 內積。

## 常見陷阱

- **查詢與文件用同一個模型。** 有些模型（Voyage、Jina-ColBERT）採用非對稱編碼 —— 查詢與文件走的是不同路徑。永遠要去查 model card。
- **漏掉前綴。** `bge-*` 系列模型的查詢前面必須加上 `"Represent this sentence for searching relevant passages: "` 這個指令前綴。忘了就是 3-5 個百分點的召回率落差。
- **Matryoshka 剪太狠。** 1,536 → 256 通常安全。1,536 → 64 就不安全了。要在你自己的評估集上驗證。
- **脈絡被截斷。** 多數模型會把超過長度上限的輸入靜默截掉。長文件需要分塊（見單元 23）。
- **忽略延遲的長尾。** MTEB 分數藏住了 p99 延遲。一個 600M 的模型可能比 335M 的模型高 2 分，但每次查詢貴 3 倍。

## 框架應用

2026 年的技術堆疊：

| 情境 | 選什麼 |
|-----------|------|
| 純英文、要快、走 API | `text-embedding-3-large` 或 `voyage-3-large` |
| 開源權重、英文 | `BAAI/bge-large-en-v1.5` |
| 開源權重、多語言 | `BAAI/bge-m3` 或 `Qwen3-Embedding-8B` |
| 長脈絡（32k 以上） | Voyage-3-large、Cohere embed-v4、Qwen3-Embedding-8B |
| 純 CPU 部署 | Nomic Embed v2（137M 參數，MoE） |
| 儲存空間受限 | Matryoshka 截斷 + int8 量化 |
| 關鍵字密集的查詢 | 加上 SPLADE 稀疏檢索，與稠密檢索做 RRF 融合 |

2026 年的做法：先從 BGE-M3 或 text-3-large 開始，用 MTEB 在你的領域上評估，若某個領域專屬模型贏超過 3 分就換過去。

## 產出交付

存成 `outputs/skill-embedding-picker.md`：

```markdown
---
name: embedding-picker
description: Pick embedding model, dimension, and retrieval mode for a given corpus and deployment.
version: 1.0.0
phase: 5
lesson: 22
tags: [nlp, embeddings, retrieval]
---

Given a corpus (size, languages, domain, avg length), deployment target (cloud / edge / on-prem), latency budget, and storage budget, output:

1. Model. Named checkpoint or API. One-sentence reason.
2. Dimension. Full / Matryoshka-truncated / int8-quantized. Reason tied to storage budget.
3. Mode. Dense / sparse / multi-vector / hybrid. Reason.
4. Query prefix / template if required by the model card.
5. Evaluation plan. MTEB tasks relevant to domain + held-out domain eval with nDCG@10.

Refuse recommendations that truncate Matryoshka to <64 dims without domain validation. Refuse ColBERTv2 for corpora under 10k passages (overhead not justified). Flag long-document corpora (>8k tokens) routed to models with 512-token windows.
```

## 練習

1. **簡單。** 用 `bge-small-en-v1.5` 以完整維度（384）編碼 100 個句子，再用 Matryoshka 128 維編碼一次。在 10 個查詢上量出 MRR 掉了多少。
2. **中等。** 在你自己領域的 500 個段落上比較 BGE-M3 的稠密、稀疏與 colbert 三種模式。召回率@10 是哪一種贏？RRF 融合有贏過表現最好的單一模式嗎？
3. **困難。** 拿三個候選模型在你領域最相關的兩個任務上跑 MTEB。回報 MTEB 分數、100 個查詢批次的 p99 延遲，以及每百萬次查詢的成本。挑出柏拉圖最優的那一個。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 稠密嵌入 | 「那個向量」 | 每段文字一個固定長度的向量。用餘弦相似度排序。 |
| 稀疏嵌入 | 「學出來的 BM25」 | 詞彙表每個詞元一個權重；大部分是零；端到端訓練出來。 |
| 多向量 | 「ColBERT 那一套」 | 每個詞元一個向量；用 MaxSim 評分；索引更大，召回率更好。 |
| Matryoshka | 「俄羅斯娃娃那招」 | 前 N 維自己就是一個有效的小號嵌入。 |
| MTEB | 「那個基準測試」 | Massive Text Embedding Benchmark —— 剛推出時 56 個任務，v2 有 100 個以上。 |
| BEIR | 「檢索的基準測試」 | 18 個零樣本檢索任務；常被引用來談跨領域的穩健度。 |
| 非對稱編碼 | 「查詢 ≠ 文件路徑」 | 模型對查詢與文件使用不同的投影。 |

## 延伸閱讀

- [Reimers, Gurevych (2019). Sentence-BERT](https://arxiv.org/abs/1908.10084) —— bi-encoder 的那篇論文。
- [Muennighoff et al. (2022). MTEB: Massive Text Embedding Benchmark](https://arxiv.org/abs/2210.07316) —— 排行榜的那篇論文。
- [Chen et al. (2024). BGE-M3: Multi-lingual, Multi-functionality, Multi-granularity](https://arxiv.org/abs/2402.03216) —— 把三種模式統一起來的模型。
- [Kusupati et al. (2022). Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147) —— 維度階梯的訓練目標。
- [Santhanam et al. (2022). ColBERTv2: Effective and Efficient Retrieval via Lightweight Late Interaction](https://arxiv.org/abs/2112.01488) —— 後期互動在生產環境的樣子。
- [MTEB leaderboard on Hugging Face](https://huggingface.co/spaces/mteb/leaderboard) —— 即時排名。
