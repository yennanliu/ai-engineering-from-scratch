# RAG 的切塊策略

> 切塊的設定對檢索品質的影響，跟挑哪個嵌入模型一樣大（Vectara NAACL 2025）。切塊做壞了，再多的重排序也救不回來。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 14（資訊檢索）、階段 5 · 22（嵌入模型）
**時間：** 約 60 分鐘

## 問題所在

你把一份 50 頁的合約丟進 RAG 系統。使用者問：「終止條款是什麼？」檢索器回傳的是封面頁。為什麼？因為模型是在 512 詞元的區塊上訓練的，而終止條款藏在第 20 頁之後，還被分頁切成兩半，附近沒有任何關鍵字能跟查詢對上。

解法不是「換一個更好的嵌入模型」。解法是切塊。切塊大小要多大？要不要重疊？要在哪裡切？要不要帶上周圍的上下文？

2026 年 2 月的基準測試結果出人意料：

- Vectara 2026 年的研究：遞迴切塊（512 詞元）以 69% 對 54% 的準確率打贏語意切塊。
- SPLADE + Mistral-8B 在 Natural Questions 上：重疊帶來的效益量不出來，等於零。
- 上下文懸崖：上下文一旦來到 2,500 詞元左右，回應品質就急遽下滑。

「顯而易見」的那個答案（語意切塊、20% 重疊、1000 詞元）往往是錯的。這個單元會把六種策略的直覺建立起來，並告訴你什麼時候該伸手拿哪一種。

## 核心概念

![六種切塊策略在同一段文字上的視覺化對照](../assets/chunking.svg)

**固定長度切塊。** 每 N 個字元或詞元切一刀。最簡單的基準線。會切在句子中間。壓縮效率好，連貫性差。

**遞迴切塊。** LangChain 的 `RecursiveCharacterTextSplitter`。先試著用 `\n\n` 切，切不動就用 `\n`，再不行用 `.`，最後用空白。逐級退讓得很乾淨。2026 年的預設選擇。

**語意切塊。** 把每個句子嵌入，算相鄰句子之間的餘弦相似度，在相似度掉到門檻以下的地方切開。能保住主題的連貫性。比較慢；有時候會生出 40 詞元的碎片，反而傷害檢索。

**依句子切塊。** 以句子邊界切。一個區塊一個句子，或一個 N 句的滑動窗口。在約 5k 詞元以內，效果追得上語意切塊，成本卻只是零頭。

**父子區塊（parent-document）。** 存小的子區塊供檢索，*同時*存較大的父區塊供上下文。用子區塊檢索，回傳父區塊。退化得很優雅：子區塊切得不好，回傳的父區塊依然堪用。

**後期切塊（2024）。** 先在詞元層級把整份文件嵌入，再把詞元嵌入池化成區塊嵌入。跨區塊的上下文因此被保留下來。要搭配長上下文的嵌入模型（BGE-M3、Jina v3）。運算量較高。

**上下文化檢索（Anthropic，2024）。** 在每個區塊前面加上一段由 LLM 生成的摘要，說明它在文件裡的位置（「這個區塊是終止條款的第 3.2 節……」）。在 Anthropic 自己的基準測試裡讓檢索改善 35-50%。建索引很貴。

### 打敗所有預設值的那條規則

讓切塊大小去配合查詢的類型：

| 查詢類型 | 切塊大小 |
|------------|-----------|
| 事實型查詢（「執行長叫什麼名字？」） | 256-512 詞元 |
| 分析型／多跳查詢 | 512-1024 詞元 |
| 整節理解 | 1024-2048 詞元 |

出自 NVIDIA 2026 年的基準測試。區塊要大到足以裝進答案加上周圍的上下文，同時又要小到讓檢索器的前 K 名聚焦在答案上，而不是被上下文的雜訊佔滿。

## 動手實作

### 步驟 1：固定長度切塊與遞迴切塊

