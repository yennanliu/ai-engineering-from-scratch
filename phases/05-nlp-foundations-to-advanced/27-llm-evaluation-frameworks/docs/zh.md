# LLM 評估 —— RAGAS、DeepEval、G-Eval

> 完全比對與 F1 抓不到語意上的等價。人工審查又撐不起規模。LLM 評審才是生產環境的答案 —— 前提是校準得夠好，那個分數才值得信。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 13（問答）、階段 5 · 14（資訊檢索）
**時間：** 約 75 分鐘

## 問題所在

你的 RAG 系統回答：「June 29th, 2007.」
黃金答案是：「June 29, 2007.」
Exact Match 給 0 分。F1 給大約 75%。人類會給 100 分。

現在把這件事乘上 10,000 個測試案例。再乘上檢索器、切塊、提示詞、模型的每一次改動。你需要一個評估器：懂語意、規模化跑起來便宜、不會對迴歸說謊、還能把該浮上來的失效模式浮上來。

2026 年有三個框架把這個問題吃了下來。

- **RAGAS。** Retrieval-Augmented Generation ASsessment。四個 RAG 指標（忠實度、答案相關性、脈絡精確率、脈絡召回率），後端是 NLI 加 LLM 評審。有研究背書，而且輕量。
- **DeepEval。** LLM 的 pytest。G-Eval、任務完成度、幻覺、偏誤等指標。原生為 CI/CD 而生。
- **G-Eval。** 一種方法（同時也是 DeepEval 的一個指標）：帶思維鏈的 LLM 評審，可自訂準則，輸出 0-1 分。

三個都靠 LLM 評審。這個單元要建立的，是對這個方法本身、以及圍繞它的那層信任機制的直覺。

## 核心概念

![四個評估面向，以及 LLM 評審的架構](../assets/llm-evaluation.svg)

**LLM 評審（LLM-as-judge）。** 把靜態指標換成一個 LLM，讓它依照評分標準去給輸出打分。給定 `(query, context, answer)`，去提示一個評審 LLM：「Score 0-1 on faithfulness.」然後把分數收回來。

它為什麼行得通：LLM 能以極低的成本逼近人類的判斷。GPT-4o-mini 每個案例約 $0.003，1000 筆樣本的迴歸評估跑一輪不到 $5。

它為什麼會無聲地失敗：

1. **評審偏誤。** 評審偏好較長的答案、來自自己模型家族的答案、以及符合提示詞風格的答案。
2. **JSON 解析失敗。** 壞掉的 JSON → NaN 分數 → 悄悄被排除在總計之外。RAGAS 的使用者都懂這個痛。用 try/except 加上明確的失敗處理把它守住。
3. **跨模型版本的偏移。** 升級評審會讓每一個指標都變樣。把評審模型與版本凍結。

**RAG 四指標。**

| 指標 | 它在問什麼 | 後端 |
|--------|----------|---------|
| 忠實度 | 答案裡的每個主張，都出自檢索到的脈絡嗎？ | 基於 NLI 的蘊涵判斷 |
| 答案相關性 | 答案有回應到問題嗎？ | 從答案反推出假設性的問題，再跟真正的問題比對 |
| 脈絡精確率 | 檢索到的區塊裡，有多少比例是相關的？ | LLM 評審 |
| 脈絡召回率 | 檢索有把該拿到的都拿回來嗎？ | LLM 評審，比對黃金答案 |

**G-Eval。** 定義一個自訂準則：「Did the answer cite the correct source?」框架會自動把它展開成一串思維鏈的評估步驟，再打出 0-1 分。適合處理 RAGAS 沒涵蓋、屬於特定領域的品質面向。

**校準。** 在拿到跟人工標註的相關性之前，永遠不要相信評審的原始分數。跑 100 個手工標註的例子。把評審分數對人工分數畫出來。算 Spearman rho。如果 rho < 0.7，你的評審評分標準還得再修。

```figure
n5-judge-gauge
```

## 動手實作

### 步驟 1：用 NLI 做忠實度（RAGAS 風格）

