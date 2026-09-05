# MCP 資源與提示詞：無狀態伺服器的可定址脈絡

> 工具執行操作。資源暴露可定址的內容。提示詞把使用者挑選的訊息模板打包起來。好的 MCP 伺服器會讓這三份契約各自分離、各自可預期。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 單元 07（打造 MCP 伺服器）、階段 13 單元 09（MCP 傳輸）
**時間：** 約 60 分鐘

## 學習目標

- 從消費端的意圖出發，在工具、資源與提示詞之間做選擇。
- 透過必備的 `server/discover` 公告資源與提示詞介面。
- 建構確定性的 `resources/list` 與 `prompts/list` 結果。
- 套用 `ttlMs` 與 `cacheScope`，同時不外洩使用者專屬資料。
- 對無效或未知的資源 URI 回傳 JSON-RPC 錯誤 `-32602`。
- 開啟一條 `subscriptions/listen` 的 POST 回應串流，並用訂閱 ID 對應每一個事件。
- 把資源內容與提示詞模板視為不可信的伺服器輸出。

## 從消費端出發

誤用 MCP 最容易的方式，就是從實作程式碼開始想。資料庫查詢變成工具，因為函數比較熟悉。可重用的工作流程變成資源，因為它存在檔案裡。提示詞變成隱藏的政策，因為宿主可以把它注入進去。

從「誰在選」以及「他們期待什麼」開始想。

| 原語 | 主要意圖 | 選擇者 | 典型結果 |
|---|---|---|---|
| 工具 | 執行一個操作 | 模型或應用 | 結構化的動作結果 |
| 資源 | 讀取某個 URI 上的內容 | 宿主、應用或使用者 | 文字或二進位內容 |
| 提示詞 | 啟動一段可重用的訊息工作流程 | 使用者透過宿主 UI | 一則或多則提示詞訊息 |

`notes://note-1` 上的一則筆記是資源，因為它是可定址的內容。`delete_note` 是工具，因為它改變狀態。`review_note` 是提示詞，因為使用者選的是一段已備好的審閱工作流程。

不要只為了看起來完整，就把同一個操作同時暴露成三種形式。每多一個介面，就多一份發現、授權、快取、錯誤處理、測試與文件。

## 2026-07-28 的無狀態信封

這一課鎖定 MCP 協定修訂版 `2026-07-28`。這個輪廓裡沒有初始化握手，也沒有協定工作階段。每一則請求都在保留的 `_meta` 鍵裡帶著自己的協定版本與客戶端能力。

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "resources/list",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientInfo": {
        "name": "course-client",
        "version": "1.0.0"
      },
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

伺服器必須實作 `server/discover`。它的結果會公告受支援的版本、資源與提示詞能力、
實作身分，以及快取提示。客戶端可以直接呼叫其他方法，但發現能在它建構 UI 之前，
給它一份穩定的快照。

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "resources": {"listChanged": true, "subscribe": true},
    "prompts": {"listChanged": true}
  },
  "ttlMs": 3600000,
  "cacheScope": "public"
}
```

一般的結果會宣告 `"resultType": "complete"`。回應的 `_meta` 用 `io.modelcontextprotocol/serverInfo` 標明是哪個實作在服務。這份資訊對診斷很有用。它不是認證身分。帶著不受支援之修訂版的請求會回傳 `-32022`，同時附上請求的修訂版與伺服器支援的修訂版。

無狀態契約會改變你的設計直覺。清單不能依賴同一條連線上先前的某次呼叫。授權可以改變可見的集合，因為憑證是請求的輸入，但連線歷史不行。

## 資源是穩定的 URI 契約

資源是由 URI 標識的內容。先設計 URI，再寫處理器。

好的 URI 具備這些性質：

- 穩定到可以加書籤，或在請求之間傳遞。
- 帶有伺服器領域的命名空間。
- 與行程 ID 或連線無關。
- 在存取儲存區之前先驗證。
- 每一次讀取都做授權。

`notes://note-1` 比 `note-1` 好，因為它的命名空間是明確的。檔案伺服器可以用 `file://` URI，但它仍然必須在解析符號連結與相對路徑片段之後，檢查設定好的目錄邊界。

`resources/list` 回傳呼叫者當下可見的資源。用 URI 這類穩定的鍵排序。確定性的順序能避免吵雜的快取未命中、變來變去的快照，以及在每次重新整理間跳動的宿主 UI。

```json
{
  "resultType": "complete",
  "resources": [
    {
      "uri": "notes://note-1",
      "name": "Architecture decision",
      "description": "Why the service uses a stateless boundary",
      "mimeType": "text/markdown"
    }
  ],
  "ttlMs": 300000,
  "cacheScope": "public",
  "_meta": {
    "io.modelcontextprotocol/serverInfo": {
      "name": "notes-server",
      "version": "2.0.0"
    }
  }
}
```

