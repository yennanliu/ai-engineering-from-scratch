# 函數呼叫深入剖析 —— OpenAI、Anthropic、Gemini

> 三家前沿供應商在 2024 年收斂到同一個工具呼叫迴圈，然後在其他每一件事上分道揚鑣。OpenAI 用 `tools` 與 `tool_calls`。Anthropic 用 `tool_use` 與 `tool_result` 區塊。Gemini 用 `functionDeclarations` 與唯一 id 對應。這一課會把三者並排 diff 一遍，好讓在某一家供應商上出貨的程式碼，移植時不會壞掉。

**類型：** 實作
**程式語言：** Python (stdlib, schema translators)
**先修單元：** 階段 13 · 01（工具介面）
**時間：** 約 75 分鐘

## 學習目標

- 說出 OpenAI、Anthropic 與 Gemini 函數呼叫酬載之間的三處形狀差異（宣告、呼叫、結果）。
- 把一份工具宣告翻譯成三家供應商的格式，並預測嚴格模式的限制會在哪裡不同。
- 在各家供應商中用 `tool_choice` 強制、禁止或自動挑選工具呼叫。
- 知道各家供應商的硬性上限（工具數、schema 深度、參數長度），以及各自在超限時吐出的錯誤特徵。

## 問題所在

函數呼叫請求的形狀因供應商而異。以下是 2026 年生產堆疊中的三個具體例子：

**OpenAI Chat Completions／Responses API。** 你傳入 `tools: [{type: "function", function: {name, description, parameters, strict}}]`。模型的回應包含 `choices[0].message.tool_calls: [{id, type: "function", function: {name, arguments}}]`，其中 `arguments` 是一個你得自己解析的 JSON 字串。嚴格模式（`strict: true`）透過受限解碼強制 schema 合規。

**Anthropic Messages API。** 你傳入 `tools: [{name, description, input_schema}]`。回應以 `content: [{type: "text"}, {type: "tool_use", id, name, input}]` 的形式回來。`input` 已經解析好了（是物件，不是字串）。你則用一則包含 `{type: "tool_result", tool_use_id, content}` 區塊的新 `user` 訊息來回覆。

**Google Gemini API。** 你傳入 `tools: [{functionDeclarations: [{name, description, parameters}]}]`（巢狀在 `functionDeclarations` 底下）。回應以 `candidates[0].content.parts: [{functionCall: {name, args, id}}]` 抵達，其中 `id` 從 Gemini 3 起是唯一的，用於平行呼叫的對應。你則用 `{functionResponse: {name, id, response}}` 回覆。

同一個迴圈。不同的欄位名稱、不同的巢狀結構、不同的「字串對物件」慣例、不同的對應機制。一支在 OpenAI 上寫出天氣代理的團隊，光是為了這些管線，就要付出兩天移植到 Anthropic，再一天移植到 Gemini。

這一課會做一個轉譯器，把三種格式統一成一份標準工具宣告，並在邊緣做路由。階段 13 · 17 會把同樣的模式一般化成一個 LLM 閘道。

## 核心概念

### 共通的結構

每家供應商都需要五樣東西：

1. **工具清單。** 每個工具的名稱、描述與輸入 schema。
2. **工具選擇。** 強制指定某個工具、禁止使用工具，或讓模型自己決定。
3. **呼叫吐出。** 指名工具與參數的結構化輸出。
4. **呼叫 id。** 把回應對應回正確的那次呼叫（對平行呼叫很要緊）。
5. **結果注入。** 一則把結果繫回該次呼叫的訊息或區塊。

### 形狀差異，逐欄位比對

| 面向 | OpenAI | Anthropic | Gemini |
|--------|--------|-----------|--------|
| 宣告的外層封裝 | `{type: "function", function: {...}}` | `{name, description, input_schema}` | `{functionDeclarations: [{...}]}` |
| schema 欄位 | `parameters` | `input_schema` | `parameters` |
| 回應容器 | assistant 訊息上的 `tool_calls[]` | 型別為 `tool_use` 的 `content[]` | 型別為 `functionCall` 的 `parts[]` |
| 參數型別 | 字串化的 JSON | 已解析的物件 | 已解析的物件 |
| id 格式 | `call_...`（OpenAI 產生） | `toolu_...`（Anthropic） | UUID（Gemini 3 起） |
| 結果區塊 | 角色 `tool`，帶 `tool_call_id` | `user` 帶 `tool_result`，附 `tool_use_id` | `functionResponse` 帶相符的 `id` |
| 強制指定工具 | `tool_choice: {type: "function", function: {name}}` | `tool_choice: {type: "tool", name}` | `tool_config: {function_calling_config: {mode: "ANY"}}` |
| 禁止使用工具 | `tool_choice: "none"` | `tool_choice: {type: "none"}` | `mode: "NONE"` |
| 嚴格 schema | `strict: true` | schema 就是 schema（一律強制） | 請求層級的 `responseSchema` |

