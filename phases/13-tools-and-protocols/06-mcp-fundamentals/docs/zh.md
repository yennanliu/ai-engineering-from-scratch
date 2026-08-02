# MCP 基礎 —— 原語、生命週期、JSON-RPC 底層

> MCP 之前的每一次整合都是一次性的。Model Context Protocol 由 Anthropic 在 2024 年 11 月首度出貨，如今由 Linux Foundation 的 Agentic AI Foundation 託管，它把探索與呼叫標準化，好讓任何客戶端都能跟任何伺服器對話。2025-11-25 版規格點名了六個原語（伺服器三個、客戶端三個）、一套三階段生命週期，以及 JSON-RPC 2.0 的線路格式。學會這些，本階段其餘的 MCP 章節就只剩下閱讀了。

**類型：** 學習
**程式語言：** Python (stdlib, JSON-RPC parser)
**先修單元：** 階段 13 · 01 到 05（工具介面與函數呼叫）
**時間：** 約 45 分鐘

## 學習目標

- 說出全部六個 MCP 原語（伺服器端的 tools、resources、prompts；客戶端的 roots、sampling、elicitation），並各舉一個使用情境。
- 走過那三階段生命週期（initialize、operation、shutdown），並指出每個階段各由誰送出哪些訊息。
- 解析並吐出 JSON-RPC 2.0 的 request、response 與 notification 封裝。
- 說明 `initialize` 時的能力協商是什麼，以及少了它會壞掉什麼。

## 問題所在

在 MCP 之前，每個會用工具的代理都有自己的協定。Cursor 有一套形似 MCP 卻不相容的工具系統。Claude Desktop 出貨的是另一套。VS Code 的 Copilot 擴充套件則有第三套。一支做了「Postgres 查詢」工具的團隊，得把同一個工具寫三遍，各自對應不同宿主的 API。要重用就得複製程式碼。

結果是一次一次性整合的寒武紀大爆發，以及生態系速度上的一道天花板。

MCP 靠標準化線路格式來修正這件事。單一台 MCP 伺服器就能在每一個 MCP 客戶端上運作：Claude Desktop、ChatGPT、Cursor、VS Code、Gemini、Goose、Zed、Windsurf，到 2026 年 4 月已有 300 個以上的客戶端。每月 1.1 億次 SDK 下載。1 萬台以上的公開伺服器。Linux Foundation 於 2025 年 12 月在新成立的 Agentic AI Foundation 之下接手託管。

本階段使用的規格修訂版是 **2025-11-25**。它加上了非同步 Tasks（SEP-1686）、URL 模式的 elicitation（SEP-1036）、帶工具的 sampling（SEP-1577）、增量式範圍同意（SEP-835），以及 OAuth 2.1 的資源指示子語意。階段 13 · 09 到 16 會涵蓋那些擴充。這一課只停在底層。

## 核心概念

### 三個伺服器原語

1. **Tools。** 可呼叫的動作。就是階段 13 · 01 那個四步驟迴圈。
2. **Resources。** 被暴露出來的資料。以 URI 定址的唯讀內容：`file:///path`、`db://query/...`，或自訂的 scheme。
3. **Prompts。** 可重用的模板。在宿主 UI 中是斜線指令；伺服器提供模板，客戶端填入參數。

### 三個客戶端原語

4. **Roots。** 伺服器被允許碰觸的那組 URI。客戶端宣告它們；伺服器遵守它們。
5. **Sampling。** 伺服器請求客戶端的模型執行一次補全。這讓伺服器端不必持有 API 金鑰就能託管代理迴圈。
6. **Elicitation。** 伺服器在流程中途向客戶端的使用者索取結構化輸入。用表單或 URL（SEP-1036）。

MCP 中的每一項能力，都恰好歸屬於這六者之一。階段 13 · 10 到 14 會逐一深入。

### 線路格式：JSON-RPC 2.0

每則訊息都是一個帶下列欄位的 JSON 物件：

