# 無狀態協定上的 MCP Apps

> 互動式結果仍然是一次 MCP 工具與資源的交換。2026-07-28 核心讓那次交換自成一體，而 Apps 擴充則加上了受沙箱限制的瀏覽器介面。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 10（資源）
**時間：** 約 75 分鐘

## 學習目標

- 透過 `server/discover` 與每請求的擴充能力公告 MCP Apps。
- 在工具被呼叫之前，就先在工具上宣告一個 `ui://` 資源。
- 在 2026-07-28 的無狀態線路上回傳完整的工具與資源結果。
- 把 Apps 的 `ui/initialize` 橋接訊息，跟已移除的 MCP 核心握手區分開來。
- 套用 origin 驗證、沙箱、CSP 與最小權限。

## 問題所在

文字結果可以「描述」一條時間軸。它沒辦法給使用者一條可以過濾、檢視、據以行動的時間軸。

MCP Apps 用一個選用的擴充解決呈現問題。工具定義指向一個 `ui://` 資源。宿主可以在工具執行之前先抓取並審查那個資源，把它算繪在受沙箱限制的 iframe 裡，並透過一條 JSON-RPC 橋接調解所有 App 動作。

核心協定在 2026-07-28 改變了。不要把 App 包進舊的連線生命週期裡：

- 沒有核心的 `initialize` 請求，也沒有 `notifications/initialized` 通知。
- 沒有 `Mcp-Session-Id` 標頭。
- 每一則請求都在 `params._meta` 裡帶著協定版本與客戶端能力。
- 伺服器實作 `server/discover`，讓客戶端能檢視版本、核心能力與擴充。
- 每一個成功的結果都有一個 `resultType` 判別欄位。
- Streamable HTTP 每則請求走一次 POST。現代的 GET 與 DELETE 入口回傳 405。

Apps 橋接仍然有一個叫 `ui/initialize` 的方法。它屬於 iframe 的 postMessage 方言。它不會重建一個核心 MCP 工作階段。

## 核心概念

### 兩套協定，一個功能

把層級講清楚：

1. MCP 核心承載 `server/discover`、`tools/list`、`tools/call`、`resources/list` 與 `resources/read`。
2. MCP Apps 擴充宣告 UI，並定義 iframe 對宿主的橋接。
3. 瀏覽器沙箱規則限制 UI 能碰到什麼。

擴充識別碼是 `io.modelcontextprotocol/ui`。兩端都要選入。客戶端在每一則請求的能力物件裡送出擴充支援：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "server/discover",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
          "io.modelcontextprotocol/ui": {}
        }
      },
      "io.modelcontextprotocol/clientInfo": {
        "name": "timeline-host",
        "version": "1.0.0"
      }
    }
  }
}
```

`clientInfo` 建議為了診斷而附上。它是自行宣告的資料，不是授權身分。

### 算繪之前先發現

伺服器的發現結果會公告這個擴充：

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "tools": {},
    "resources": {},
    "extensions": {
      "io.modelcontextprotocol/ui": {}
    }
  },
  "ttlMs": 300000,
  "cacheScope": "public",
  "_meta": {
    "io.modelcontextprotocol/serverInfo": {
      "name": "timeline-app-server",
      "version": "2.0.0"
    }
  }
}
```

伺服器必須支援發現。客戶端不被強制在每個動作之前都呼叫發現，因為每個動作都自帶能力。

### 在工具定義上宣告 UI

現代的 Apps 契約在 `tools/list` 裡把 UI 綁到工具上：

```json
{
  "name": "notes_timeline",
  "description": "Render a timeline of notes.",
  "inputSchema": {
    "type": "object",
    "properties": {}
  },
  "_meta": {
    "ui": {
      "resourceUri": "ui://notes/timeline.html"
    }
  }
}
```

這是刻意設計成「呼叫前」的中繼資料。宿主可以在某個結果要求顯示之前，就先預載、快取並做安全審查。相容程式碼可能接受較舊的扁平中繼資料鍵，但新伺服器應該發出巢狀的 `_meta.ui.resourceUri` 形式。

`tools/list` 在現行核心裡是可快取的。要帶上確定性排序、`ttlMs` 與 `cacheScope`。當可見的工具會因使用者或權杖而異時，用 `private`。

