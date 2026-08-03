# OpenTelemetry GenAI —— 端到端追蹤工具呼叫

> 一個代理呼叫了五個工具、三台 MCP 伺服器與兩個子代理。你需要一條橫跨這一切的追蹤。OpenTelemetry 的 GenAI 語意慣例（v1.37 起屬性已穩定）是 2026 年的標準，Datadog、Langfuse、Arize Phoenix、OpenLLMetry 與 AgentOps 都原生支援。這一課會替那些必要屬性命名、走過 span 階層（代理 → LLM → 工具），並出貨一個你可以接到任何 OTel 匯出器上的 stdlib span 產生器。

**類型：** 實作
**程式語言：** Python (stdlib, OTel span emitter)
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 08（MCP 客戶端）
**時間：** 約 75 分鐘

## 學習目標

- 說出一個 LLM span 與一個工具執行 span 所需的 OTel GenAI 屬性。
- 建出一棵涵蓋代理迴圈、LLM 呼叫、工具呼叫與 MCP 客戶端分派的追蹤階層。
- 決定要擷取哪些內容（選擇加入）與要遮蔽哪些（預設值）。
- 不必重寫工具程式碼，就把 span 匯出到本機的收集器（Jaeger、Langfuse）。

## 問題所在

2026 年 2 月的一次除錯：使用者回報「我的代理有時要 30 秒才回應；有時只要 3 秒」。沒有追蹤。日誌顯示了那次 LLM 呼叫，但沒有工具分派、沒有 MCP 伺服器的來回、也沒有子代理。你只能猜。最後你找到了：某台 MCP 伺服器偶爾會在冷啟動時卡住。

沒有端到端追蹤，你找不到這個問題。OTel GenAI 修正了這件事。

這些慣例在 2025 到 2026 年間，於 OpenTelemetry 的語意慣例小組底下定案。它們定義了穩定的屬性名稱，好讓 Datadog、Langfuse、Phoenix、OpenLLMetry 與 AgentOps 都解析同一套 span。埋一次點；送到任何後端。

## 核心概念

### Span 階層

```
agent.invoke_agent  (top, INTERNAL span)
 ├── llm.chat       (CLIENT span)
 ├── tool.execute   (INTERNAL)
 │    └── mcp.call  (CLIENT span)
 ├── llm.chat       (CLIENT span)
 └── subagent.invoke (INTERNAL)
```

整棵樹巢狀在同一個 trace id 底下。span id 則串起父子關係。

### 必要屬性

依 2025 到 2026 年的 semconv：

- `gen_ai.operation.name` —— `"chat"`、`"text_completion"`、`"embeddings"`、`"execute_tool"`、`"invoke_agent"`。
- `gen_ai.provider.name` —— `"openai"`、`"anthropic"`、`"google"`、`"azure_openai"`。
- `gen_ai.request.model` —— 請求的模型字串（例如 `"gpt-4o-2024-08-06"`）。
- `gen_ai.response.model` —— 實際服務的那個模型。
- `gen_ai.usage.input_tokens`／`gen_ai.usage.output_tokens`。
- `gen_ai.response.id` —— 供對應用的供應商回應 id。

工具 span 用的是：

- `gen_ai.tool.name` —— 工具識別字。
- `gen_ai.tool.call.id` —— 那次特定呼叫的 id。
- `gen_ai.tool.description` —— 工具描述（選配）。

代理 span 用的是：

- `gen_ai.agent.name`／`gen_ai.agent.id`／`gen_ai.agent.description`。

### Span 種類

- 跨行程邊界的呼叫（LLM 供應商、MCP 伺服器）用 `SpanKind.CLIENT`。
- 代理自己的迴圈步驟與工具執行用 `SpanKind.INTERNAL`。

### 選擇加入的內容擷取

預設情況下，span 承載的是指標與時序 —— 不含提示詞或補全。大型酬載與 PII 預設關閉。設定 `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` 與特定的內容擷取環境變數，才會納入內容。在生產環境啟用之前請仔細檢視。

### Span 上的事件

詞元層級的事件可以當成 span 事件加上去：

- `gen_ai.content.prompt` —— 輸入訊息。
- `gen_ai.content.completion` —— 輸出訊息。
- `gen_ai.content.tool_call` —— 記錄下來的工具呼叫。

事件在 span 之內依時間排序，便於細節重播。

### 匯出器

OTel span 可以匯出到：

- **Jaeger／Tempo。** 開源、地端。
- **Langfuse。** 專攻 LLM 可觀測性；能視覺化詞元用量。
- **Arize Phoenix。** 評測 + 追蹤合一。
- **Datadog。** 商用；原生解析 `gen_ai.*` 屬性。
- **Honeycomb。** 欄式儲存；便於查詢。