```python
from typing import Callable
from transformers import pipeline

nli = pipeline("text-classification",
               model="MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli",
               top_k=None)

# `llm` is any callable: prompt str -> generated str.
# Example: llm = lambda p: client.messages.create(model="claude-haiku-4-5", ...).content[0].text
LLM = Callable[[str], str]


def atomic_claims(answer: str, llm: LLM) -> list[str]:
    prompt = f"""Break this answer into simple factual claims (one per line):
{answer}
"""
    return llm(prompt).splitlines()


def faithfulness(answer: str, context: str, llm: LLM) -> float:
    claims = atomic_claims(answer, llm)
    if not claims:
        return 0.0
    supported = 0
    for claim in claims:
        result = nli({"text": context, "text_pair": claim})[0]
        entail = next((s for s in result if s["label"] == "entailment"), None)
        if entail and entail["score"] > 0.5:
            supported += 1
    return supported / len(claims)
```

把答案拆解成原子主張。拿每個主張去對檢索到的脈絡做 NLI 檢查。忠實度就是被支持的比例。

### 步驟 2：答案相關性

```python
import numpy as np
from sentence_transformers import SentenceTransformer

# encoder: any model implementing .encode(texts, normalize_embeddings=True) -> ndarray
# e.g., encoder = SentenceTransformer("BAAI/bge-small-en-v1.5")

def answer_relevance(question: str, answer: str, encoder, llm: LLM, n: int = 3) -> float:
    prompt = f"Write {n} questions this answer could be the answer to:\n{answer}"
    generated = [line for line in llm(prompt).splitlines() if line.strip()][:n]
    if not generated:
        return 0.0
    q_emb = np.asarray(encoder.encode([question], normalize_embeddings=True)[0])
    g_embs = np.asarray(encoder.encode(generated, normalize_embeddings=True))
    sims = [float(q_emb @ g_emb) for g_emb in g_embs]
    return sum(sims) / len(sims)
```

如果答案暗示的問題跟真正被問的那個不一樣，相關性就會掉下來。

### 步驟 3：G-Eval 自訂指標

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams, LLMTestCase

metric = GEval(
    name="Correctness",
    criteria="The answer should be factually accurate and match the expected output.",
    evaluation_steps=[
        "Read the expected output.",
        "Read the actual output.",
        "List factual claims in the actual output.",
        "For each claim, mark supported or unsupported by the expected output.",
        "Return score = fraction supported.",
    ],
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
)

test = LLMTestCase(input="When was the first iPhone released?",
                   actual_output="June 29th, 2007.",
                   expected_output="June 29, 2007.")
metric.measure(test)
print(metric.score, metric.reason)
```

那些評估步驟就是評分標準。寫得明確的步驟，比隱含的「score 0-1」提示詞穩定得多。

### 步驟 4：CI 關卡

```python
import deepeval
from deepeval.metrics import FaithfulnessMetric, ContextualRelevancyMetric


def test_rag_system():
    cases = load_regression_cases()
    faith = FaithfulnessMetric(threshold=0.85)
    rel = ContextualRelevancyMetric(threshold=0.7)
    for case in cases:
        faith.measure(case)
        assert faith.score >= 0.85, f"faithfulness regression on {case.id}"
        rel.measure(case)
        assert rel.score >= 0.7, f"relevancy regression on {case.id}"