### 回傳資料，然後讓宿主綁定視圖

工具呼叫回傳一般內容加上結構化資料：

```json
{
  "resultType": "complete",
  "content": [
    {"type": "text", "text": "Timeline ready."}
  ],
  "structuredContent": {
    "notes": [
      {"id": "note-1", "title": "Discover", "created": "2026-07-28"}
    ]
  },
  "isError": false
}
```

宿主已經知道哪個視圖屬於哪個工具。不要只為了重複那個 URI 就發明新的內容區塊。

### 把 app 當成資源來提供

伺服器在發現裡公告了 `resources`，所以它也要實作必備的 `resources/list` 操作。它那筆確定性的清單項目包含標準 URI、穩定名稱、描述與 MIME 型別。清單結果會包含 `resultType`、伺服器身分中繼資料、`ttlMs` 與 `cacheScope`，就跟確定性的工具清單一樣。

宿主送出 `resources/read`。在 Streamable HTTP 上，請求長這樣：

```text
POST /mcp
MCP-Protocol-Version: 2026-07-28
Mcp-Method: resources/read
Mcp-Name: ui://notes/timeline.html
```

標頭值與 JSON-RPC 主體必須一致。不一致就是協定錯誤 `-32020`。

結果包含 HTML 資源與快取提示：

```json
{
  "resultType": "complete",
  "contents": [
    {
      "uri": "ui://notes/timeline.html",
      "mimeType": "text/html;profile=mcp-app",
      "text": "<!doctype html>...",
      "_meta": {
        "ui": {
          "csp": {
            "connectDomains": [],
            "resourceDomains": [],
            "frameDomains": [],
            "baseUriDomains": []
          },
          "permissions": {}
        }
      }
    }
  ],
  "ttlMs": 60000,
  "cacheScope": "public"
}
```

### 把 UI 資源當成可執行內容來快取

App 資源跟一般散文不能互換。它的快取條目可以執行橋接程式碼、算繪工具資料，並請求由宿主調解的動作。快取鍵要包含標準 `ui://` URI、被准入的伺服器身分與版本、資源內容摘要值，以及當 `cacheScope` 為 private 時的授權脈絡。絕不要跨主體重用一份 private 的 App 資源，因為即使 URI 完全相同，HTML 或它的政策中繼資料仍可能不同。

當它的 `ttlMs` 過期、工具的 `_meta.ui.resourceUri` 綁定改變、伺服器版本或被准入的描述固定值改變，或一個已確認的資源變更訂閱點名了那個 URI 時，就讓該條目失效。重新抓取，並在重新掛載之前重新套用 CSP 與權限審查。過期的 iframe 不得只因為新版資源還沒載入，就繼續保有更寬的權限。

### 先排除線路上的歧義，再談功能政策

驗證有一個刻意安排的順序。先驗證 JSON-RPC 的形狀，並要求協定中繼資料是字串、客戶端能力是物件映射。接著把路由標頭拿去跟主體比對。之後才決定那個已取得一致的協定版本是否受支援。這個順序能防止代理與伺服器解讀成不同的請求。

| 條件 | HTTP | JSON-RPC 錯誤 |
|-----------|------|----------------|
| 標頭與主體的版本、方法或名稱不一致 | 400 | `-32020` |
| 標頭與主體對一個不受支援的版本取得一致 | 400 | `-32022`，`data` 精確為 `{"supported":["2026-07-28"],"requested":"<actual>"}` |
| `resources/read` 缺少 Apps 擴充能力 | 400 | `-32021`，附上 `data.requiredCapabilities.extensions.io.modelcontextprotocol/ui` |
| 方法未知 | 404 | `-32601` |

JSON-RPC 通知沒有 `id`，所以伺服器絕不會為它發出 JSON-RPC 回應。被接受的 HTTP 通知回傳 202 與空主體。錯誤可以改變 HTTP 狀態碼，但仍然不能為一則通知造出 JSON-RPC 錯誤主體。

### 沙箱是一道邊界，不是一份信任判決

宿主控制那個 iframe。App 無法直接讀取宿主的 cookie、local storage 或頁面 DOM。所有特權工作都必須跨過橋接。

採用這些預設：

