# 打造一台 MCP 伺服器 —— Python + TypeScript SDK

> 多數 MCP 教學只示範 stdio 的 hello world。一台真正的伺服器會同時暴露工具、資源與提示詞，處理能力協商，吐出結構化的錯誤，而且在各家 SDK 上行為一致。這一課會從頭到尾做一台筆記伺服器：stdlib 的 stdio 傳輸、JSON-RPC 分派、三個伺服器原語，以及一種純函式風格 —— 等你要畢業時，它能直接放進 Python SDK 的 FastMCP 或 TypeScript SDK。

**類型：** 實作
**程式語言：** Python (stdlib, stdio MCP server)
**先修單元：** 階段 13 · 06（MCP 基礎）
**時間：** 約 75 分鐘

## 學習目標

- 實作 `initialize`、`tools/list`、`tools/call`、`resources/list`、`resources/read`、`prompts/list` 與 `prompts/get` 這些方法。
- 寫一個從 stdin 讀取 JSON-RPC 訊息、把回應寫到 stdout 的分派迴圈。
- 依 JSON-RPC 2.0 規格與 MCP 額外的錯誤碼，吐出結構化的錯誤回應。
- 把一個 stdlib 實作畢業到 FastMCP（Python SDK）或 TypeScript SDK，而不必重寫工具邏輯。

## 問題所在

在你能用上遠端傳輸（階段 13 · 09）或認證層（階段 13 · 16）之前，你需要一台乾淨的本機伺服器。本機意味著 stdio：伺服器由客戶端以子行程的方式啟動，訊息以換行分隔的形式流經 stdin／stdout。

2025-11-25 版規格規定，stdio 訊息編碼成 JSON 物件並帶明確的 `\n` 分隔符。這裡沒有 SSE；SSE 是舊的遠端模式，正在 2026 年年中被移除（Atlassian 的 Rovo MCP 伺服器於 2026 年 6 月 30 日棄用它；Keboola 則是 2026 年 4 月 1 日）。就 stdio 而言，每行一個 JSON 物件就是它線路格式的全部。

筆記伺服器是個好形狀，因為它把三個伺服器原語都操練到了。工具做變更（`notes_create`）。資源暴露資料（`notes://{id}`）。提示詞出貨模板（`review_note`）。這一課的形狀可以類推到任何領域。

## 核心概念

### 分派迴圈

```
loop:
  line = stdin.readline()
  msg = json.loads(line)
  if has id:
    handle request -> write response
  else:
    handle notification -> no response
```

三條規則：

- 不要把任何不是 JSON-RPC 封裝的東西印到 stdout。除錯日誌走 stderr。
- 每個 request 都「必須」對應一個帶相同 `id` 的 response。
- Notification「絕不可」被回應。

### 實作 `initialize`

```python
def initialize(params):
    return {
        "protocolVersion": "2025-11-25",
        "capabilities": {
            "tools": {"listChanged": True},
            "resources": {"listChanged": True, "subscribe": False},
            "prompts": {"listChanged": False},
        },
        "serverInfo": {"name": "notes", "version": "1.0.0"},
    }
```

只宣告你支援的東西。客戶端靠這組能力集來為功能設閘門。

### 實作 `tools/list` 與 `tools/call`

`tools/list` 回傳 `{tools: [...]}`，每一筆都有 `name`、`description`、`inputSchema`。`tools/call` 接收 `{name, arguments}`，並回傳 `{content: [blocks], isError: bool}`。

內容區塊是定型的。最常見的有：

```json
{"type": "text", "text": "Found 2 notes"}
{"type": "resource", "resource": {"uri": "notes://14", "text": "..."}}
{"type": "image", "data": "<base64>", "mimeType": "image/png"}
```

工具錯誤有兩種形狀。協定層級的錯誤（未知方法、參數錯誤）是 JSON-RPC 錯誤。工具層級的錯誤（呼叫合法但工具失敗了）則以 `{content: [...], isError: true}` 回傳。這讓模型能在自己的上下文裡看見那次失敗。

### 實作資源

資源在設計上就是唯讀的。`resources/list` 回傳一份清單；`resources/read` 回傳內容。URI 可以是 `file://...`、`http://...`，或像 `notes://` 這樣的自訂 scheme。

當你把資料以資源而非工具的形式暴露時：

- 模型不會「呼叫」它；客戶端可以在使用者要求時把它注入上下文。
- 訂閱讓伺服器能在資源變動時推送更新（階段 13 · 10）。
- 階段 13 · 14 會用 `ui://` 把它延伸成互動式資源。

### 實作提示詞

提示詞是帶具名參數的模板。宿主會把它們呈現成斜線指令。一個 `review_note` 提示詞可能接收一個 `note_id` 參數，並產出一份多訊息的提示詞模板，交由客戶端餵給它的模型。

### stdio 傳輸的微妙之處