- Request：`{jsonrpc: "2.0", id, method, params}`。
- Response：`{jsonrpc: "2.0", id, result | error}`。
- Notification：`{jsonrpc: "2.0", method, params}` —— 沒有 `id`，也不預期有回應。

底層規格約有 15 個方法，依原語分組。重要的那些是：

- `initialize`／`initialized`（握手）
- `tools/list`、`tools/call`
- `resources/list`、`resources/read`、`resources/subscribe`
- `prompts/list`、`prompts/get`
- `sampling/createMessage`（伺服器對客戶端）
- `notifications/tools/list_changed`、`notifications/resources/updated`、`notifications/progress`

### 三階段生命週期

**第 1 階段：initialize。**

客戶端送出帶著自己 `capabilities` 與 `clientInfo` 的 `initialize`。伺服器回覆它自己的 `capabilities`、`serverInfo`，以及它所說的規格版本。客戶端消化完回應後送出 `notifications/initialized`。從這裡開始，雙方都可以依協商好的能力發送請求。

**第 2 階段：operation。**

雙向。客戶端呼叫 `tools/list` 做探索，再用 `tools/call` 呼叫。若伺服器宣告了該能力，它可以送出 `sampling/createMessage`。當伺服器的工具集變動時，它可以送出 `notifications/tools/list_changed`。當使用者變更 root 範圍時，客戶端可以送出 `notifications/roots/list_changed`。

**第 3 階段：shutdown。**

任一方關閉傳輸。MCP 沒有結構化的關閉方法；連線結束的訊號由傳輸層（stdio 或 Streamable HTTP，見階段 13 · 09）承載。

### 能力協商

`initialize` 握手中的 `capabilities` 就是那份契約。以下是伺服器端的範例：

```json
{
  "tools": {"listChanged": true},
  "resources": {"subscribe": true, "listChanged": true},
  "prompts": {"listChanged": true}
}
```

這台伺服器宣告它能吐出 `tools/list_changed` 通知，並支援 `resources/subscribe`。客戶端則以宣告自己的能力來回應：

```json
{
  "roots": {"listChanged": true},
  "sampling": {},
  "elicitation": {}
}
```

如果客戶端沒有宣告 `sampling`，伺服器就不得呼叫 `sampling/createMessage`。反過來也一樣：如果伺服器沒有宣告 `resources.subscribe`，客戶端就不得嘗試訂閱。

這正是防止生態系漂移的機制。一個不支援 sampling 的客戶端仍然是合法的 MCP 客戶端；一台不呼叫 `sampling` 的伺服器也仍然是合法的 MCP 伺服器。它們只是不在這項功能上一起使用而已。

### 結構化內容與錯誤形狀

`tools/call` 回傳一個由定型區塊組成的 `content` 陣列：`text`、`image`、`resource`。階段 13 · 14 會把 MCP Apps（`ui://` 互動式 UI）加進這份清單。

錯誤使用 JSON-RPC 的錯誤碼。規格新增的有：`-32002`「Resource not found」、`-32603`「Internal error」，另外還有以 `error.data` 形式攜帶的 MCP 專屬錯誤資料。

### 客戶端能力對工具呼叫的細節

一個常見的混淆：`capabilities.tools` 指的是客戶端支不支援工具清單變更通知。至於客戶端「會不會」去呼叫某些特定工具，那是由它的模型驅動的執行期選擇，不是能力旗標。能力旗標是規格層級的契約。模型的選擇則與之正交。

### 為什麼是 JSON-RPC 而不是 REST？

JSON-RPC 2.0（2010）是一套輕量的雙向協定。REST 則是由客戶端發起的。MCP 需要由伺服器發起的訊息（sampling、通知），所以帶對稱請求／回應形狀的 JSON-RPC 自然合適。JSON-RPC 也能乾淨地疊在 stdio 與 WebSocket／Streamable HTTP 之上，不必重新發明 HTTP 那套請求形狀。

```figure
mcp-tool-call
```

## 框架應用