```python
def chunk_fixed(text, size=512, overlap=0):
    step = size - overlap
    return [text[i:i + size] for i in range(0, len(text), step)]


def chunk_recursive(text, size=512, seps=("\n\n", "\n", ". ", " ")):
    if len(text) <= size:
        return [text]
    for sep in seps:
        if sep not in text:
            continue
        parts = text.split(sep)
        chunks = []
        buf = ""
        for p in parts:
            if len(p) > size:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(chunk_recursive(p, size=size, seps=seps[1:] or (" ",)))
                continue
            candidate = buf + sep + p if buf else p
            if len(candidate) <= size:
                buf = candidate
            else:
                if buf:
                    chunks.append(buf)
                buf = p
        if buf:
            chunks.append(buf)
        return [c for c in chunks if c.strip()]
    return chunk_fixed(text, size)
```

### 步驟 2：語意切塊

```python
def chunk_semantic(text, encoder, threshold=0.6, min_chars=200, max_chars=2048):
    sentences = split_sentences(text)
    if not sentences:
        return []
    embs = encoder.encode(sentences, normalize_embeddings=True)
    chunks = [[sentences[0]]]
    for i in range(1, len(sentences)):
        sim = float(embs[i] @ embs[i - 1])
        current_len = sum(len(s) for s in chunks[-1])
        if sim < threshold and current_len >= min_chars:
            chunks.append([sentences[i]])
        else:
            chunks[-1].append(sentences[i])

    result = []
    for group in chunks:
        text_group = " ".join(group)
        if len(text_group) > max_chars:
            result.extend(chunk_recursive(text_group, size=max_chars))
        else:
            result.append(text_group)
    return result
```

`threshold` 要在你自己的領域上調。太高會切出碎片，太低會變成一個巨大的區塊。

### 步驟 3：父子區塊

```python
def chunk_parent_child(text, parent_size=2048, child_size=256):
    parents = chunk_recursive(text, size=parent_size)
    mapping = []
    for p_idx, parent in enumerate(parents):
        children = chunk_recursive(parent, size=child_size)
        for child in children:
            mapping.append({"child": child, "parent_idx": p_idx, "parent": parent})
    return mapping


def retrieve_parent(child_query, mapping, encoder, top_k=3):
    child_embs = encoder.encode([m["child"] for m in mapping], normalize_embeddings=True)
    q_emb = encoder.encode([child_query], normalize_embeddings=True)[0]
    scores = child_embs @ q_emb
    top = np.argsort(-scores)[:top_k]
    seen, parents = set(), []
    for i in top:
        if mapping[i]["parent_idx"] not in seen:
            parents.append(mapping[i]["parent"])
            seen.add(mapping[i]["parent_idx"])
    return parents
```

關鍵心法：父區塊要去重。多個子區塊可能對到同一個父區塊，全都回傳只是在浪費上下文。

### 步驟 4：上下文化檢索（Anthropic 的模式）

```python
def contextualize_chunks(document, chunks, llm):
    context_prompts = [
        f"""<document>{document}</document>
Here is the chunk to situate: <chunk>{c}</chunk>
Write 50-100 words placing this chunk in the document's context."""
        for c in chunks
    ]
    contexts = llm.batch(context_prompts)
    return [f"{ctx}\n\n{c}" for ctx, c in zip(contexts, chunks)]
```

拿上下文化之後的區塊去建索引。查詢時，檢索就能受益於這些額外的周邊訊號。

### 步驟 5：評估

```python
def recall_at_k(queries, corpus_chunks, encoder, k=5):
    chunk_embs = encoder.encode(corpus_chunks, normalize_embeddings=True)
    hits = 0
    for q_text, gold_idxs in queries:
        q_emb = encoder.encode([q_text], normalize_embeddings=True)[0]
        top = np.argsort(-(chunk_embs @ q_emb))[:k]
        if any(i in gold_idxs for i in top):
            hits += 1
    return hits / len(queries)
```

永遠要自己量。對你的語料庫來說「最好」的策略，可能跟任何一篇部落格文章講的都不一樣。

## 常見陷阱

- **只用事實型查詢來評估切塊。** 換成多跳查詢，贏家完全不同。評估集要按查詢類型分層。
- **語意切塊沒設最小長度。** 會生出 40 詞元的碎片，反而傷害檢索。一律強制 `min_tokens`。
- **把重疊當成拜物教。** 2026 年的研究發現重疊往往一點效益都沒有，索引成本卻翻倍。要量，不要猜。
- **沒有最小／最大值的約束。** 5 個詞元的區塊和 5000 個詞元的區塊都會弄壞檢索。夾住它。
- **跨文件切塊。** 絕不能讓一個區塊橫跨兩份文件。一律逐份文件切塊，之後再合併。