- 把所有 CSP 網域清單留空，然後只加上 App 真正需要的來源。fetch、XHR 與 WebSocket 用 `connectDomains`；腳本、樣式、圖片與字型用 `resourceDomains`。
- 可行時就把程式碼與資料打包在一起。
- 除非有看得見的功能需要，否則不要請求相機、麥克風或位置權限。
- 把 `postMessage` 固定在確切的對端 origin，並拒絕來自其他任何 origin 的事件。
- 把工具參數、工具結果、資源文字與橋接訊息，全部視為不可信的輸入。
- 讓使用者同意留在宿主端。iframe 不能核准自己的重大動作。

不要把教學文裡固定的 `sandbox` 屬性直接複製到每一個宿主上。宿主必須依 App 的 origin 模型與自身的隔離設計來選旗標。

被允許的網域仍然是一條外洩路徑。`connectDomains: ["https://api.example.com"]` 代表任何在 App 裡執行的腳本，都能把被允許的資料送到那裡。精確的 origin 比對能防止目的地混淆，但它不會判斷那個負載是否恰當。預設讓 connect 存取保持空白、避免把 bearer token 放進 iframe、可行時把範圍窄的操作透過宿主代理、限制回應與請求大小，並稽核每一次對外請求是由哪一個使用者動作引起的。把 `resourceDomains` 跟 `connectDomains` 分開看待；載入字型或腳本的權限，不該等同於任意上傳資料的權限。

### Apps 橋接有它自己的生命週期

Apps 橋接是一套走 `postMessage` 的 JSON-RPC 方言。它可以交換 `ui/initialize` 與 `ui/*` 通知，也可以代理像 `tools/call` 這種看起來像核心的方法。

View 送出帶有 `appInfo` 與 `appCapabilities` 物件的 `ui/initialize`。宿主回傳它的能力與宿主脈絡。只有在那則回應之後，View 才送出 `ui/notifications/initialized`。宿主必須等到這則 Apps 通知，才能開始送訊息給 View。

那次本地握手，建立的是一個 iframe 與一個宿主 frame 之間的橋接。它不協商 MCP 協定版本、不建立伺服器狀態，也不鑄造傳輸工作階段。注意那個確切的前綴：核心的 `notifications/initialized` 被移除了，而 Apps 的 `ui/notifications/initialized` 還在。由橋接的工具呼叫所產生的核心請求，是一則全新、自成一體的請求，帶著新的 JSON-RPC id 與完整的請求中繼資料。

### 宿主脈絡、動作與撤銷

橋接初始化之後，宿主仍然是權威。View 只能透過宿主公告過的某項能力，才能請求工具動作、導覽、剪貼簿使用或其他特權效果。宿主會驗證那則帶型別的請求、當前使用者、目標與參數，套用核准政策，並且可以拒絕它。按鈕點擊與有效的橋接訊息表達的是意圖；兩者都不授予權限。

把主題、尺寸與無障礙當成會變動的宿主脈絡，而不是一次性的算繪輸入：

- 套用宿主提供的色彩與字體排印 token，並在主題或對比偏好改變時做出反應。
- 讓 View 回報它想要的尺寸，但由宿主設上限並實際套用 iframe 大小，好讓內容無法逃出版面配置或製造欺騙性的覆蓋層。
- 在 iframe 內部保留鍵盤順序、可見焦點、無障礙名稱、螢幕閱讀器狀態、足夠的對比、縮放與減少動態效果的行為。
- 在調整尺寸與重新算繪之後，重新測試宿主控制項與 View 控制項之間的焦點轉移。

App 開著的時候，能力仍可能被撤銷，因為使用者換了帳號、政策改了、某台伺服器被隔離，或宿主收窄了同意範圍。要在動作發生的當下檢查能力與授權，不能只在 `ui/initialize` 時檢查。撤銷發生時，拒絕待處理的特權呼叫、停止不再符合政策的網路活動、清掉已算繪的敏感狀態，並在 UI 資源本身不再被准入時重新掛載或退回文字。View 必須把拒絕當成正常結果來處理，而不是一直重試到宿主讓步為止。

### 退路是契約的一部分

支援 Apps 的伺服器，仍然可以服務那些沒有公告 UI 擴充的宿主：

