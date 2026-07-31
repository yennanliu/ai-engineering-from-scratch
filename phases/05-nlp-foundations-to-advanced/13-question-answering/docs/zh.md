# 問答系統

> 有三種系統塑造了現代的問答技術。抽取式找出跨度，檢索增強把答案錨定在文件上，生成式直接產生答案。今天每一個 AI 助理都是這三者的混合。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 11（機器翻譯）、階段 5 · 10（注意力機制）
**時間：** 約 75 分鐘

## 問題所在

使用者打進「第一支 iPhone 什麼時候上市？」，他期待看到的是「2007 年 6 月 29 日」。不是「Apple 的歷史悠久而多變」。也不是一個孤零零沒有句子的「2007」。他要的是直接、有依據、而且正確的答案。

過去十年，問答領域由三種架構主導。

- **抽取式問答。** 給定一個問題，以及一段已知含有答案的上下文段落，找出答案跨度在段落中的起始與結束索引。SQuAD 是這個任務的經典基準。
- **開放領域問答。** 段落不會直接給你。先檢索出相關段落，再從中抽取或生成答案。這是今天每一條 RAG 流程的地基。
- **生成式／封閉式問答。** 由一個大型語言模型憑參數記憶作答。沒有檢索。推論最快，但在事實上最不可靠。

2026 年的趨勢是混合：先檢索出最好的幾段段落，再提示一個生成模型基於這些段落作答。這就是 RAG，第 14 單元會深入講檢索那一半。本單元負責問答那一半。

## 核心概念

![問答架構：抽取式、檢索增強、生成式](../assets/qa.svg)

**抽取式。** 用一個 transformer（BERT 系列）把問題與段落一起編碼。訓練兩個預測頭，分別預測答案的起始與結束詞元索引。損失是所有合法位置上的交叉熵。輸出是段落裡的一段跨度。它在結構上就不會幻覺，也在結構上處理不了段落無法回答的問題。

**檢索增強（RAG）。** 分兩個階段。第一，檢索器從語料庫中找出前 `k` 段段落。第二，閱讀器（抽取式或生成式）利用這些段落產生答案。檢索器與閱讀器分開，讓兩邊可以各自訓練、各自評估。現代的 RAG 常常在兩者之間再加一個重排器。

**生成式。** 一個純解碼器的 LLM（GPT、Claude、Llama）憑學到的權重作答。沒有檢索步驟。在常識上表現優異，在罕見或最新的事實上則慘不忍睹。幻覺率與該事實在預訓練資料中出現的頻率成反比。

## 動手實作

### 步驟 1：用預訓練模型做抽取式問答

```python
from transformers import pipeline

qa = pipeline("question-answering", model="deepset/roberta-base-squad2")

passage = (
    "Apple Inc. released the first iPhone on June 29, 2007. "
    "The device was announced by Steve Jobs at Macworld in January 2007."
)
question = "When was the first iPhone released?"

answer = qa(question=question, context=passage)
print(answer)
```

```python
{'score': 0.98, 'start': 57, 'end': 70, 'answer': 'June 29, 2007'}
```

`deepset/roberta-base-squad2` 是在 SQuAD 2.0 上訓練的，那份資料包含無答案的問題。預設情況下，`question-answering` pipeline 就算模型的 null 分數勝出，也一樣會回傳分數最高的那段跨度——它*不會*自動回傳空答案。要拿到明確的「無答案」行為，呼叫時要傳入 `handle_impossible_answer=True`：這樣一來，只有在 null 分數超過所有跨度分數時，pipeline 才會回傳空答案。不論用哪種方式，`score` 欄位都一定要檢查。

### 步驟 2：檢索增強流程（草圖）

