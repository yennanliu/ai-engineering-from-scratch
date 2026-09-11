# MCP 基礎：無狀態請求與 JSON-RPC

> 現代 MCP 沒有握手，也沒有協定工作階段。每一則請求都必須自帶足夠的中繼資料，才能被單獨理解、授權、路由與重試。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 13，單元 01 至 05
**時間：** 約 55 分鐘

## 學習目標

- 分辨 MCP 的伺服器原語與它的客戶端功能。
- 為 MCP `2026-07-28` 建構有效的 JSON-RPC 2.0 請求與回應。
- 在每一則請求上附加協定版本、客戶端能力與客戶端身分。
- 不靠握手就使用 `server/discover`，並處理 `UnsupportedProtocolVersionError`。
- 追蹤一則獨立請求，從驗證一路走到完整結果。

## 問題所在

一台 MCP 伺服器可能在同一個行程或同一個 HTTP worker 上，連續收到來自不同客戶端、能力也不同的兩則請求。如果伺服器記住了上一則請求宣告了什麼，它就可能套用錯誤的權限，或回傳錯誤的線路形狀。

MCP `2026-07-28` 消除了這種模稜兩可。協定核心是無狀態的。伺服器必須從「當下這則請求」來決定怎麼處理當下這則請求，而不是從連線歷史。

這改變了心智模型。舊的順序是先連線、再握手、然後才操作。現代的順序更簡單：

1. 客戶端送出一則自我描述的請求。
2. 伺服器驗證那則請求的版本與能力。
3. 伺服器處理該方法。
4. 伺服器回傳一個帶型別的結果，或一個 JSON-RPC 錯誤。

下一則請求從頭把同樣的流程再走一遍。

## 核心概念

### 伺服器原語

MCP 伺服器暴露三種主要原語：

1. **工具（Tools）** 是由模型控制的動作，用 `tools/list` 發現、用 `tools/call` 調用。
2. **資源（Resources）** 是以 URI 定址的資料，用 `resources/list` 發現、用 `resources/read` 取得。
3. **提示詞（Prompts）** 是可重用的模板，用 `prompts/list` 發現、用 `prompts/get` 算繪。

Roots、sampling 與 logging 為了相容性仍留在 `2026-07-28` 的 schema 裡，但已被棄用。新的實作應該改用明確的工具或資源輸入來取代 roots，用模型供應商的 API 直接處理 sampling，並用 stderr 或 OpenTelemetry 來做 logging。Elicitation 仍然可以透過 Multi Round-Trip Requests 使用：伺服器回傳一則輸入請求，客戶端再重試原本的操作。現代伺服器絕不主動發起獨立的 JSON-RPC 請求。

### JSON-RPC 信封

MCP 使用 JSON-RPC 2.0：

- 請求：`{jsonrpc, id, method, params}`
- 回應：`{jsonrpc, id, result}` 或 `{jsonrpc, id, error}`
- 通知：`{jsonrpc, method, params}`，沒有 `id`

請求的 `id` 只用來對應一則回應。它不會建立協定工作階段。

### 必要的請求中繼資料

每一則現代請求都在 `params` 裡帶一個 `_meta` 物件：

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "tools/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
      "io.modelcontextprotocol/clientInfo": {
        "name": "course-client",
        "version": "1.0.0"
      }
    }
  }
}
```

協定版本與客戶端能力是必填。客戶端身分是建議填寫。它是自行宣告、供顯示與除錯用的資料，不是安全憑證。

伺服器不得從先前的請求、stdio 行程、HTTP 連線，或單靠某個傳輸標頭，去推斷這些值。

### 完整結果與伺服器身分

每一個成功的現代結果都包含 `resultType`。一般的最終結果用 `"complete"`。伺服器也應該在結果的中繼資料裡表明自己的身分：

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "resultType": "complete",
    "tools": [],
    "ttlMs": 30000,
    "cacheScope": "public",
    "_meta": {
      "io.modelcontextprotocol/serverInfo": {
        "name": "notes-server",
        "version": "1.0.0"
      }
    }
  }
}
```

`tools/list`、`resources/list`、`prompts/list`、`resources/templates/list`、`resources/read` 與 `server/discover` 都是可快取的結果。它們會帶上 `ttlMs` 與 `cacheScope`。一個安全的預設是 `ttlMs: 0` 加上 `cacheScope: "private"`。清單項目應該有確定性的排序，這樣等價的回應才會產生穩定的快取鍵與穩定的模型脈絡。

### 不靠握手的發現

每一台現代伺服器都必須實作 `server/discover`。客戶端可以在呼叫其他方法之前先呼叫它，取得：

- `supportedVersions`
- 伺服器 `capabilities`
- 選用的使用 `instructions`
- 結果 `_meta` 裡的伺服器身分
- 快取提示

發現很有用，但它不是一道關卡。客戶端可以直接先送 `tools/list`，因為那則請求本身已經帶著自己的協定版本與能力。

如果請求的版本不受支援，伺服器回傳 JSON-RPC 錯誤碼 `-32022`，並附上：

```json
{
  "requested": "2027-01-01",
  "supported": ["2026-07-28"]
}
```

客戶端挑一個雙方都支援的現代版本，用一個新的 JSON-RPC 請求 id 重試。

### 一則請求的生命週期

照這個順序追蹤一則現代請求：