- 在 `tools/list` 裡回傳同一個工具，但不帶 `_meta.ui`。
- 為 `tools/call` 保留一份有用的文字結果。
- 對 UI 的 `resources/read` 以「缺少能力」錯誤拒絕。
- 判斷工具是否完成時，絕不要假設 iframe 存在。

```figure
t3-ui-sandbox
```

## 動手實作

`code/main.py` 不用 SDK，就建了一個小小的行程內協定模型。它驗證當前的請求信封與 Streamable HTTP 路由值、透過 `server/discover` 公告 Apps、列出工具與資源、執行工具，並提供一份自成一體的 HTML 資源。

這個模型收到的是已經解析好的主體與路由標頭。它不是一個完整的 HTTP 轉接層，也不解析 `Content-Type` 或 `Accept`。完整的 Streamable HTTP 轉接層請看單元 09，那裡會要求 `Content-Type: application/json`，以及同時包含 `application/json` 與 `text/event-stream` 的 `Accept` 值。

執行它：

```bash
cd phases/13-tools-and-protocols/14-mcp-apps
python3 code/main.py
python3 -m unittest discover code/tests -v
```

在輸出裡檢視四件事：

1. 每一次呼叫都是獨立的。
2. 每一則請求都有 `_meta` 能力。
3. 在任何資源讀取之前，`resources/list` 就回傳了一份穩定的描述。
4. 每一個結果都有 `resultType` 與伺服器身分中繼資料。
5. 沒有任何核心工作階段識別碼出現。

## 框架應用

先從 `server/discover` 開始。確認 `io.modelcontextprotocol/ui` 出現在伺服器的擴充映射裡。接著呼叫 `tools/list` 兩次，一次帶 Apps 能力、一次不帶。第一次的回應會宣告那個資源。第二次仍然是一個可用的純文字工具。

讀取 `ui://notes/timeline.html`。在 HTML 裡搜尋 `hostOrigin` 與 `event.origin` 那道防護。那兩行是「橋接沒有用萬用字元目標」最起碼、看得見的證據。

## 產出交付

這一課交付 `outputs/skill-mcp-apps-spec.md`。在寫框架程式碼之前，用它來審查 App 契約。它會逼作者交代當前的核心信封、擴充協商、退路、UI 資源、快取政策、CSP、權限、橋接方法，以及同意邊界。

## 練習

1. 把客戶端能力改成空的擴充映射。確認 `tools/list` 保留了那個工具，但移除了 UI 綁定。
2. 送出 `Mcp-Name: ui://notes/other.html`，而主體讀的是 timeline。確認錯誤是 `-32020`。
3. 把資源改成 `cacheScope: private`。描述是什麼使用者專屬的條件證成了它。
4. 把腳本搬到 `https://static.example.com/app.js`。把那個 origin 加進 `resourceDomains`，並說明新出現的供應鏈風險。
5. 加一個 `notes_open` 工具，並把按鈕點擊路由到宿主。讓使用者核准留在宿主端。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| MCP Apps | 選用擴充，用於由 MCP 宿主算繪的互動式 HTML |
| `io.modelcontextprotocol/ui` | 兩端都會公告的擴充識別碼 |
| `ui://` | App UI 模板的資源 scheme |
| `text/html;profile=mcp-app` | MCP App HTML 的 MIME 型別 |
| `server/discover` | 現行的協定與能力發現 RPC |
| `resources/list` | 當伺服器公告資源時必備的資源列出方法 |
| `resultType` | 現代成功結果上的必填判別欄位 |
| `ui/initialize` | Apps 橋接的第一則請求，與已移除的核心初始化無關 |
| `ui/notifications/initialized` | 宿主回應之後，Apps View 送出的就緒通知 |
| CSP | 瀏覽器政策，限制腳本、樣式、圖片與網路來源 |
| 文字退路 | 為不支援 Apps 的宿主保留的工具行為 |

## 延伸閱讀

- [MCP 2026-07-28 base protocol](https://modelcontextprotocol.io/specification/2026-07-28/basic)
- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)
- [MCP Apps build guide](https://modelcontextprotocol.io/extensions/apps/build)
- [Official extension support matrix](https://modelcontextprotocol.io/extensions/client-matrix)