```python
from sentence_transformers import SentenceTransformer
import numpy as np

encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

corpus = [
    "Apple Inc. released the first iPhone on June 29, 2007.",
    "Macworld 2007 featured the iPhone announcement by Steve Jobs.",
    "Android launched in 2008 as Google's mobile operating system.",
    "The first iPod was released in 2001.",
]
corpus_embeddings = encoder.encode(corpus, normalize_embeddings=True)


def retrieve(question, top_k=2):
    q_emb = encoder.encode([question], normalize_embeddings=True)
    sims = (corpus_embeddings @ q_emb.T).squeeze()
    order = np.argsort(-sims)[:top_k]
    return [corpus[i] for i in order]


def answer(question):
    passages = retrieve(question, top_k=2)
    combined = " ".join(passages)
    return qa(question=question, context=combined)


print(answer("When was the first iPhone released?"))
```

兩階段的流程。稠密檢索器（Sentence-BERT）靠語意相似度找出相關段落。抽取式閱讀器（RoBERTa-SQuAD）從合併後的頂端段落裡拉出答案跨度。這在小語料上行得通。若語料有上百萬份文件，請改用 FAISS 或向量資料庫。

### 步驟 3：搭配 RAG 的生成式做法

```python
def rag_generate(question, llm):
    passages = retrieve(question, top_k=3)
    prompt = f"""Context:
{chr(10).join('- ' + p for p in passages)}

Question: {question}

Answer using only the context above. If the context does not contain the answer, say "I don't know."
"""
    return llm(prompt)
```

提示詞的寫法很關鍵。明確要求模型只依據上下文作答、上下文不足時就回「I don't know」，比起隨手寫的提示詞，能把幻覺率壓低 40-60%。更講究的寫法還會加上引用出處、信賴分數與結構化抽取。

### 步驟 4：反映真實世界的評估

SQuAD 用的是**精確匹配（EM）**與**詞元層級的 F1**。EM 是正規化之後（轉小寫、去標點、移除冠詞）的嚴格比對——預測要嘛完全吻合，要嘛就是 0 分。F1 則計算預測與參考答案之間的詞元重疊，會給部分分數。兩者都會低估改寫過的答案："June 29, 2007" 對上 "June 29th, 2007" 通常 EM 是 0（序數詞破壞了正規化），但靠重疊的詞元仍然能拿到相當高的 F1。

生產環境的問答系統要看：

- **答案正確率**（由 LLM 或人工評判，因為指標捕捉不到語意等價）。
- **引用正確率。** 被引用的段落真的支持這個答案嗎？把生成的引用與檢索到的段落做字串比對，自動檢查非常容易。
- **拒答校準。** 當答案不在檢索到的段落裡時，系統是否正確地說出「我不知道」？量測它錯誤自信的比率。
- **檢索召回率。** 在評估閱讀器之前，先量測檢索器有沒有把對的段落送進前 `k` 名。閱讀器沒辦法補救一段根本沒被檢索到的段落。

### RAGAS：2026 年的生產級評估框架

`RAGAS` 是專為 RAG 系統打造的，也是 2026 年出貨時的預設選擇。它在不需要黃金參考答案的前提下，評出四個維度：

- **忠實度。** 答案裡的每一項主張都來自檢索到的上下文嗎？用基於 NLI 的蘊涵關係來衡量。這是你最主要的幻覺指標。
- **答案相關性。** 這個答案有回應到問題嗎？做法是從答案反推出假想的問題，再跟真正的問題比對。
- **上下文精確率。** 檢索到的區塊中，真正相關的比例是多少？精確率低就等於提示詞裡混進雜訊。
- **上下文召回率。** 檢索到的這一組是否包含所有必要資訊？召回率低，閱讀器就不可能成功。

不需要參考答案這一點，讓你可以直接在線上生產流量上評估，不必先整理出黃金答案。對於精確匹配類指標完全派不上用場的開放式問題，再疊一層「LLM 當評審」。

`pip install ragas`。把你的檢索器加閱讀器接上去。每一次查詢拿到四個純量。有退步就發警報。

## 框架應用

2026 年的技術堆疊：