```

當成一個 pytest 檔案交付。每個 PR 都跑。出現迴歸就擋掉合併。

### 步驟 5：從零寫一個玩具評估

見 `code/main.py`。純標準函式庫的近似版本：忠實度（答案主張與脈絡的重疊）與相關性（答案詞元與問題詞元的重疊）。不是生產級的東西，但骨架就是這個樣子。

## 常見陷阱

- **沒有校準。** 一個跟人工標註相關性只有 0.3 的評審就是雜訊。上線前一定要跑一輪校準。
- **自我評估。** 用同一個 LLM 又生成又當評審，分數會被抬高 10-20%。評審要換一個不同的模型家族。
- **成對比較裡的位置偏誤。** 評審偏好排在前面的那個選項。永遠要打亂順序，並且兩種順序都跑。
- **原始總計會藏住失敗。** 平均分 0.85 常常藏著 5% 的災難性失敗。永遠要去看最低的那個分位。
- **黃金資料集腐爛。** 沒有版本控管的評估集會隨時間漂移，讓縱向比較失去意義。每次改動都給資料集打上標籤。
- **LLM 成本。** 規模一大，評審呼叫就會吃掉大部分成本。用能過校準門檻的最便宜模型。GPT-4o-mini、Claude Haiku、Mistral-small。

## 框架應用

2026 年的技術堆疊：

| 情境 | 框架 |
|---------|-----------|
| RAG 品質監控 | RAGAS（4 個指標） |
| CI/CD 迴歸測試關卡 | DeepEval + pytest |
| 自訂領域準則 | DeepEval 裡的 G-Eval |
| 線上實流量監控 | RAGAS 的無參考模式 |
| 人在迴路中的抽查 | LangSmith 或 Phoenix，搭配標註 UI |
| 紅隊演練／安全性評估 | Promptfoo + DeepEval |

典型的堆疊：RAGAS 做監控、DeepEval 做 CI、G-Eval 處理新的面向。三個都跑；它們彼此不同意的地方很有用。

## 產出交付

存成 `outputs/skill-eval-architect.md`：

```markdown
---
name: eval-architect
description: Design an LLM evaluation plan with calibrated judge and CI gates.
version: 1.0.0
phase: 5
lesson: 27
tags: [nlp, evaluation, rag]
---

Given a use case (RAG / agent / generative task), output:

1. Metrics. Faithfulness / relevance / context-precision / context-recall + any custom G-Eval metrics with criteria.
2. Judge model. Named model + version, rationale for cost vs accuracy.
3. Calibration. Hand-labeled set size, target Spearman rho vs human > 0.7.
4. Dataset versioning. Tag strategy, change log, stratification.
5. CI gate. Thresholds per metric, regression-window logic, bottom-quantile alert.

Refuse to rely on a judge untested against ≥50 human-labeled examples. Refuse self-evaluation (same model generates + judges). Refuse aggregate-only reporting without bottom-10% surfacing. Flag any pipeline where judge upgrade lands without parallel baseline eval.
```

## 練習

1. **簡單。** 拿 10 個已知有幻覺的 RAG 例子跑 RAGAS。確認忠實度指標每一個都抓到了。
2. **中等。** 手工把 50 個問答答案的正確性標成 0-1。用 G-Eval 打分。量評審與人工之間的 Spearman rho。
3. **困難。** 用 DeepEval 做一個 pytest CI 關卡。故意讓檢索器退化。確認關卡會失敗。再對最低的 10% 加上門檻檢查，做出最低分位的警示。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| LLM 評審 | 「用 LLM 打分」 | 提示一個評審模型，依照評分標準把輸出打成 0-1 分。 |
| RAGAS | 「那個 RAG 指標函式庫」 | 開源評估框架，內含 4 個無參考的 RAG 指標。 |
| 忠實度 | 「答案有沒有根據？」 | 答案主張中被檢索脈絡蘊涵的比例。 |
| 脈絡精確率 | 「檢索到的區塊相關嗎？」 | 前 K 個區塊裡真正有用的比例。 |
| 脈絡召回率 | 「檢索有找齊嗎？」 | 黃金答案的主張中，有被檢索區塊支持的比例。 |
| G-Eval | 「自訂的 LLM 評審」 | 評分標準 + 思維鏈評估步驟 + 0-1 分。 |
| 校準 | 「信任，但要驗證」 | 評審分數與人工分數之間的 Spearman 相關係數。 |

## 延伸閱讀

- [Es et al. (2023). RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217) —— RAGAS 的論文。
- [Liu et al. (2023). G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634) —— G-Eval 的論文。
- [DeepEval docs](https://deepeval.com/docs/metrics-introduction) —— 開源的生產環境堆疊。
- [Zheng et al. (2023). Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) —— 偏誤、校準與極限。
- [MLflow GenAI Scorer](https://mlflow.org/blog/third-party-scorers) —— 整合 RAGAS、DeepEval、Phoenix 的統一框架。
