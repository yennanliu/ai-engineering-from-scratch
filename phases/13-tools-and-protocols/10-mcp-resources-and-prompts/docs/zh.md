# MCP 資源與提示詞 —— 工具之外的上下文暴露

> 工具拿走了 MCP 九成的注意力。另外兩個伺服器原語解決的是不同的問題。資源把資料暴露出來供讀取；提示詞則把可重用的模板暴露成斜線指令。許多伺服器應該改用資源，而不是把讀取包成工具；應該改用提示詞，而不是把工作流程寫死在客戶端的提示詞裡。這一課會替那條決策規則命名，並走過 `resources/*` 與 `prompts/*` 這些訊息。

**類型：** 實作
**程式語言：** Python (stdlib, resource + prompt handler)
**先修單元：** 階段 13 · 07（MCP 伺服器）
**時間：** 約 45 分鐘

## 學習目標

- 針對給定的領域，決定一項能力該暴露成工具、資源，還是提示詞。
- 實作 `resources/list`、`resources/read`、`resources/subscribe`，並處理 `notifications/resources/updated`。
- 實作帶參數模板的 `prompts/list` 與 `prompts/get`。
- 辨識宿主在什麼情況下把提示詞呈現成斜線指令，又在什麼情況下自動注入為上下文。

## 問題所在

一台為筆記應用寫的天真 MCP 伺服器，會把每樣東西都暴露成工具：`notes_read`、`notes_list`、`notes_search`。這等於把每一次資料存取都包進一次由模型驅動的工具呼叫。後果是：

- 每一個可能受惠於上下文的查詢，模型都得決定要不要呼叫 `notes_read`。
- 唯讀內容無法被訂閱，也無法串流到宿主的側邊面板。
- 客戶端 UI（Claude Desktop 的資源附加面板、Cursor 的「Include file」選擇器）呈現不了那些資料。

正確的劃分是：把資料暴露成資源，把會變更狀態或需要運算的動作暴露成工具，把可重用的多步驟工作流程暴露成提示詞。每個原語都有它自己的 UX 承擔特性與存取模式。

## 核心概念

### 工具對資源對提示詞 —— 那條決策規則

| 能力 | 原語 |
|------------|-----------|
| 使用者想搜尋、篩選或轉換資料 | tool |
| 使用者想讓宿主把這份資料納入上下文 | resource |
| 使用者想要一套可以重跑的模板化工作流程 | prompt |

指導原則：如果模型在每一次相關查詢時去呼叫它都有好處，那它是工具。如果使用者把它附加到一段對話中有好處，那它是資源。如果使用者想重用的單位是一整套多步驟工作流程，那它是提示詞。

### 資源

`resources/list` 回傳 `{resources: [{uri, name, mimeType, description?}]}`。`resources/read` 接收 `{uri}` 並回傳 `{contents: [{uri, mimeType, text | blob}]}`。

URI 可以是任何可定址的東西：

- `file:///Users/alice/notes/mcp.md`
- `postgres://my-db/query/SELECT ...`
- `notes://note-14`（自訂 scheme）
- `memory://session-2026-04-22/recent`（伺服器專屬）

`contents[]` 同時支援文字與二進位。二進位使用 `blob`（一個 base64 編碼的字串）加上一個 `mimeType`。

### 資源訂閱

在 capabilities 中宣告 `{resources: {subscribe: true}}`。客戶端呼叫 `resources/subscribe {uri}`。資源變動時，伺服器送出 `notifications/resources/updated {uri}`。客戶端再重讀。

使用情境：一台以磁碟上檔案為資源的筆記伺服器；一個檔案監看器觸發更新通知；當檔案在宿主之外被編輯時，Claude Desktop 就把它重新拉進上下文。

### 資源模板（2025-11-25 新增）

`resourceTemplates` 讓你能暴露一個帶參數的 URI 模式：`notes://{id}`，並以 `id` 作為補全目標。客戶端就能在資源選擇器中自動補全那些 id。

### 提示詞

`prompts/list` 回傳 `{prompts: [{name, description, arguments?}]}`。`prompts/get` 接收 `{name, arguments}` 並回傳 `{description, messages: [{role, content}]}`。

提示詞是一份會被填成訊息串的模板，由宿主餵給它的模型。舉例來說，一個 `code_review` 提示詞接收一個 `file_path` 參數，並回傳一段三則訊息的序列：一則系統訊息、一則帶檔案內容的使用者訊息，以及一則帶推理模板的 assistant 開場。

### 宿主與提示詞

Claude Desktop、VS Code 與 Cursor 都把提示詞呈現成聊天 UI 中的斜線指令。使用者輸入 `/code_review`，再從一張表單中挑選參數。伺服器的提示詞，就是「使用者的捷徑」與「實際送給模型的完整提示詞」之間的那份契約。

不是每個客戶端都已經支援提示詞 —— 請查看能力協商的結果。若伺服器宣告了提示詞能力，但客戶端不支援，那就只是看不到那些斜線指令而已。

### 「清單已變更」通知