| 使用場景 | 建議做法 |
|---------|-------------|
| 已給定段落，找出答案跨度 | `deepset/roberta-base-squad2` |
| 在固定語料上作答，封閉式不可接受 | RAG：稠密檢索器 + LLM 閱讀器 |
| 在文件庫上即時作答 | RAG 搭配混合檢索器（BM25 + 稠密）+ 重排器（第 14 單元） |
| 對話式問答（會有追問） | LLM 加上對話歷史，每一輪都跑一次 RAG |
| 高度重視事實、受法規監管的領域 | 在權威語料上做抽取式；絕對不要單靠生成式 |

抽取式問答在 2026 年不再流行，因為搭配 LLM 的 RAG 能處理的情況更多。但在必須逐字引用的場合它依然在服役：法律研究、法規遵循、稽核工具。

## 產出交付

存成 `outputs/skill-qa-architect.md`：

```markdown
---
name: qa-architect
description: Choose QA architecture, retrieval strategy, and evaluation plan.
version: 1.0.0
phase: 5
lesson: 13
tags: [nlp, qa, rag]
---

Given requirements (corpus size, question type, factuality constraint, latency budget), output:

1. Architecture. Extractive, RAG with extractive reader, RAG with generative reader, or closed-book LLM. One-sentence reason.
2. Retriever. None, BM25, dense (name the encoder), or hybrid.
3. Reader. SQuAD-tuned model, LLM by name, or "domain-fine-tuned DistilBERT."
4. Evaluation. EM + F1 for extractive benchmarks; answer accuracy + citation accuracy + refusal calibration for production. Name what you are measuring and how you are measuring it.

Refuse closed-book LLM answers for regulatory or compliance-sensitive questions. Refuse any QA system without a retrieval-recall baseline (you cannot evaluate the reader without knowing the retriever surfaced the right passage). Flag questions that require multi-hop reasoning as needing specialized multi-hop retrievers like HotpotQA-trained systems.
```

## 練習

1. **簡單。** 用上面的 SQuAD 抽取式流程處理 10 段維基百科段落。自己手寫 10 個問題。量測答案正確的比例。段落與問題都乾淨的話，你應該會看到 7 到 9 題正確。
2. **中等。** 加上一個拒答分類器。當最高的檢索分數低於某個閾值（例如餘弦相似度 0.3）時，直接回傳「我不知道」，不要呼叫閱讀器。用一組保留資料調校這個閾值。
3. **困難。** 在你自選的 10,000 份文件語料上建一條 RAG 流程。實作混合檢索（BM25 + 稠密），並用 RRF 融合（見第 14 單元）。比較有沒有混合這一步時的答案正確率。記錄下哪些類型的問題受益最多。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 抽取式問答 | 「找出答案跨度」 | 預測答案在給定段落中的起始與結束索引。 |
| 開放領域問答 | 「在語料上做問答」 | 沒有給定段落；必須先檢索再作答。 |
| RAG | 「先檢索再生成」 | 檢索增強生成。檢索器加閱讀器的流程。 |
| SQuAD | 「經典基準」 | Stanford Question Answering Dataset。以 EM 加 F1 評分。 |
| 幻覺 | 「編出來的答案」 | 閱讀器的輸出得不到檢索上下文的支持。 |
| 拒答校準 | 「知道什麼時候該閉嘴」 | 系統在無法作答時，正確地說出「我不知道」。 |

## 延伸閱讀

- [Rajpurkar et al. (2016). SQuAD: 100,000+ Questions for Machine Comprehension of Text](https://arxiv.org/abs/1606.05250) —— 基準論文。
- [Karpukhin et al. (2020). Dense Passage Retrieval for Open-Domain QA](https://arxiv.org/abs/2004.04906) —— DPR，問答領域經典的稠密檢索器。
- [Lewis et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) —— 為 RAG 命名的那篇論文。
- [Gao et al. (2023). Retrieval-Augmented Generation for Large Language Models: A Survey](https://arxiv.org/abs/2312.10997) —— 全面的 RAG 綜述。
