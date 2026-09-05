# Model Context Protocol（MCP）

> MCP 讓 AI 宿主用同一套協定去發現並調用工具、資源與提示詞。2026-07-28 修訂版把這套協定變成無狀態的：能力與版本脈絡隨著每一次請求一起送出，而不是綁在一次連線的握手裡。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 11 · 09（函數呼叫）、階段 11 · 03（結構化輸出）
**時間：** 約 75 分鐘

## 學習目標

- 分辨 MCP 的宿主、客戶端、伺服器、傳輸層與伺服器原語。
- 建構一則帶有 MCP 2026-07-28 所要求之中繼資料的 JSON-RPC 請求。
- 用 `server/discover` 檢視版本、身分與能力。
- 從工具、資源與提示詞回傳帶型別且具快取意識的結果。
- 說明現代的無狀態 MCP 如何與握手時代的伺服器互通。
- 為一台伺服器選定安全的狀態、傳輸與核准邊界。

## 問題所在

你的應用需要一次資料庫查詢、一個日曆操作，以及一支檔案讀取器。少了共用協定，每一個 AI 宿主都得為這同一批能力自己寫一套發現、調用、錯誤、傳輸與授權的膠水程式碼。

MCP 縮小了那個整合矩陣。伺服器發布一個標準的 JSON-RPC 介面。符合規格的客戶端就能發現這個介面、把它呈現給模型或使用者、調用它，並解讀結果，不需要針對特定伺服器的轉接層。

有一條重要的界線很容易被忽略。MCP 標準化的是「溝通」。它不會決定模型該呼叫哪個工具，不會讓不可信的內容變安全，也不會把一次無狀態的請求變成應用層的持久狀態。那些決定仍然屬於你的宿主與伺服器。

## 核心概念

![MCP 宿主、無狀態請求與伺服器原語](../assets/mcp-architecture.svg)

### 三種伺服器原語

1. **工具（Tools）** 是可呼叫的動作。每個工具都有名稱、描述、JSON Schema 輸入與處理器。
2. **資源（Resources）** 是具名、以 URI 定址、可供客戶端讀取的內容。
3. **提示詞（Prompts）** 是可重用的模板，宿主可以把它暴露給使用者。

宿主就是那個 AI 應用。宿主內部的一個 MCP 客戶端只跟一台伺服器對話。傳輸層負責在兩者之間搬運 JSON-RPC 訊息。

### 無狀態請求取代了握手

MCP 2026-07-28 移除了 `initialize` 與 `notifications/initialized`，也移除了協定層級的工作階段。每一則請求都在 `params._meta` 裡自備解讀它所需的脈絡：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
      "io.modelcontextprotocol/clientInfo": {
        "name": "lesson-client",
        "version": "1.0.0"
      }
    }
  }
}
```

協定版本與客戶端能力是必填。客戶端身分則是建議填寫。缺少 `_meta`、缺少必填欄位，或必填欄位型別錯誤，都算格式錯誤，會回傳 Invalid Params（`-32602`）。一個格式正確但伺服器不支援的版本字串，回傳的是 `UnsupportedProtocolVersionError`（`-32022`）。伺服器不需要翻出先前的協商紀錄，就能處理一則有效的請求。

無狀態不代表應用永遠不能保有狀態。它的意思是：狀態不再藏在一條 MCP 連線或 `Mcp-Session-Id` 背後。如果一段工作流程需要延續性，伺服器會鑄造一個不透明的把手（handle），客戶端在後續呼叫時把那個把手當成一般的工具參數傳回去。授權仍然必須在每一次請求上重新檢查。

### 發現與版本選擇

每一台現代伺服器都實作 `server/discover`。它的結果會公告支援的版本、能力，以及伺服器身分：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "complete",
    "supportedVersions": ["2026-07-28"],
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "ttlMs": 3600000,
    "cacheScope": "public",
    "_meta": {
      "io.modelcontextprotocol/serverInfo": {
        "name": "demo-server",
        "version": "1.0.0"
      }
    }
  }
}
```

