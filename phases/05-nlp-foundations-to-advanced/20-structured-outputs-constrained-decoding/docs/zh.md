# 結構化輸出與受限解碼

> 向 LLM 要 JSON。大多數時候你會拿到 JSON。在正式環境裡，「大多數」就是問題所在。受限解碼在取樣之前先動手改 logit，把「大多數」變成「總是」。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 17（聊天機器人）、階段 5 · 19（子詞分詞）
**時間：** 約 60 分鐘

## 問題所在

一個分類器這樣提示 LLM：「回傳 {positive, negative, neutral} 其中之一。」模型回傳的是「The sentiment is positive — this review is overwhelmingly favorable because the customer explicitly states that they ...」。你的解析器當掉了。你的分類器 F1 是 0.0。

自由形式的生成不是契約，只是一個建議。正式環境的系統需要契約。

2026 年有三個層次。

1. **提示詞。** 好好拜託模型。「只回傳那個 JSON 物件。」在前沿模型上大約有 80% 有效，小模型上更低。
2. **原生結構化輸出 API。** OpenAI `response_format`、Anthropic 的工具使用、Gemini 的 JSON 模式。在支援的結構定義上很可靠，但綁定廠商。
3. **受限解碼。** 在每一個生成步驟修改 logit，讓模型*沒辦法*吐出不合法的詞元。從構造上就 100% 合法。任何本地模型都適用。

這個單元會為三者建立直覺，並指出什麼時候該用哪一個。

## 核心概念

![受限解碼在每一步遮蔽不合法的詞元](../assets/constrained-decoding.svg)

**受限解碼是怎麼運作的。** 在每個生成步驟，LLM 會在整個詞彙表（約 10 萬個詞元）上產生一個 logit 向量。一個 *logit 處理器*坐在模型與取樣器之間。它會依照目前在目標文法（JSON Schema、正規表達式、上下文無關文法）中的位置，算出哪些詞元是合法的，並把所有不合法詞元的 logit 設成負無限大。剩下這些 logit 過完 softmax 之後，機率質量只會落在合法的延續上。

2026 年的實作：

- **Outlines。** 把 JSON Schema 或正規表達式編譯成一台有限狀態機。每個詞元都能以 O(1) 查到是否為合法的下一個詞元。因為以 FSM 為基礎，遞迴的結構定義需要先攤平。
- **XGrammar / llguidance。** 上下文無關文法引擎，能處理遞迴的 JSON Schema，解碼額外開銷近乎為零。OpenAI 在 2025 年的結構化輸出實作中公開致謝 llguidance。
- **vLLM guided decoding。** 內建 `guided_json`、`guided_regex`、`guided_choice`、`guided_grammar`，後端可選 Outlines、XGrammar 或 lm-format-enforcer。
- **Instructor。** 基於 Pydantic、包在任何 LLM 外面的一層封裝。驗證失敗就重試。跨供應商，但它不修改 logit——靠的是重試加上懂結構化輸出的提示詞。

### 反直覺的結果

受限解碼往往比不受限的生成*更快*。原因有兩個。第一，它縮小了下一個詞元的搜尋空間。第二，聰明的實作對於被強制的詞元會完全跳過生成（像 `{"name": "` 這種鷹架，每一個位元組都已經確定了）。

### 會讓你付出代價的陷阱

欄位順序很要緊。把 `answer` 放在 `reasoning` 前面，模型就會在思考之前先把答案定下來。JSON 是合法的。答案是錯的。沒有任何驗證抓得到這件事。

```json
// BAD
{"answer": "yes", "reasoning": "because ..."}

// GOOD
{"reasoning": "... therefore ...", "answer": "yes"}
```

結構定義的欄位順序是邏輯，不是排版。

## 動手實作

### 步驟 1：從零打造受正規表達式約束的生成

完整的獨立 FSM 實作見 `code/main.py`。核心想法用 30 行就講完了：

```python
def mask_logits(logits, valid_token_ids):
    mask = [float("-inf")] * len(logits)
    for tid in valid_token_ids:
        mask[tid] = logits[tid]
    return mask


def generate_constrained(model, tokenizer, prompt, fsm):
    ids = tokenizer.encode(prompt)
    state = fsm.initial_state
    while not fsm.is_accept(state):
        logits = model.next_token_logits(ids)
        valid = fsm.valid_tokens(state, tokenizer)
        logits = mask_logits(logits, valid)
        tok = sample(logits)
        ids.append(tok)
        state = fsm.transition(state, tok)
    return tokenizer.decode(ids)
```

FSM 追蹤的是文法中我們目前已經滿足了哪些部分。`valid_tokens(state, tokenizer)` 算出哪些詞彙表詞元可以推進 FSM，而不會離開通往接受狀態的路徑。

### 步驟 2：用 Outlines 處理 JSON Schema

```python
from pydantic import BaseModel
from typing import Literal
import outlines


class Review(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float
    evidence_span: str


model = outlines.models.transformers("meta-llama/Llama-3.2-3B-Instruct")
generator = outlines.generate.json(model, Review)

result = generator("Classify: 'The wait staff was attentive and the food arrived hot.'")
print(result)
# Review(sentiment='positive', confidence=0.93, evidence_span='attentive ... hot')
```

零驗證錯誤。永遠都是零。FSM 讓不合法的輸出根本到不了。

### 步驟 3：用 Instructor 寫不綁供應商的 Pydantic

```python
import instructor
from anthropic import Anthropic
from pydantic import BaseModel, Field


class Invoice(BaseModel):
    vendor: str
    total_usd: float = Field(ge=0)
    line_items: list[str]


client = instructor.from_anthropic(Anthropic())
invoice = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    response_model=Invoice,
    messages=[{"role": "user", "content": "Extract from: 'Acme Corp $420. Widget, Gizmo.'"}],
)
```

