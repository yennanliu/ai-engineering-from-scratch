# 打造一個 MCP 客戶端 —— 探索、呼叫、工作階段管理

> 多數 MCP 內容出貨的是伺服器教學，對客戶端則揮揮手帶過。困難的編排恰恰住在客戶端程式碼裡：行程啟動、能力協商、跨多台伺服器合併工具清單、sampling 回呼、重連，以及命名空間衝突的解決。這一課會做一個多伺服器客戶端，把三台不同的 MCP 伺服器抬進單一個扁平的工具命名空間，供模型使用。

**類型：** 實作
**程式語言：** Python (stdlib, multi-server MCP client)
**先修單元：** 階段 13 · 07（打造一台 MCP 伺服器）
**時間：** 約 75 分鐘

## 學習目標

- 以子行程的方式啟動一台 MCP 伺服器、完成 `initialize`，並送出一則 `notifications/initialized`。
- 維護每台伺服器各自的工作階段狀態（能力、工具清單、最後看到的通知 id）。
- 把多台伺服器的工具清單合併進單一個命名空間，並處理衝突。
- 把一次工具呼叫路由到擁有它的那台伺服器，並把回應重組起來。

## 問題所在

一個真正的代理宿主（Claude Desktop、Cursor、Goose、Gemini CLI）會同時載入多台 MCP 伺服器。使用者可能同時跑著一台檔案系統伺服器、一台 Postgres 伺服器與一台 GitHub 伺服器。客戶端的職責是：

1. 啟動每一台伺服器。
2. 各自獨立地握手。
3. 對每一台呼叫 `tools/list`，並把結果攤平。
4. 當模型吐出 `notes_search` 時，在合併後的命名空間中查出它，並路由到正確的伺服器。
5. 處理來自任何一台伺服器的通知（`tools/list_changed`）而不阻塞。
6. 在傳輸失敗時重連。

把這些全部手工做出來，正是「玩具」與「堪用」之間的分野。官方 SDK 把這些包起來了，但那套心智模型得是你自己的。

## 核心概念

### 子行程啟動

用 `subprocess.Popen` 搭配 `stdin=PIPE, stdout=PIPE, stderr=PIPE`。設 `bufsize=1` 並使用文字模式，以便逐行讀取。每台伺服器是一個行程；客戶端每台伺服器各持有一個 `Popen` 把手。

### 每台伺服器的工作階段狀態

每台伺服器各有一個 `Session` 物件，內含：

- `process` —— 那個 Popen 把手。
- `capabilities` —— 伺服器在 `initialize` 時宣告的內容。
- `tools` —— 最後一次 `tools/list` 的結果。
- `pending` —— 從請求 id 到一個等待回應的 promise／future 的映射。

請求本質上是非同步的；當伺服器 B 的呼叫進行到一半時，送給伺服器 A 的 `tools/call` 不得被阻塞。要嘛用執行緒配佇列，要嘛用 asyncio。

### 合併後的命名空間

當客戶端看到彙總後的工具清單時，名稱可能會撞到。兩台伺服器可能都暴露了 `search`。客戶端有三種選項：

1. **以伺服器名稱作前綴。** `notes/search`、`files/search`。清楚，但醜。
2. **靜默的先到先贏。** 較晚那台伺服器的 `search` 覆蓋掉較早的。有風險；它把衝突藏起來了。
3. **拒絕衝突。** 拒絕載入第二台伺服器；通知使用者。對安全敏感的宿主而言最安全。

Claude Desktop 用的是伺服器名稱前綴。Cursor 用的是帶明確錯誤的拒絕衝突。VS Code MCP 同樣採用伺服器名稱前綴。

### 路由

合併之後，一張分派表把 `tool_name -> session` 映射起來。模型依名稱吐出一次呼叫；客戶端找到對應的工作階段，把一則 `tools/call` 訊息寫進那台伺服器的 stdin，然後等待回應。

### Sampling 回呼

如果伺服器在 `initialize` 時宣告了 `sampling` 能力，它就可以送出 `sampling/createMessage`，請客戶端跑它的 LLM。客戶端必須：

1. 阻擋對那台伺服器的後續請求，直到這次取樣有結果為止；若它的實作支援並行，也可以做管線化。
2. 呼叫它的 LLM 供應商。
3. 把回應送回伺服器。

單元 11 會從頭到尾講 sampling。這一課為求完整只放了一個樁。

### 通知處理

`notifications/tools/list_changed` 意味著要重新呼叫 `tools/list`。`notifications/resources/updated` 意味著若那項資源正在使用中就要重讀。通知不得產生回應 —— 不要試圖去 ack 它們。

一個常見的客戶端 bug：在 `tools/call` 上阻塞了讀取迴圈，而此時串流裡正躺著一則通知。請用一條背景讀取執行緒，把每一則訊息推進佇列；主執行緒再出列並分派。

### 重連