1. 解析一個 JSON-RPC 信封。
2. 確認 `jsonrpc` 是 `"2.0"`、`id` 存在、`method` 是字串，而 `params` 是物件。
3. 要求 `params._meta` 裡有版本字串與能力物件；中繼資料格式錯誤或缺漏就是 `-32602`。
4. 在 HTTP 邊界上，把版本、方法與適用的名稱標頭拿去跟主體比對。不一致就是 `-32020`，即使兩個版本值當中有一個本來就不受支援也一樣。
5. 確立一致之後，再把「一致但不受支援」的版本以 `-32022` 拒絕。
6. 檢查必要能力，然後依 `method` 路由，並驗證該方法專屬的參數。
7. 在處理器執行之前，對這個具體操作做認證與授權。
8. 回傳一個帶有伺服器身分的完整結果。
9. 忘掉請求範圍內的協定中繼資料。

這個順序能防止兩個元件解讀成不同的呼叫。閘道不能一邊授權 `Mcp-Name: notes.read`，源站那頭卻執行 `params.name: notes.delete`。它也讓格式錯誤的輸入、標頭混淆、版本協商、能力失敗、授權與處理器失敗，各自留下互不混淆的證據。

關閉 stdin 或一則 HTTP 回應，結束的是傳輸活動。它並不會終止協定工作階段，因為現代 MCP 根本沒有協定工作階段。

### 明確的舊版相容

到 `2025-11-25` 為止的版本使用 `initialize`、`notifications/initialized`、以連線為範圍的能力，而在更早的 Streamable HTTP 上還有選用的協定工作階段。當一個橫跨兩個時代的客戶端要跟舊伺服器對話時，那些行為仍然相關。

讓兩個時代保持分離。現代請求是靠必填的每請求中繼資料來識別。舊版連線只能透過文件明訂的退路來選用。不要把 `initialize` 當成對 `2026-07-28` 伺服器的預設開場。

因此「無狀態」帶有時代專屬的意義。在 `2026-07-28` 裡，它是一條協定不變式：每一則一般請求都能被獨立解讀，而且不存在 MCP 工作階段。在到 `2025-11-25` 為止的版本裡，初始化與協商出來的能力屬於一條連線，所以相容轉接層可以保留那份舊版連線狀態。跨時代的實作不是一台寬鬆的狀態機。它是一個無狀態的現代核心，旁邊擺著一個被隔離的舊版轉接層，而且在任何一邊的解析器啟動之前，就已經做出明確的選擇決定。

這兩種意義都沒有禁止持久的應用狀態。工作流程、任務或草稿都可以藏在共用儲存區裡的一個不透明把手背後。客戶端把那個把手當成一般輸入送出，而每一個副本都要對它的使用做認證與授權。協定脈絡不得洩漏進那個儲存區，被拿來當作被移除的工作階段的替代品。

```figure
mcp-tool-call
```

## 框架應用

`code/main.py` 不靠任何框架，就能建構、驗證、追蹤並分派現代 MCP 訊息。執行：

```bash
python3 code/main.py
python3 -m unittest discover code/tests -v
```

在輸出裡留意三條不變式：

- 每一則請求都重複帶上自己的 `_meta` 欄位。
- 每一個成功的結果都是 `resultType: "complete"`，而且包含伺服器身分。
- 清單結果有確定性排序，並帶著明確的快取提示。

## 產出交付

這一課交付 `outputs/skill-mcp-handshake-tracer.md`。歷史檔名維持不變，但這個產物現在是一支無狀態請求追蹤器。它獨立稽核每一則訊息，只在舊版握手流量真的出現時才把它標記出來。

## 練習

1. 把某一則請求的協定版本改成 `2027-01-01`。確認錯誤碼是 `-32022`，而且 data 公告了受支援的版本。
2. 從第二則請求裡拿掉 `io.modelcontextprotocol/clientCapabilities`。確認伺服器沒有沿用第一則請求的能力。
3. 把記憶體裡的工具登錄表反轉。確認 `tools/list` 仍然回傳同樣的確定性排序。
4. 把 `cacheScope` 從 `public` 改成 `private`。說明這兩種情況下，各有哪些授權脈絡可以重用該回應。
5. 加一個「省略 `clientInfo`」的選用測試。這則請求應該仍然有效，因為客戶端身分是建議填寫，不是必填。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| 無狀態協定 | 每一則請求都自備解讀它所需的中繼資料 |
| 請求中繼資料 | `params._meta` 裡的版本、客戶端能力，以及建議填寫的客戶端身分 |
| `server/discover` | 必備的伺服器方法，提供版本、能力、使用說明與身分 |
| `resultType` | 每一個成功的現代結果上的判別欄位 |
| 可快取結果 | 帶有必填 `ttlMs` 與 `cacheScope` 提示的結果 |
| 協定時代 | 現代的每請求中繼資料，或舊版以連線為範圍的初始化 |
| 傳輸生命期 | 行程、連線或回應串流的生命期，不是協定工作階段狀態 |
| `-32022` | 不支援的協定版本錯誤，附上請求版本與受支援版本 |

## 延伸閱讀

- [MCP Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture)
- [MCP Base Protocol](https://modelcontextprotocol.io/specification/2026-07-28/basic)
- [MCP Server Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [MCP 2026-07-28 Changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