機制完全不同。Instructor 不碰 logit。它把結構定義寫進提示詞、解析輸出，驗證失敗就重試（預設 3 次）。任何供應商都能用。重試會增加延遲與成本。它的賣點是跨供應商的可攜性。

### 步驟 4：廠商原生 API

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-5",
    input=[{"role": "user", "content": "Classify: 'The food was cold.'"}],
    text={"format": {"type": "json_schema", "name": "sentiment",
          "schema": {"type": "object", "required": ["sentiment"],
                     "properties": {"sentiment": {"type": "string",
                                                  "enum": ["positive", "negative", "neutral"]}}}}},
)
print(response.output_parsed)
```

在伺服器端做受限解碼。對支援的結構定義而言，可靠度與 Outlines 相當。不必自己管本地模型。代價是被綁在該廠商上。

## 常見陷阱

- **遞迴的結構定義。** Outlines 會把遞迴攤平到固定深度。樹狀結構的輸出（嵌套留言、AST）需要 XGrammar 或 llguidance（基於 CFG）。
- **超大的列舉。** 一個 10,000 個選項的列舉編譯很慢，甚至會逾時。改用檢索器：先預測 top-k 候選，再約束到這些候選上。
- **文法太嚴。** 強制 `date: "YYYY-MM-DD"` 這樣的正規表達式，模型就沒辦法在日期缺失時輸出 `"unknown"`。於是模型會用捏一個日期來應付。請允許 `null` 或一個哨兵值。
- **過早定案。** 見上面的欄位順序陷阱。永遠把推理放前面。
- **沒有結構定義的廠商 JSON 模式。** 純 JSON 模式只保證是合法的 JSON，不保證*對你的使用情境合法*。永遠給一份完整的結構定義。

## 框架應用

2026 年的技術選擇：

| 情境 | 選擇 |
|-----------|------|
| OpenAI／Anthropic／Google 的模型，簡單結構定義 | 廠商原生結構化輸出 |
| 任何供應商，Pydantic 工作流，可以容忍重試 | Instructor |
| 本地模型，需要 100% 合法，扁平結構定義 | Outlines（FSM） |
| 本地模型，遞迴結構定義 | XGrammar 或 llguidance |
| 自架推論伺服器 | vLLM guided decoding |
| 批次處理，可以接受重試 | Instructor + 最便宜的模型 |

## 產出交付

存成 `outputs/skill-structured-output-picker.md`：

```markdown
---
name: structured-output-picker
description: Choose a structured output approach, schema design, and validation plan.
version: 1.0.0
phase: 5
lesson: 20
tags: [nlp, llm, structured-output]
---

Given a use case (provider, latency budget, schema complexity, failure tolerance), output:

1. Mechanism. Native vendor structured output, Instructor retries, Outlines FSM, or XGrammar CFG. One-sentence reason.
2. Schema design. Field order (reasoning first, answer last), nullable fields for "unknown", enum vs regex, required fields.
3. Failure strategy. Max retries, fallback model, graceful `null` handling, out-of-distribution refusal.
4. Validation plan. Schema compliance rate (target 100%), semantic validity (LLM-judge), field-coverage rate, latency p50/p99.

Refuse any design that puts `answer` or `decision` before reasoning fields. Refuse to use bare JSON mode without a schema. Flag recursive schemas behind an FSM-only library.
```

## 練習

1. **簡單。** 在不用受限解碼的情況下，提示一個小型開放權重模型（例如 Llama-3.2-3B）產生 `Review(sentiment, confidence, evidence_span)`。在 100 則評論上量出能解析成合法 JSON 的比例。
2. **中等。** 同一份語料改用 Outlines 的 JSON 模式。比較合規率、延遲與語意正確度。
3. **困難。** 從零實作一個受正規表達式約束的解碼器，用來產生電話號碼（`\d{3}-\d{3}-\d{4}`）。驗證 1000 個樣本中有 0 個不合法輸出。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 受限解碼（constrained decoding） | 強制輸出合法 | 在每個生成步驟遮蔽不合法詞元的 logit。 |
| logit 處理器 | 負責施加約束的那個東西 | 一個函式：`(logits, state) -> masked_logits`。 |
| FSM | 有限狀態機 | 編譯後的文法表示；查合法的下一個詞元是 O(1)。 |
| CFG | 上下文無關文法 | 能處理遞迴的文法；比 FSM 慢，但表達力更強。 |
| 結構定義的欄位順序 | 這有差嗎？ | 有——第一個欄位就定案了；永遠把推理放在答案之前。 |
| Guided decoding | vLLM 對它的稱法 | 同一個概念，整合進推論伺服器裡。 |
| JSON 模式 | OpenAI 的早期版本 | 保證 JSON 語法正確；**不**保證符合結構定義。 |

## 延伸閱讀

- [Willard, Louf (2023). Efficient Guided Generation for LLMs](https://arxiv.org/abs/2307.09702) —— Outlines 的論文。
- [XGrammar paper (2024)](https://arxiv.org/abs/2411.15100) —— 快速的、基於 CFG 的受限解碼。
- [vLLM — Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs.html) —— 推論伺服器端的整合。
- [OpenAI — Structured Outputs guide](https://platform.openai.com/docs/guides/structured-outputs) —— API 參考與各種坑。
- [Instructor library](https://python.useinstructor.com/) —— Pydantic 加上跨供應商的重試。
- [JSONSchemaBench (2025)](https://arxiv.org/abs/2501.10868) —— 對 6 個受限解碼框架做基準測試。