`code/main.py` 出貨了一個最小的 JSON-RPC 2.0 解析器與產生器，接著手動走過 `initialize` → `tools/list` → `tools/call` → `shutdown` 這串序列，並印出每一則訊息。沒有真正的傳輸；就只有訊息形狀。拿它對照延伸閱讀連結的那份規格，逐一驗證每個封裝。

要看的地方有：

- `initialize` 雙向宣告能力；回應中有 `serverInfo` 與 `protocolVersion: "2025-11-25"`。
- `tools/list` 回傳一個 `tools` 陣列；每一筆都有 `name`、`description`、`inputSchema`。
- `tools/call` 用的是 `params.name` 與 `params.arguments`。
- 回應的 `content` 是一個由 `{type, text}` 區塊組成的陣列。

## 產出交付

這一課產出 `outputs/skill-mcp-handshake-tracer.md`。給定一份 pcap 風格的 MCP 客戶端—伺服器互動逐字記錄，這項技能會為每則訊息標註它屬於哪個原語、哪個生命週期階段，以及它依賴哪一項能力。

## 練習

1. 跑一次 `code/main.py`。找出能力協商發生的那一行，並描述如果伺服器沒有宣告 `tools.listChanged` 會有什麼不同。

2. 擴充解析器以處理 `notifications/progress`。訊息形狀是：`{method: "notifications/progress", params: {progressToken, progress, total}}`。在一次長時間執行的 `tools/call` 進行中吐出它，並確認客戶端的處理器會顯示一條進度條。

3. 把 MCP 2025-11-25 規格從頭讀到尾 —— 整份文件大約 80 頁。找出那個多數伺服器「不」需要的能力旗標。提示：它和資源訂閱有關。

4. 在紙上勾勒出：一項假想的「排程任務」功能會歸屬於哪個原語。（提示：伺服器希望客戶端在排定的時間呼叫它。今天這六個原語沒有一個吻合。）MCP 的 2026 路線圖有一份針對此事的 SEP 草案。

5. 從 GitHub 上某台開放的 MCP 伺服器抓一份工作階段日誌來解析。數一數 request、response 與 notification 各有多少則。算出流量中生命週期與 operation 各佔多少比例。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| MCP | 「Model Context Protocol」 | 用於模型對工具之探索與呼叫的開放協定 |
| 伺服器原語 | 「伺服器暴露出什麼」 | tools（動作）、resources（資料）、prompts（模板） |
| 客戶端原語 | 「客戶端讓伺服器用什麼」 | roots（範圍）、sampling（LLM 回呼）、elicitation（使用者輸入） |
| JSON-RPC 2.0 | 「那套線路格式」 | 對稱的 request／response／notification 封裝 |
| `initialize` 握手 | 「能力協商」 | 第一組訊息往返；伺服器與客戶端各自宣告支援的功能 |
| `tools/list` | 「探索」 | 客戶端向伺服器索取它當前的工具集 |
| `tools/call` | 「呼叫」 | 客戶端請伺服器帶著參數執行某個工具 |
| `notifications/*_changed` | 「變更事件」 | 伺服器告訴客戶端它的原語清單變了 |
| 內容區塊 | 「定型的結果」 | 工具結果中的 `{type: "text" \| "image" \| "resource" \| "ui_resource"}` |
| SEP | 「Spec Evolution Proposal」 | 具名的草案提案（例如非同步 Tasks 的 SEP-1686） |

## 延伸閱讀

- [Model Context Protocol — Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) —— 權威的規格文件
- [Model Context Protocol — Architecture concepts](https://modelcontextprotocol.io/docs/concepts/architecture) —— 六原語的心智模型
- [Anthropic — Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) —— 2024 年 11 月的發布文
- [MCP blog — First MCP anniversary](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) —— 週年回顧與 2025-11-25 規格的變動
- [WorkOS — MCP 2025-11-25 spec update](https://workos.com/blog/mcp-2025-11-25-spec-update) —— SEP-1686、1036、1577、835 與 1724 的摘要