大家說的都是 OTLP 這個線路格式。你的程式碼不必在意。

### 跨 MCP 的傳播

當 MCP 客戶端呼叫伺服器時，把 W3C 的 traceparent 標頭注入請求。Streamable HTTP 支援標準標頭。stdio 則原生不承載 HTTP 標頭；規格的 2026 路線圖正在討論為 JSON-RPC 呼叫加上一個 `_meta.traceparent` 欄位。

在那之前：手動把 traceparent 放進每一次請求的 `_meta`。伺服器則把 trace id 記錄下來。

### 指標

除了 span 之外，GenAI 的 semconv 還定義了指標：

- `gen_ai.client.token.usage` —— 直方圖。
- `gen_ai.client.operation.duration` —— 直方圖。
- `gen_ai.tool.execution.duration` —— 直方圖。

那些不需要逐次呼叫細節的儀表板，就用這些。

### AgentOps 這一層

AgentOps（成立於 2024 年）專攻 GenAI 可觀測性。它包住熱門框架（LangGraph、Pydantic AI、CrewAI），自動吐出 OTel span。如果你的堆疊用的是它支援的框架，這很有用；否則就用手動埋點。

```figure
t3-span-waterfall
```

## 框架應用

`code/main.py` 為一個「呼叫 LLM、分派兩個工具、做一次 MCP 來回」的代理，把 OTel 形狀的 span 以類 OTLP-JSON 的格式吐到 stdout。沒有真正的匯出器 —— 這一課的焦點是 span 的形狀與屬性集合。把輸出貼進任何相容 OTLP 的檢視器，或者直接讀它。

要看的地方有：

- trace id 在所有 span 之間共享。
- 父子連結透過 `parentSpanId` 編碼。
- 必要的 `gen_ai.*` 屬性都有填。
- 內容擷取預設關閉；有一個情境會透過環境變數把它打開。

## 產出交付

這一課產出 `outputs/skill-otel-genai-instrumentation.md`。給定一份代理程式碼庫，這項技能會產出一份埋點計畫：該在哪裡加 span、該填哪些屬性，以及該對準哪些匯出器。

## 練習

1. 跑一次 `code/main.py`。數一數 span 的數量，並指認哪些是 CLIENT、哪些是 INTERNAL。

2. 打開內容擷取（環境變數），確認 `gen_ai.content.prompt` 與 `gen_ai.content.completion` 事件有出現。並記下這對 PII 的意涵。

3. 加上工具執行的指標 `gen_ai.tool.execution.duration`，並在每次呼叫時把它當成一個直方圖樣本吐出。

4. 把一個 traceparent 從父層代理 span 傳播到一次 MCP 請求的 `_meta.traceparent` 欄位。驗證 MCP 伺服器會看到相同的 trace id。

5. 讀 OTel GenAI 的 semconv 規格。找出一個 semconv 中列出、而本課程式碼「沒有」吐出的屬性。把它加上去。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| OTel | 「OpenTelemetry」 | 追蹤、指標、日誌的開放標準 |
| GenAI semconv | 「GenAI 語意慣例」 | 給 LLM／工具／代理 span 用的穩定屬性名稱 |
| `gen_ai.*` | 「那個屬性命名空間」 | 所有 GenAI 屬性都共用這個前綴 |
| Span | 「一段計時的操作」 | 帶起點、終點與屬性的一個工作單位 |
| Trace | 「跨 span 的血緣」 | 共用同一個 trace id 的 span 構成的樹 |
| SpanKind | 「CLIENT／SERVER／INTERNAL」 | 關於 span 方向的提示 |
| OTLP | 「OpenTelemetry Line Protocol」 | 匯出器使用的線路格式 |
| 選擇加入的內容 | 「提示詞／補全擷取」 | 預設關閉；用環境變數啟用 |
| traceparent | 「W3C 標頭」 | 跨服務傳播追蹤上下文 |
| 匯出器 | 「各後端專屬的輸送器」 | 把 span 送到 Jaeger／Datadog 等處的元件 |

## 延伸閱讀

- [OpenTelemetry — GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/) —— GenAI span、指標與事件的權威慣例
- [OpenTelemetry — GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) —— LLM 與工具執行 span 的屬性清單
- [OpenTelemetry — GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) —— 代理層級的 `invoke_agent` span
- [open-telemetry/semantic-conventions — GenAI spans](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md) —— 託管在 GitHub 上的真值來源
- [Datadog — LLM OTel semantic convention](https://www.datadoghq.com/blog/llm-otel-semantic-convention/) —— 生產環境整合的逐步說明