- 以換行分隔的 JSON。沒有長度前綴的封框。
- 不要做緩衝。每次寫入之後都 `sys.stdout.flush()`。
- 生命週期由客戶端掌控。stdin 關閉（EOF）時，乾淨地結束。
- 不要靜默處理 SIGPIPE；記錄下來然後退出。

### 註記

每個工具都可以帶 `annotations` 來描述安全性質：

- `readOnlyHint: true` —— 純讀取，重試也安全。
- `destructiveHint: true` —— 不可逆的副作用；客戶端應該要求確認。
- `idempotentHint: true` —— 同樣的輸入產生同樣的輸出。
- `openWorldHint: true` —— 會與外部系統互動。

客戶端靠這些來決定 UX（確認對話框、狀態指示器）與路由（階段 13 · 17）。

### 畢業路徑

`code/main.py` 裡那台 stdlib 伺服器大約 180 行。FastMCP（Python）把同樣的邏輯收攏成裝飾器風格：

```python
from fastmcp import FastMCP
app = FastMCP("notes")

@app.tool()
def notes_search(query: str, limit: int = 10) -> list[dict]:
    ...
```

TypeScript SDK 有對等的形狀。等你準備好，畢業路徑是直接替換的；那些概念（能力、分派、內容區塊）都一樣。

```figure
t3-dispatch-loop
```

## 框架應用

`code/main.py` 是一台完整的、跑在 stdio 上、純 stdlib 的筆記 MCP 伺服器。它處理 `initialize`、三個工具（`notes_list`、`notes_search`、`notes_create`）的 `tools/list` 與 `tools/call`、每則筆記的 `resources/list` 與 `resources/read`，以及一個 `review_note` 提示詞。你可以用管線灌 JSON-RPC 訊息來驅動它：

```
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python main.py
```

要看的地方有：

- 分派器是一個以方法名稱為鍵的 `dict[str, Callable]`。
- 每個工具執行器回傳的是一串內容區塊，不是一個裸字串。
- 執行器拋出例外時，`isError: true` 會被設上。

## 產出交付

這一課產出 `outputs/skill-mcp-server-scaffolder.md`。給定一個領域（筆記、工單、檔案、資料庫），這項技能會鷹架出一台 MCP 伺服器，附上正確的工具／資源／提示詞劃分與 SDK 畢業路徑。

## 練習

1. 跑一次 `code/main.py`，用手工打造的 JSON-RPC 訊息驅動它。操練 `notes_create`，接著用 `resources/read` 把新筆記取回來。

2. 加上一個帶 `annotations: {destructiveHint: true}` 的 `notes_delete` 工具。驗證客戶端會呈現一個確認對話框（這需要一個真正的宿主；Claude Desktop 可以）。

3. 實作 `resources/subscribe`，讓伺服器在筆記被修改時推送 `notifications/resources/updated`。再加上一個 keepalive 任務。

4. 把這台伺服器移植到 FastMCP。那個 Python 檔應該會縮到 80 行以內。線路上的行為必須一模一樣；用同一套 JSON-RPC 測試框架驗證。

5. 讀規格的 `server/tools` 章節，找出一個本課伺服器沒有實作的工具定義欄位。（提示：有好幾個；挑一個把它加上去。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| MCP 伺服器 | 「那個暴露工具的東西」 | 在 stdio 或 HTTP 上說 MCP JSON-RPC 的行程 |
| stdio 傳輸 | 「子行程模型」 | 伺服器由客戶端啟動；透過 stdin／stdout 溝通 |
| 分派器 | 「方法路由器」 | 從 JSON-RPC 方法名稱到處理函式的映射 |
| 內容區塊 | 「工具結果的一塊」 | 工具回應中 `content` 陣列裡的定型元素 |
| `isError` | 「工具層級的失敗」 | 表示工具失敗了；與 JSON-RPC 錯誤區分開來 |
| 註記 | 「安全提示」 | readOnly／destructive／idempotent／openWorld 這幾個旗標 |
| FastMCP | 「Python SDK」 | 疊在 MCP 協定之上、基於裝飾器的高階框架 |
| 資源 URI | 「可定址的資料」 | `file://`、`db://` 或自訂 scheme，用來指認一項資源 |
| 提示詞模板 | 「斜線指令簡報」 | 由伺服器提供、帶參數插槽、給宿主 UI 用的模板 |
| 能力宣告 | 「功能開關」 | 在 `initialize` 中依原語宣告的各項旗標 |

## 延伸閱讀

- [Model Context Protocol — Python SDK](https://github.com/modelcontextprotocol/python-sdk) —— 作為參考的 Python 實作
- [Model Context Protocol — TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) —— 平行的 TS 實作
- [FastMCP — server framework](https://gofastmcp.com/) —— MCP 伺服器的裝飾器風格 Python API
- [MCP — Quickstart server guide](https://modelcontextprotocol.io/quickstart/server) —— 使用任一 SDK 的端到端教學
- [MCP — Server tools spec](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) —— tools/* 訊息的完整參考