傳輸可能失敗：伺服器崩潰、OS 殺掉行程、stdio 管線斷掉。客戶端偵測到 stdout 上的 EOF，就把那個工作階段視為已死。選項有：

- 靜默重啟伺服器並重新握手。對純唯讀的伺服器沒問題。
- 把失敗呈現給使用者。對帶使用者可見工作階段的有狀態伺服器沒問題。

階段 13 · 09 會談 Streamable HTTP 的重連語意；stdio 則簡單得多。

### Keepalive 與工作階段 id

Streamable HTTP 用一個 `Mcp-Session-Id` 標頭。stdio 則沒有工作階段 id —— 行程的身分「就是」那個工作階段。keepalive ping 是選配的；stdio 管線不會因為閒置而斷掉。

## 框架應用

`code/main.py` 以子行程的方式啟動三台模擬的 MCP 伺服器，各自握手，合併它們的工具清單，並把工具呼叫路由到正確的那一台。那些「伺服器」其實是另外幾個跑著玩具回應器的 Python 行程（沒有真正的 LLM）。跑跑看，你會看到：

- 三次初始化，各帶自己的能力集。
- 三份 `tools/list` 結果合併成一個 7 個工具的命名空間。
- 一次基於工具名稱的路由決策。
- 一次靠命名空間前綴避免掉的衝突。

要看的地方有：

- `Session` 這個 dataclass 乾淨地持有每台伺服器的狀態。
- 背景讀取執行緒把 stdout 上的每一行都出列，而不阻塞主執行緒。
- 分派表就是一個簡單的 `dict[str, Session]`。
- 衝突處理是明確寫出來的：當兩台伺服器宣告同一個名稱時，較晚那個會被加上前綴改名。

## 產出交付

這一課產出 `outputs/skill-mcp-client-harness.md`。給定一份宣告式的 MCP 伺服器清單（名稱、指令、參數），這項技能會產出一套測試框架，負責啟動它們、合併工具清單，並出貨一個帶衝突解決的路由函式。

## 練習

1. 跑一次 `code/main.py`，看看伺服器啟動的日誌。用 SIGTERM 殺掉其中一個模擬伺服器行程，觀察客戶端如何偵測到 EOF 並把那個工作階段標記為已死。

2. 實作命名空間前綴。當兩台伺服器都暴露 `search` 時，把第二個改名為 `<server>/search`。更新分派表並驗證工具呼叫路由正確。

3. 為伺服器重啟加上一套連線池風格的退避機制：連續失敗時指數退避，上限 30 秒，失敗三次後對使用者發出一則通知。

4. 勾勒一個支援 100 台並行 MCP 伺服器的客戶端。什麼資料結構會取代那個簡單的分派 dict？（提示：用 trie 做前綴命名空間，再加上一個「每台伺服器工具數」的指標。）

5. 把這個客戶端移植到官方的 MCP Python SDK。SDK 包了 `stdio_client` 與 `ClientSession`。程式碼應該會從約 200 行縮到約 40 行，同時保留多伺服器路由。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| MCP 客戶端 | 「代理宿主」 | 啟動伺服器並編排工具呼叫的那個行程 |
| 工作階段 | 「每台伺服器的狀態」 | 能力、工具清單，以及待處理請求的簿記 |
| 合併命名空間 | 「一份工具清單」 | 橫跨所有活躍伺服器的扁平工具名稱集合 |
| 命名空間衝突 | 「兩台伺服器同名工具」 | 客戶端必須為重複者加前綴、拒絕，或先到先贏 |
| 路由 | 「這次呼叫歸誰？」 | 從工具名稱分派到擁有它的伺服器 |
| 背景讀取器 | 「非阻塞的 stdout」 | 把伺服器 stdout 抽進佇列的執行緒或任務 |
| Sampling 回呼 | 「LLM 即服務」 | 客戶端用來處理伺服器發來的 `sampling/createMessage` 的處理器 |
| `notifications/*_changed` | 「原語變動了」 | 訊號：客戶端必須重新探索或重新讀取 |
| 重連政策 | 「伺服器掛掉時」 | 傳輸失敗時的重啟語意 |
| stdio 工作階段 | 「行程 = 工作階段」 | 沒有工作階段 id；子行程的生命週期就是那個工作階段 |

## 延伸閱讀

- [Model Context Protocol — Client spec](https://modelcontextprotocol.io/specification/2025-11-25/client) —— 權威的客戶端行為
- [MCP — Quickstart client guide](https://modelcontextprotocol.io/quickstart/client) —— 用 Python SDK 寫的 hello world 客戶端教學
- [MCP Python SDK — client module](https://github.com/modelcontextprotocol/python-sdk) —— 作為參考的 `ClientSession` 與 `stdio_client`
- [MCP TypeScript SDK — Client](https://github.com/modelcontextprotocol/typescript-sdk) —— TS 的對應實作
- [VS Code — MCP in extensions](https://code.visualstudio.com/api/extension-guides/ai/mcp) —— VS Code 如何在單一編輯器宿主中多工多台 MCP 伺服器