## 框架應用

2026 年的技術堆疊：

| 情境 | 策略 |
|-----------|----------|
| 第一次建，語料庫還不熟 | 遞迴切塊，512 詞元，不重疊 |
| 事實型問答 | 遞迴切塊，256-512 詞元 |
| 分析型／多跳 | 遞迴切塊，512-1024 詞元 + 父子區塊 |
| 大量交叉引用（合約、論文） | 後期切塊或上下文化檢索 |
| 對話語料庫 | 以發話輪次為區塊 + 講者中介資料 |
| 短文本（推文、評論） | 一份文件就是一個區塊 |

從遞迴切塊 512 開始。在一個 50 題的評估集上量 recall@5。再從那裡往下調。

## 產出交付

存成 `outputs/skill-chunker.md`：

```markdown
---
name: chunker
description: Pick a chunking strategy, size, and overlap for a given corpus and query distribution.
version: 1.0.0
phase: 5
lesson: 23
tags: [nlp, rag, chunking]
---

Given a corpus (document types, avg length, domain) and query distribution (factoid / analytical / multi-hop), output:

1. Strategy. Recursive / sentence / semantic / parent-document / late / contextual. Reason.
2. Chunk size. Token count. Reason tied to query type.
3. Overlap. Default 0; justify if >0.
4. Min/max enforcement. `min_tokens`, `max_tokens` guards.
5. Evaluation plan. Recall@5 on 50-query stratified eval set (factoid, analytical, multi-hop).

Refuse any chunking strategy without min/max chunk size enforcement. Refuse overlap above 20% without an ablation showing it helps. Flag semantic chunking recommendations without a min-token floor.
```

## 練習

1. **簡單。** 用 fixed(512, 0)、recursive(512, 0) 與 recursive(512, 100) 各切一份 20 頁的文件。比較區塊數量與切點的品質。
2. **中等。** 在 5 份文件上做一個 30 題的評估集。分別量遞迴切塊、語意切塊與父子區塊的 recall@5。哪個贏？跟部落格文章講的一樣嗎？
3. **困難。** 實作上下文化檢索。量它相對於遞迴切塊基準線的 MRR 改善。回報建索引的成本（LLM 呼叫次數）對上準確率的收益。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 區塊（chunk） | 「文件的一小片」 | 被嵌入、建索引、檢索的次文件單位。 |
| 重疊 | 「安全邊界」 | 相鄰區塊之間共用的 N 個詞元；在 2026 年的基準測試裡往往沒用。 |
| 語意切塊 | 「聰明的切塊」 | 在相鄰句子的嵌入相似度下降處切開。 |
| 父子區塊 | 「兩層檢索」 | 檢索小的子區塊，回傳較大的父區塊。 |
| 後期切塊 | 「先嵌入再切塊」 | 在詞元層級嵌入整份文件，再池化成區塊向量。 |
| 上下文化檢索 | 「Anthropic 的招式」 | 建索引前，把 LLM 生成的摘要加在每個區塊前面。 |
| 上下文懸崖 | 「2500 詞元的牆」 | RAG 中在約 2.5k 上下文詞元處觀察到的品質下滑（2026 年 1 月）。 |

## 延伸閱讀

- [Yepes et al. / LangChain — Recursive Character Splitting docs](https://python.langchain.com/docs/how_to/recursive_text_splitter/) —— 生產環境的預設做法。
- [Vectara (2024, NAACL 2025). Chunking configurations analysis](https://arxiv.org/abs/2410.13070) —— 切塊的重要性跟挑嵌入模型一樣大。
- [Jina AI — Late Chunking in Long-Context Embedding Models (2024)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) —— 後期切塊的論文。
- [Anthropic — Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) —— 用 LLM 生成的上下文前綴換到 35-50% 的檢索改善。
- [NVIDIA 2026 chunk-size benchmark — Premai summary](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/) —— 依查詢類型決定切塊大小。