### 你真的會撞到的上限

- **OpenAI。** 每次請求 128 個工具。schema 深度 5。參數字串 <= 8192 位元組。嚴格模式要求不得有 `$ref`、不得有互相重疊的 `oneOf`／`anyOf`／`allOf`，且每個屬性都要列進 `required`。
- **Anthropic。** 每次請求 64 個工具。schema 深度實際上無上限，但實務上限是 10。沒有嚴格模式旗標；schema 是一份契約，而模型傾向遵守。
- **Gemini。** 每次請求 64 個函數。schema 型別是 OpenAPI 3.0 的子集（與 JSON Schema 2020-12 略有出入）。從 Gemini 3 起平行呼叫帶唯一 id。

### `tool_choice` 的行為

大家都支援三種模式，只是名稱不同。

- **Auto。** 模型自己挑工具或文字。預設值。
- **Required／Any。** 模型至少得呼叫一個工具。
- **None。** 模型不得呼叫工具。

再加上各家獨有的一種模式：

- **OpenAI。** 依名稱強制指定某個工具。
- **Anthropic。** 依名稱強制指定某個工具；`disable_parallel_tool_use` 旗標把單次與多次分開。
- **Gemini。** `mode: "VALIDATED"` 會把每個回應都送過一次 schema 驗證器，不管模型本來想幹嘛。

### 平行呼叫

OpenAI 的 `parallel_tool_calls: true`（預設）會在同一則 assistant 訊息中吐出多次呼叫。你把它們全部跑完，再用一則批次的 tool 角色訊息回覆，其中每個 `tool_call_id` 各一筆。Anthropic 歷來是單次呼叫；`disable_parallel_tool_use: false`（自 Claude 3.5 起為預設）啟用多次呼叫。Gemini 2 允許平行呼叫，但沒給穩定的 id；Gemini 3 加上了 UUID，好讓亂序的回應能乾淨地對應。

### 串流

三家都支援串流的工具呼叫。線路格式各不相同：

- **OpenAI。** `tool_calls[i].function.arguments` 的差量分塊會逐步抵達。你要一直累積到 `finish_reason: "tool_calls"`。
- **Anthropic。** block-start／block-delta／block-stop 事件。`input_json_delta` 分塊承載部分參數。
- **Gemini。** `streamFunctionCallArguments`（Gemini 3 新增）吐出的分塊帶 `functionCallId`，好讓多個平行呼叫能交錯進行。

階段 13 · 03 會深入平行 + 串流的重組。這一課聚焦在宣告與單次呼叫的形狀上。

### 錯誤與修復

無效參數的錯誤看起來也各不相同。

- **OpenAI（非嚴格模式）。** 模型回傳 `arguments: "{bad json}"`，你的 JSON 解析失敗，於是你注入一則錯誤訊息再呼叫一次。
- **OpenAI（嚴格模式）。** 驗證發生在解碼期間；無效 JSON 不可能出現，但可能冒出 `refusal`。
- **Anthropic。** `input` 可能含有非預期的欄位；schema 只是建議性的。要在伺服器端驗證。
- **Gemini。** OpenAPI 3.0 的怪癖：物件欄位上的 `enum` 會被靜默忽略；請自己驗證。

### 轉譯器模式

你程式碼裡的一份標準工具宣告長這樣（形狀由你決定）：

```python
Tool(
    name="get_weather",
    description="Use when ...",
    input_schema={"type": "object", "properties": {...}, "required": [...]},
    strict=True,
)
```

三個小函式把它翻譯成三家供應商的形狀。`code/main.py` 裡的測試框架做的正是這件事，接著再把一次假的工具呼叫，繞著各家供應商的回應形狀跑一圈。不需要網路 —— 這一課教的是形狀，不是 HTTP。

生產團隊會把這個轉譯器包進 `AbstractToolset`（Pydantic AI）、`UniversalToolNode`（LangGraph）或 `BaseTool`（LlamaIndex）。階段 13 · 17 會出貨一個閘道，在這三家中的任何一家前面暴露一組 OpenAI 形狀的 API。