客戶端也可以直接呼叫別的方法，然後處理版本錯誤，但走發現流程能讓能力顯示與版本選擇變得明確。不支援的版本會回傳 `UnsupportedProtocolVersionError`，錯誤碼 `-32022`。它的 `data` 裡有 `supported`（伺服器修訂版本的陣列）與 `requested`（被拒絕的那個修訂版本）。

在 stdio 上，橫跨兩個時代的客戶端會先用 `server/discover` 探測。收到發現結果，或收到 `UnsupportedProtocolVersionError` 這類可辨識的現代錯誤，就代表對面是現代伺服器。任何無法被辨識為現代的錯誤或逾時，才允許退回到 2025-11-25 的 `initialize` 流程。舊行為是相容性程式碼，不是現代預設。

### 結果是明確的

2026-07-28 的每一個核心結果都帶有 `resultType`：

- `complete` 代表操作已完成。
- `input_required` 代表伺服器需要再走一趟往返，走的是 Multi Round-Trip Requests 模式。核心伺服器只能從 `tools/call`、`resources/read` 或 `prompts/get` 回傳它。

客戶端必須把沒有 `resultType` 的舊版結果當成 complete。

伺服器應該在每個結果的 `_meta` 裡放進 `io.modelcontextprotocol/serverInfo`。這個身分是自行宣告的，用途是顯示、記錄與除錯，不是拿來做安全決策。

清單與讀取結果還會帶上 `ttlMs` 與 `cacheScope`。一個確定性的 `tools/list` 排序，加上新鮮度提示，讓客戶端能安全地快取發現結果，也改善了提示詞快取的穩定性。`cacheScope: public` 允許共用快取；`private` 則把重用限制在呼叫端的脈絡內。

### 線路格式與傳輸

MCP 使用走 stdio 或 Streamable HTTP 的 JSON-RPC 2.0。

- 請求有 `jsonrpc`、`id`、`method` 與 `params`。
- 回應帶有相對應的 `id`，以及 `result` 或 `error` 其中之一。
- 通知沒有 `id`，也不期待回應。

現代的 Streamable HTTP 暴露單一個接受 POST 的端點。每一則 JSON-RPC 訊息各自走一次 POST。請求型的 POST 會收到一個 JSON 物件，或是一條以最終回應收尾、範圍限於該請求的 Server-Sent Events 串流。被接受的通知型 POST 收到 HTTP 202 且沒有回應主體；這個核心修訂版並未在 Streamable HTTP 上定義任何客戶端到伺服器的通知。

2026-07-28 裡沒有獨立的 MCP GET 串流、沒有 DELETE 工作階段端點、沒有 `Mcp-Session-Id`，也沒有 `Last-Event-ID` 重播。長時間存活的變更通知改用一次 `subscriptions/listen` POST，它的回應會以 SSE 串流的形式保持開啟。

### 不靠伺服器發起請求也能取得客戶端輸入

較舊的修訂版允許伺服器在串流上送出 `sampling/createMessage`、`roots/list` 或 `elicitation/create` 這類請求。現行協定改用 Multi Round-Trip Requests。符合條件的工具呼叫、資源讀取或提示詞取得會回傳 `resultType: input_required`，並至少帶上 `inputRequests` 或 `requestState` 其中之一。客戶端蒐集所需的輸入之後，用一個新的 JSON-RPC ID 重試原本的方法，附上對應的 `inputResponses`，而且若原本有給 `requestState`，就原封不動地回送。若原本沒有 `inputRequests`，重試時就不放 `inputResponses`。