`resources/read` 回傳一個或多個內容項目。未知的 URI 不是一次成功的空讀取。現行的 Resources 規格把無效或未知的資源 URI 歸到 JSON-RPC 的 invalid parameters，錯誤碼 `-32602`。

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": -32602,
    "message": "Unknown or invalid resource URI",
    "data": {
      "uri": "notes://missing"
    }
  }
}
```

這個區分讓客戶端能把「不存在」跟「一份有效的空文件」分開。它也避免了不小心退回去做更大範圍的查找。

### 資源模板

資源模板描述一整族帶參數的 URI。當把每一個具體項目都列出來會太貴、或數量無上限時，就用它。舉例來說，`notes://projects/{project}/decisions/{decision}` 告訴客戶端怎麼組出一個有效的位址，而不必回傳每一個決策。

模板不會削弱驗證。要解析變數、套用授權、強制長度與字元限制，並用帶型別的參數組出儲存查詢。絕不要把任意的 URI 尾段串接進檔案系統路徑或資料庫語句裡。

### 內容不是可信的指令

資源文字裡可能有提示詞注入、機密、誤導性的指令，或格式錯亂的標記。宿主應該保留來源出處，並把資源內容當成資料。伺服器應該限制內容大小、回傳準確的 MIME 型別、遮蔽呼叫者無權存取的欄位，並避免回傳無關的紀錄。

## 提示詞是由使用者控制的模板

MCP 提示詞是為了「由使用者明確挑選」而設計的。宿主可以把它們算繪成斜線指令、選單項目或工作流程按鈕。協定並不要求特定的 UI。

在同一份請求授權底下，`prompts/list` 應該是確定性的。每一個提示詞都需要穩定的名稱、有用的描述，以及參數宣告，好讓宿主在 `prompts/get` 之前先蒐集輸入。

```json
{
  "resultType": "complete",
  "prompts": [
    {
      "name": "review_note",
      "title": "Review a note",
      "description": "Review one note for a named concern",
      "arguments": [
        {
          "name": "uri",
          "description": "The note resource URI",
          "required": true
        }
      ]
    }
  ],
  "ttlMs": 600000,
  "cacheScope": "public"
}
```

`prompts/get` 把參數解析成訊息。它不會取代宿主的系統指令。宿主決定回傳的訊息如何進入模型脈絡，並讓自己受信任的政策維持在更高的優先序。

在伺服器邊界驗證提示詞參數。提示詞裡的 URI 應該通過跟直接資源讀取一樣的授權檢查。不要讓提示詞變成繞過資源存取的側通道。

## 快取提示是正確性的一部分

`ttlMs` 告訴客戶端一個結果可以重用多久。`cacheScope` 描述誰可以共用那個快取值。

| 範圍 | 意義 | 典型用途 |
|---|---|---|
| `public` | 在授權允許時可跨使用者重用 | 公開的提示詞目錄 |
| `private` | 綁在發出請求的使用者或憑證脈絡上 | 使用者自有的筆記內容 |

依資料的變動速率，以及過期資料造成的傷害，來挑 TTL。公開的提示詞目錄也許五分鐘就合適。私有筆記的讀取可以用一分鐘。

MCP 只把 `public` 與 `private` 定義為 `cacheScope` 的值。對於帶有機密、或變動極快的結果，回傳 `cacheScope: "private"` 搭配 `ttlMs: 0`，再在宿主的快取政策裡套用更嚴格的 no-store 規則。`no-store` 本身不是 MCP 的 `cacheScope` 值。

快取提示永遠不能取代授權。快取鍵必須涵蓋每一個會改變可見性的請求維度，包含租戶、使用者、範圍、語系與分頁游標。如果共用快取無法安全地表達那些維度，就用 `private` 搭配零 TTL，以及宿主層級的 no-store 政策。

## 訂閱使用由客戶端開啟的回應串流

現代的訂閱模式取代了先前的 `resources/subscribe` RPC，以及舊的 HTTP GET 事件端點。

客戶端把 `subscriptions/listen` 當成一般的 JSON-RPC 請求送出。在 Streamable HTTP 上，這是一次 POST，它的回應會以 SSE 串流的形式保持開啟。`notifications` 物件是一份允許清單。伺服器不得推送未被請求的通知類型。

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "method": "subscriptions/listen",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
      "io.modelcontextprotocol/clientInfo": {
        "name": "course-client",
        "version": "1.0.0"
      }
    },
    "notifications": {
      "resourcesListChanged": true,
      "promptsListChanged": true,
      "resourceSubscriptions": [
        "notes://note-1"
      ]
    }
  }
}
```

請求 ID 就是訂閱 ID。在任何被請求的事件之前，伺服器會送出 `notifications/subscriptions/acknowledged`。它的過濾條件只包含伺服器接受的那個子集。

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/subscriptions/acknowledged",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/subscriptionId": 17
    },
    "notifications": {
      "resourcesListChanged": true,
      "resourceSubscriptions": [
        "notes://note-1"
      ]
    }
  }
}
```