```figure
function-call-args
```

## 框架應用

`code/main.py` 定義了一個標準的 `Tool` dataclass，以及三個分別吐出 OpenAI、Anthropic 與 Gemini 宣告 JSON 的轉譯器。接著它把三種形狀各自手工打造的供應商回應，解析成同一個標準呼叫物件，藉此展示它們在皮下的語意其實一模一樣。跑跑看，並把三份宣告並排 diff 一下。

要看的地方有：

- 三段宣告區塊只在外層封裝與欄位名稱上不同。
- 三段回應區塊的差別在於呼叫住在哪裡（頂層的 `tool_calls`、`content[]` 區塊、`parts[]` 項目）。
- 單一個 `canonical_call()` 函式，就能從三種回應形狀中抽出 `{id, name, args}`。

## 產出交付

這一課產出 `outputs/skill-provider-portability-audit.md`。給定一份針對某家供應商的函數呼叫整合，這項技能會產出一份可攜性稽核：它依賴了哪些供應商上限、哪些欄位需要改名，以及移植到其他各家時會壞掉什麼。

## 練習

1. 跑一次 `code/main.py`，驗證三份供應商宣告 JSON 序列化的都是同一個底層 `Tool` 物件。修改那個標準工具，加上一個 enum 參數，然後確認只有 Gemini 的轉譯器需要處理那個 OpenAPI 怪癖。

2. 為每家供應商加上一個 `ListToolsResponse` 解析器，用來抽出模型在一次 `list_tools` 或探索呼叫之後回傳的工具清單。OpenAI 原生沒有這個東西；把這個不對稱記下來。

3. 實作 `tool_choice` 的轉換：把一份標準的 `ToolChoice(mode="force", tool_name="x")` 映射到三家供應商的形狀。接著再映射 `mode="any"` 與 `mode="none"`。對照本課那張差異表。

4. 挑三家供應商中的一家，把它的函數呼叫指南從頭讀到尾。找出一個它的 schema 規格中有、而另外兩家不支援的欄位。候選有：OpenAI 的 `strict`、Anthropic 的 `disable_parallel_tool_use`、Gemini 的 `function_calling_config.allowed_function_names`。

5. 寫一組測試向量：一次參數違反所宣告 schema 的工具呼叫。把它送過每家供應商的驗證器（用單元 01 那個 stdlib 版本當替身就行），記錄哪些錯誤會觸發。寫下就嚴格性而言，你在生產環境會選哪一家。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| 函數呼叫 | 「工具使用」 | 供應商層級、用於吐出結構化工具呼叫的 API |
| 工具宣告 | 「工具規格」 | 名稱 + 描述 + JSON Schema 輸入酬載 |
| `tool_choice` | 「強制／禁止」 | auto／required／none／指定名稱這幾種模式 |
| 嚴格模式 | 「schema 強制」 | OpenAI 的旗標，把解碼約束成符合 schema |
| `tool_use` 區塊 | 「Anthropic 的呼叫形狀」 | 帶 id、name、input 的行內內容區塊 |
| `functionCall` part | 「Gemini 的呼叫形狀」 | 一個含 name、args 與 id 的 `parts[]` 項目 |
| 參數即字串 | 「字串化的 JSON」 | OpenAI 回傳的 args 是 JSON 字串，不是物件 |
| 平行工具呼叫 | 「一輪之內扇出」 | 同一則 assistant 訊息中的多次工具呼叫 |
| 拒絕 | 「模型婉拒」 | 只在嚴格模式下出現的 refusal 區塊，用來取代一次呼叫 |
| OpenAPI 3.0 子集 | 「Gemini 的 schema 怪癖」 | Gemini 用的是一種類 JSON Schema 的方言，有些微差異 |

## 延伸閱讀

- [OpenAI — Function calling guide](https://platform.openai.com/docs/guides/function-calling) —— 權威參考，含嚴格模式與平行呼叫
- [Anthropic — Tool use overview](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview) —— `tool_use` 與 `tool_result` 的區塊語意
- [Google — Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling) —— 平行呼叫、唯一 id 與 OpenAPI 子集
- [Vertex AI — Function calling reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/function-calling) —— Gemini 的企業版表面
- [OpenAI — Structured outputs](https://platform.openai.com/docs/guides/structured-outputs) —— 嚴格模式 schema 強制的細節