Roots、Sampling 與 Logging 仍然可用，但已被標記為棄用，所以新的實作不該再採用它們。既有的 Roots 或 Sampling 請求要走在 MRTR 的 `inputRequests` 裡面，絕不是獨立的伺服器到客戶端 JSON-RPC 請求。優先採用明確的檔案或目錄參數、資源 URI、伺服器組態，以及直接對接模型供應商。stdio 的診斷訊息寫到 stderr，正式環境的遙測交給 OpenTelemetry。

```figure
mcp-nxm-collapse
```

## 動手實作

### 步驟 1：註冊伺服器介面

即使請求契約改了，註冊本身還是很單純：

```python
server = MCPServer("demo-server")

@server.tool(
    "add",
    "Add two integers.",
    {
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "integer"}
        },
        "required": ["a", "b"]
    }
)
def add(a: int, b: int) -> dict:
    return {"sum": a + b}
```

`code/main.py` 裡實際交付的實作還註冊了一個資源與一個提示詞。它刻意只用標準函式庫，讓你能看見每一層信封，而不是把協定丟給 SDK 代勞。

### 步驟 2：為每一則請求附上中繼資料

```python
def request(method, params=None):
    body_params = dict(params or {})
    body_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {
            "name": "demo-client",
            "version": "1.0.0"
        }
    }
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": body_params
    }
```

不要只把這份中繼資料快取在一個連線物件裡。伺服器會在每一次請求上驗證它。

### 步驟 3：列清單之前可以先發現

呼叫 `server/discover`，選一個支援的版本，再呼叫 `tools/list`。如果你已經知道版本、而且能處理 `-32022`，直接呼叫 `tools/list` 也是合法的。

這份示範會依名稱排序回傳工具清單，並附上 `ttlMs`、`cacheScope`、`resultType` 與伺服器身分。工具呼叫回傳的則是 complete 且不可快取的結果，因為它的輸出可能取決於當下的狀態。

### 步驟 4：把同一則請求映射到 HTTP

一次遠端的 `tools/call` POST 會帶上與 JSON-RPC 主體互相對照的標頭：

```http
POST /mcp HTTP/1.1
Content-Type: application/json
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: add
```

`MCP-Protocol-Version` 標頭必須與 `_meta` 裡的版本一致。`Mcp-Method` 在每一則 JSON-RPC 請求上都是必填，而且必須與 `method` 相符。`Mcp-Name` 只在 `tools/call`、`resources/read` 與 `prompts/get` 上必填，值必須對應工具名稱、資源 URI 或提示詞名稱。缺少必填標頭或內容不一致，會回傳 HTTP 400 與 `HeaderMismatch` 錯誤碼 `-32020`。

### 步驟 5：把安全性擺在協定狀態之外

- 在每一次 HTTP 請求上驗證授權與受眾（audience）。
- 把本機伺服器綁在 localhost，並在 Streamable HTTP 上驗證 `Origin`。
- 用 `destructiveHint: true` 標記會造成變更的工具，並要求宿主核准。
- 明確傳入目錄與檔案範圍，不要依賴已棄用的 Roots。
- 把資源與工具輸出當成不可信的資料。
- 在 stdio 下把 stdout 專留給 JSON-RPC；診斷訊息寫到 stderr。

## 框架應用

在單元目錄底下執行：

```bash
python3 code/main.py
cd code
python3 -m unittest discover tests -v
```

第一行應該回報以協定 `2026-07-28` 發現了 `demo-server`。接著去看 `MCPClient.request`：它為每一次呼叫重新組出 `_meta`。試著把某一則請求的中繼資料拿掉，看伺服器如何拒絕它。

## 產出交付

`outputs/skill-mcp-server-designer.md` 會把一個領域轉成一份無狀態的 MCP 設計。它的驗收門檻要求：一份發現結果、每請求的中繼資料政策、確定性且具快取意識的清單、明確的狀態把手、傳輸標頭、授權，以及核准規則。

## 繼續深入 MCP

這一課給你的是協定模型。階段 13 把四個正式環境的邊界拆成獨立的「建構並驗證」單元：