那條串流上後續的每一個事件，都帶著同樣的中繼資料。

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/resources/updated",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/subscriptionId": 17
    },
    "uri": "notes://note-1"
  }
}
```

通知說的是「資源變了」。客戶端在當前授權的前提下，透過 `resources/read` 再讀一次。它不會假設事件裡就帶著新文件。

多個訂閱可以共用同一條 stdio 通道。訂閱 ID 讓客戶端能把它們解多工。在 HTTP 上，關閉回應串流即取消該訂閱。優雅結束串流的伺服器，會回傳一則與原始請求對應、`resultType: "complete"` 的最終回應。

不要把訂閱串流當成協定工作階段。後續的讀取仍然是一則完整的請求，可以落在任何一個健康的伺服器實例上。

```figure
t3-primitive-sort
```

## 互動實驗

用這張圖把專案追蹤系統的五項能力分類：議題細節、建立議題、衝刺審閱模板、專案政策，以及關閉議題。接著決定哪些清單可以公開快取、哪些讀取必須維持私有，以及哪些資源值得推送更新通知。

每做一次分類，都指出「誰在選」。如果是模型執行動作，用工具。如果是宿主讀取以 URI 定址的內容，用資源。如果是使用者啟動一段備好的訊息工作流程，用提示詞。

## 實作練習

從版本庫根目錄執行模擬器：

```bash
cd phases/13-tools-and-protocols/10-mcp-resources-and-prompts/code
python3 main.py
python3 -m unittest discover tests -v
```

照這個順序檢視逐字紀錄：

1. 確認 `server/discover` 公告了當前修訂版與兩種能力。
2. 確認兩份清單結果都已排序，並使用 `resultType: "complete"`。
3. 確認清單與讀取結果都帶著刻意設定的快取提示。
4. 把讀取的 URI 改成 `notes://missing`，觀察 `-32602`。
5. 確認訂閱確認訊息出現在資源事件之前。
6. 確認事件與優雅關閉都帶著訂閱 ID `5`。

這份 Python 模型不會真的開一條 HTTP 連線。它呈現的是 SDK 必須放到請求範圍回應串流上的那些訊息。正式環境請用官方 SDK 處理框架化與傳輸。

## 交付產物

`outputs/skill-primitive-splitter.md` 是一份可重用的設計審查，用於 MCP 原語的選擇。它現在還會檢查確定性發現、快取範圍、無效 URI 行為，以及現代訂閱過濾條件。

這一課同時交付 `assets/primitive-split.svg`，是原語與訂閱邊界的靜態版本，方便離線研讀。

## 驗證

```bash
cd phases/13-tools-and-protocols/10-mcp-resources-and-prompts/code
python3 main.py
python3 -m unittest discover tests -v
```

預期結果：主程式印出一份 JSON 逐字紀錄，而測試指令回報至少十二項測試通過。

## 與綜合專案的銜接

當你的綜合專案伺服器要在動作之外，還暴露可定址的知識時，就採用這份契約。請包含一份確定性的目錄快照、一次已授權的資源讀取、一次提示詞解析、一個無效 URI 案例，以及一份訂閱逐字紀錄。

你的證據應該顯示：沒有任何清單依賴連線歷史，而且訂閱事件本身絕不授予對底層資源的存取權。

## 練習

1. 加一個 `notes://projects/{project}/notes/{id}` 資源模板，並驗證兩個變數。
2. 為 `resources/list` 加上分頁，同時保住確定性的排序。
3. 把某個資源改成 `cacheScope: "private"` 搭配 `ttlMs: 0`，加上宿主層級的 no-store 政策，並說明是什麼威脅同時證成了這兩道控制。
4. 加一個提示詞清單變更的訂閱，並證明當過濾條件裡沒有 `promptsListChanged` 時不會送出任何事件。
5. 同時建立兩個訂閱，並證明每個事件都帶著正確的請求 ID。
6. 在讀取處理器裡加上授權主體，並證明快取條目無法跨主體。

## 關鍵術語

- **資源（Resource）：** MCP 伺服器暴露的、以 URI 定址的內容。
- **提示詞（Prompt）：** MCP 伺服器暴露的、由使用者控制的訊息模板。
- **確定性清單：** 在相同請求輸入下，成員與排序都穩定的發現結果。
- **`ttlMs`：** 以毫秒為單位的快取新鮮度時長。
- **`cacheScope`：** 一則快取結果的共用邊界。
- **`subscriptions/listen`：** 長時間存活的請求，其回應串流推送經明確過濾的通知。
- **訂閱 ID：** 原始 listen 請求的 ID，會在通知中繼資料裡重複出現。
- **無效參數：** JSON-RPC 錯誤 `-32602`，用於無效或未知的資源 URI。
- **不支援的協定版本：** JSON-RPC 錯誤 `-32022`，內含 `supported` 與 `requested` 修訂版。
- **`server/discover`：** 必備的伺服器方法，回傳受支援的修訂版、能力、身分與選用的快取提示。

## 延伸閱讀

- [MCP 2026-07-28 Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- [MCP 2026-07-28 Prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
- [MCP 2026-07-28 Subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions)
- [MCP 2026-07-28 Caching](https://modelcontextprotocol.io/specification/2026-07-28/basic/utilities/caching)