當集合變動時，資源與提示詞都會吐出 `notifications/list_changed`。一台剛匯入 20 則新筆記的筆記伺服器會吐出 `notifications/resources/list_changed`；客戶端於是重新呼叫 `resources/list` 把新增的抓進來。

### 內容型別的慣例

文字用：`mimeType: "text/plain"`、`text/markdown`、`application/json`。
二進位用：`image/png`、`application/pdf`，再加上 `blob` 欄位。
MCP Apps（單元 14）用：在 `ui://` URI 中使用 `text/html;profile=mcp-app`。

### 動態資源

資源 URI 不一定要對應一個靜態檔案。`notes://recent` 可以在每次讀取時回傳最新的五則筆記。`db://query/users/active` 可以執行一次帶參數的查詢。伺服器可以自由地動態計算內容。

規則是：如果客戶端能依 URI 做快取，那個 URI 就必須穩定。如果那次運算是一次性的，URI 就該帶上時間戳或 nonce，好讓客戶端的快取不會過期失效。

### 訂閱對輪詢

具備訂閱能力的客戶端會透過 `notifications/resources/updated` 收到伺服器推播。不支援訂閱的客戶端或宿主，則靠重讀來輪詢。兩者都符合規格。伺服器的能力宣告會告訴客戶端它支援哪一種。

訂閱的代價是：伺服器上每個工作階段的狀態（誰訂閱了什麼）。要讓訂閱集合有界；斷線的客戶端應該逾時。

### 提示詞對系統提示詞

MCP 中的提示詞不是系統提示詞。宿主的系統提示詞（它自己的運作指示）與 MCP 提示詞（由伺服器提供、由使用者調用的模板）是並存的。一個行為端正的客戶端，絕不會讓伺服器的提示詞覆寫它自己的系統提示詞；它會把兩者分層疊起來。

## 框架應用

`code/main.py` 在單元 07 那台筆記伺服器上，擴充了以下內容：

- 每則筆記各自的資源（`notes://note-1` 等），並支援 `resources/subscribe`。
- 一個會渲染成三則訊息模板的 `review_note` 提示詞。
- 一個檔案監看器模擬，會在筆記被修改時吐出 `notifications/resources/updated`。
- 一個總是回傳最新五則筆記的 `notes://recent` 動態資源。

跑一次示範，看看完整的流程。

## 產出交付

這一課產出 `outputs/skill-primitive-splitter.md`。給定一台提案中的 MCP 伺服器，這項技能會把每一項能力歸類成 tool／resource／prompt，並附上理由。

## 練習

1. 跑一次 `code/main.py`。觀察初始的資源清單，接著觸發一次筆記編輯，驗證 `notifications/resources/updated` 事件有觸發。

2. 加上一個 `resources/list_changed` 的發送器：當有新筆記被建立時，送出那則通知，好讓客戶端重新探索。

3. 為一台 GitHub MCP 伺服器設計三個提示詞：`summarize_pr`、`triage_issue`、`release_notes`。每個都要有參數 schema。提示詞本體要能不必再修改就直接跑。

4. 從單元 07 的伺服器中挑一個既有工具，判斷它該維持是工具，還是該拆成「資源加工具」這一對。用一句話說明理由。

5. 讀規格的 `server/resources` 與 `server/prompts` 章節。找出 `resources/read` 中那個很少被填、但規格支援的欄位。提示：看看資源內容上的 `_meta`。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| 資源 | 「被暴露出來的資料」 | 以 URI 定址、宿主可讀取的內容 |
| 資源 URI | 「指向資料的指標」 | 帶 scheme 前綴的識別字（`file://`、`notes://` 等） |
| `resources/subscribe` | 「盯著變化」 | 由客戶端選擇加入、針對特定 URI 的伺服器推播更新 |
| `notifications/resources/updated` | 「資源變了」 | 通知客戶端某個已訂閱資源有了新內容的訊號 |
| 資源模板 | 「帶參數的 URI」 | 帶補全提示、供宿主選擇器使用的 URI 模式 |
| 提示詞 | 「斜線指令模板」 | 帶參數插槽的具名多訊息模板 |
| 提示詞參數 | 「模板輸入」 | 宿主在渲染前會蒐集的定型參數 |
| `prompts/get` | 「渲染模板」 | 伺服器回傳填好的訊息串 |
| 內容區塊 | 「定型的一塊」 | `{type: text \| image \| resource \| ui_resource}` |
| 斜線指令 UX | 「使用者捷徑」 | 宿主把提示詞呈現成以 `/` 開頭的指令 |

## 延伸閱讀

- [MCP — Concepts: Resources](https://modelcontextprotocol.io/docs/concepts/resources) —— 資源 URI、訂閱與模板
- [MCP — Concepts: Prompts](https://modelcontextprotocol.io/docs/concepts/prompts) —— 提示詞模板與斜線指令整合
- [MCP — Server resources spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) —— `resources/*` 訊息的完整參考
- [MCP — Server prompts spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts) —— `prompts/*` 訊息的完整參考
- [MCP — Protocol info site: resources](https://modelcontextprotocol.info/docs/concepts/resources/) —— 在官方文件之外展開說明的社群指南