1. [MCP 工具契約與內容](../../../13-tools-and-protocols/28-mcp-tool-contracts-and-content/docs/en.md) 談封閉輸入 schema、結構化內容、路由中繼資料、不透明分頁、補全授權，以及協定錯誤與工具領域錯誤的差別。
2. [MCP 可靠性、取消與流量控制](../../../13-tools-and-protocols/29-mcp-reliability-cancellation-and-flow-control/docs/en.md) 談請求取消、持久任務取消、期限、冪等性、反壓、代理緩衝與重連行為。
3. [MCP 登錄檔供應鏈、准入、漂移與回滾](../../../13-tools-and-protocols/30-mcp-registry-supply-chain-and-drift/docs/en.md) 談命名空間證明、產物來源、不可變固定、線上漂移、Registry 狀態、准入證據與回滾。
4. [MCP 一致性工程](../../../13-tools-and-protocols/31-mcp-conformance-versioning-and-operations/docs/en.md) 談黃金與負向線路逐字紀錄、嚴格版本時代、SDK 差異、代理證據、遮蔽、健康門檻與發布回滾。

當伺服器要跨越團隊或信任邊界時，請照順序把它們走完。四者合起來，會把你從「這個方法可以動」帶到「這份契約在部署過程中依然安全且可診斷」。

## 練習

1. 加一個 `subtract` 工具，確認 `tools/list` 仍然維持字母排序。
2. 拿掉協定版本那個鍵，驗證會拿到 Invalid Params（`-32602`）。接著送出格式正確但不受支援的版本 `2025-11-25`，驗證 `-32022`，確認 `requested` 原樣回送那個修訂版本，然後從 `supported` 裡挑一個。
3. 在一個建立操作裡加上由伺服器鑄造的 `draftId`，然後在更新時把它列為必要參數。說明為什麼那是應用狀態，而不是協定工作階段。
4. 讓一個需要使用者確認的工具回傳 `input_required`。用新的 ID、一筆 `inputResponses`，以及原封不動的 `requestState` 重試原本的呼叫，而不是自創一個伺服器到客戶端的 JSON-RPC 請求。
5. 勾勒一個橫跨兩個時代的 stdio 客戶端。把結果或可辨識的現代錯誤視為現代，只在遇到無法辨識的錯誤或逾時時，才允許退回 `initialize`。

## 關鍵術語

| 術語 | 大家嘴上說的 | 實際上是什麼 |
|------|-----------------|------------------------|
| MCP | 「LLM 的工具協定」 | 用於伺服器發現、工具、資源、提示詞與擴充的 JSON-RPC 協定 |
| 宿主（Host） | 「那個 AI 應用」 | 擁有模型與 UI，並掛載一個以上的 MCP 客戶端 |
| 客戶端（Client） | 「那個連接器」 | 代表宿主，用 MCP 跟一台伺服器對話 |
| 無狀態 MCP | 「沒有工作階段」 | 每則請求自帶版本與能力；沒有任何協定狀態以連線為鍵 |
| `server/discover` | 「能力探測」 | 必備的伺服器方法，公告版本、能力與身分 |
| `resultType` | 「結果狀態」 | 標記結果是 `complete` 還是 `input_required` |
| 狀態把手（State handle） | 「工作流程 id」 | 由伺服器鑄造、以一般參數傳遞的應用層識別碼 |
| Streamable HTTP | 「遠端傳輸」 | 單一 POST 端點，回應為 JSON 或範圍限於該請求的 SSE |
| MRTR | 「問完再重試」 | 把輸入請求嵌在結果裡，之後重試原本的操作 |

## 延伸閱讀

- [MCP 2026-07-28 重點變更](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- [MCP 伺服器發現](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [MCP Multi Round-Trip Requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 已棄用功能](https://modelcontextprotocol.io/specification/2026-07-28/deprecated)
