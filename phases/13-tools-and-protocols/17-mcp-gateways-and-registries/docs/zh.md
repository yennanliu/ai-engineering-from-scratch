# 無狀態 MCP 閘道與登錄檔准入

> 閘道應該讓每一條路由都明確。2026-07-28 協定在沒有傳輸工作階段的情況下，給了它方法、名稱、版本、能力、身分、快取與追蹤這些邊界。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 13 · 15（安全）、階段 13 · 16（授權）
**時間：** 約 75 分鐘

## 學習目標

- 把數台 MCP 伺服器聚合在單一個 2026-07-28 端點後面，且不使用工作階段親和性。
- 在套用政策或轉發之前，先驗證每請求的中繼資料與路由標頭。
- 用穩定的命名空間、確定性排序、描述固定、RBAC 與私有快取來合併工具。
- 把登錄檔紀錄當成發現用的證據，它仍然需要准入政策。
- 正確路由請求範圍的 SSE、`subscriptions/listen`、MRTR 重試，以及 Tasks 擴充的呼叫。
- 讓舊版的握手與工作階段支援，跟現代路徑隔離開來。

## 問題所在

把一個客戶端直接接上一台伺服器很簡單。規模大一點的部署，需要對更難的問題有一致的答案：

- 哪些伺服器被允許？
- 哪個主體可以看到並呼叫哪個工具？
- 兩個後端暴露同一個名稱時會怎樣？
- 描述變更怎麼被審查？
- 速率限制與稽核事件套在哪裡？
- 任何一個實例都能處理下一則請求嗎？

閘道坐在客戶端與後端 MCP 伺服器之間。它對外呈現單一個 MCP 端點、套用橫切政策，並轉發被核准的請求。

較舊的閘道設計，常常把一個客戶端工作階段多工成好幾個後端工作階段，並改寫 `Mcp-Session-Id`。那是舊版的相容設計。2026-07-28 核心沒有協定工作階段。

## 核心概念

### 現代閘道路徑

對每一則請求：

1. 從傳輸授權認證出主體。
2. 驗證 `MCP-Protocol-Version`、`Mcp-Method`、`Mcp-Name` 與 `params._meta`。
3. 對主體、資源、方法、工具與參數做授權。
4. 套用描述、登錄檔、速率與資料政策。
5. 為選定的後端建立一則全新、自成一體的請求。
6. 驗證後端結果，並回傳閘道結果。
7. 記下一筆稽核事件，過程中不記錄機密。

沒有任何一步需要隱藏的協定工作階段。應用狀態仍然可以存在於資料庫、明確把手、Tasks，或有完整性保護的 MRTR 狀態裡。

### 執行期政策才是閘道的主要決策

准入決定的是哪一個後端版本可以進到閘道裡。它不授權一次即時呼叫。對每一則請求，閘道都要從已認證的主體、簽發者與資源、租戶、比對到的方法與名稱、正規化後的參數、被准入的描述固定值、當前後端健康狀態、能力交集、資料分級、速率狀態，以及任何綁定動作的核准，重新計算政策。

這個順序很重要。登錄檔紀錄可能還是 active，而使用者的角色卻已被撤銷。描述可能還被固定住，而某個目的地參數卻跨越了租戶邊界。後端可能還被核准著，而事故政策卻隔離了所有會改變狀態的呼叫。因此執行期政策才是主要的允許或拒絕決策，而登錄檔與描述證據只是輸入。

不要把「允許」的決策快取在連線或已被移除的工作階段識別碼底下。若政策不可用，就依操作類別遵循一份明訂的失敗政策。安全的預設是：對狀態變更與敏感讀取一律 fail closed；至於明確核准過的公開讀取路徑，只有在它們的風險模型允許時，才可以使用短暫的最後已知政策。記下是哪個政策版本與哪條失敗路徑做出了決定，然後在回傳之前驗證後端結果。

### 單一個 POST 端點

現代 Streamable HTTP 透過 POST 送出每一則 JSON-RPC 訊息：

```text
POST /mcp
Authorization: Bearer <gateway-token>
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: notes.search
Accept: application/json, text/event-stream
```

閘道可以對那次 POST 回傳 JSON，或請求範圍的 SSE。對現代請求而言，GET 與 DELETE 回傳 405。`Mcp-Session-Id` 與 `Last-Event-ID` 不會產生權限、親和性或重播行為。

標頭與主體的值必須一致。在查找後端之前就用 `-32020` 拒絕不一致。這讓負載平衡器、閘道與限流器不必解析完整主體就能路由，同時保住端到端的完整性。

用一個確切的順序驗證：JSON-RPC 與中繼資料型別、標頭與主體是否相等，然後才是那個已取得一致之版本是否受支援。不一致回傳 HTTP 400 與 `-32020`。如果標頭與主體對一個不受支援的版本取得一致，回傳 HTTP 400 與 `-32022`，`data` 精確為 `{"supported":["2026-07-28"],"requested":"<actual>"}`。未知的方法回傳 HTTP 404 與 `-32601`。

`ProtocolError` 帶有選用的 `data`，閘道會把它序列化進 JSON-RPC 錯誤物件。通知沒有 `id`，所以它永遠不會收到 JSON-RPC 的成功或錯誤。被接受的 HTTP 通知回傳 202 與空主體。

### 每一層都要實作發現

閘道為客戶端實作 `server/discover`。它也會去發現每一個後端，好知道協定版本、能力與擴充。

閘道結果範例：

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "tools": {"listChanged": true}
  },
  "ttlMs": 30000,
  "cacheScope": "private",
  "_meta": {
    "io.modelcontextprotocol/serverInfo": {
      "name": "enterprise-gateway",
      "version": "2.0.0"
    }
  }
}
```

只公告閘道能端到端兌現的那個能力交集。後端有某個功能，不代表把它暴露出去就自動安全。閘道有某個功能但沒有後端路徑，公告它也沒有用。

`serverInfo` 是自行宣告的顯示與診斷資料。不要把它當成登錄檔或發布者的證明。

### 每請求的客戶端能力

每一則被轉發的請求，都需要一個當前的 `_meta` 信封：

```json
{
  "io.modelcontextprotocol/protocolVersion": "2026-07-28",
  "io.modelcontextprotocol/clientCapabilities": {},
  "io.modelcontextprotocol/clientInfo": {
    "name": "enterprise-gateway",
    "version": "1.0.0"
  }
}
```

不要盲目把外層客戶端的能力複製給後端。對後端來說，閘道才是客戶端。只公告閘道會正確調解的那些功能。

### 確定性的命名空間

把後端工具合併在穩定的公開名稱底下：

```text
notes.search
notes.create
issues.list
issues.open
```

保留一份從公開名稱到後端與原始工具名稱的映射。撞名時絕不要選第一個或最後一個。公開名稱是核准與稽核契約的一部分，所以改它就是一次遷移。

`tools/list` 必須具確定性。當可見性因主體而異時，回傳 `cacheScope: private`。有界限的 `ttlMs` 能降低後端的發現負載，同時不讓使用者專屬的清單跨授權脈絡外洩。

每一個被暴露的工具描述，都包含穩定的名稱、描述，以及根節點為物件的 `inputSchema`。加命名空間不能拿掉必填的描述欄位。完整的清單結果同時包含 `resultType`、伺服器身分中繼資料與快取提示。

### 固定已核准的描述

在准入時，把完整的描述正規化，並把它的摘要值存在那個限定過的公開名稱底下。在列清單與呼叫時，拿即時的描述跟已核准的摘要值比對。

若它變了：

- 把它從 `tools/list` 裡拿掉。
- 拒絕直接呼叫。
- 發出一筆稽核事件。
- 在更新固定值之前，要求政策或人工重新核准。

閘道是一個好用的集中執行點，但它不會把一份初次見到的描述變成安全的。初次審查仍然必要。

### 登錄檔幫你發現，不幫你決定

登錄檔的 `server.json` 提供發布中繼資料。一筆有套件支撐的紀錄可能長這樣：

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "com.example/notes",
  "description": "Example notes MCP server.",
  "version": "1.0.0",
  "packages": [
    {
      "registryType": "npm",
      "identifier": "@example/notes-mcp",
      "version": "1.0.0",
      "transport": {"type": "stdio"}
    }
  ]
}
```

發布中繼資料不承載閘道的安全決策。把已驗證的發布者與來源證據，放在獨立的准入狀態裡：

```json
{
  "registryName": "com.example/notes",
  "registryVersion": "1.0.0",
  "publisher": {"namespace": "com.example", "status": "verified"},
  "provenance": {
    "source": "registry.modelcontextprotocol.io",
    "recordId": "com.example/notes@1.0.0"
  },
  "admission": {"status": "approved", "reviewedBy": "gateway-policy"}
}
```

閘道會檢查 `server.json` 的形狀，並把它跟那份外部狀態接起來。閘道仍然需要一份准入政策。

對每一個被准入的後端，記下：

- 確切的登錄檔與紀錄識別碼。
- 已驗證的發布者命名空間或網域證據。
- 被允許的傳輸與端點。
- 固定的版本，或已核准的升級政策。
- 產物或描述的摘要值。
- 授權簽發者與資源。
- 審查者、核准時間與到期時間。

不要因為某台伺服器的顯示名稱很像某個眼熟的產品就接受它。也不要把「登錄檔上有」當成一次運維安全審查。私有伺服器就算從不出現在公開登錄檔裡，也可以透過同一套證據結構被准入。

這一課實作的是閘道的接縫：在後端變成可路由之前，把發布證據跟本地准入接起來。[單元 30：MCP 登錄檔供應鏈、准入、漂移與回滾](../../30-mcp-registry-supply-chain-and-drift/docs/en.md) 會建構完整的控制平面，涵蓋精確的命名空間證明、產物來源、不可變固定、即時描述漂移、登錄檔狀態調和、可察覺竄改的准入帳本，以及有證據支撐的回滾。讓那份供應鏈狀態，跟上面那個每請求的執行期決策保持分離。

### 憑證調解

閘道認證它的呼叫者，並另外向後端認證自己。後端憑證絕不會給客戶端。

把這些綁定寫清楚：

```text
outer principal -> gateway role and policy
backend issuer + resource -> backend registration and token
```

絕不要把外層的閘道權杖傳給後端。也絕不要把後端權杖拿去另一個簽發者或資源上重用。如果某個工具是代表終端使用者行動，就用設計過的交換或 claims 模型保留那份委派關係，而不是用一份共用的服務憑證去冒充使用者。

### 不靠工作階段的速率限制

以已認證的主體、簽發者、資源、公開工具、成本類別與時間窗為鍵來設限。工作階段 id 根本不存在，而且就算存在也很容易被輪替掉。

在消耗昂貴工作之前，先做便宜的驗證。決定被拒絕的呼叫要不要計入濫用上限、業務配額，或兩者皆計。

### 稽核整條決策鏈

記下足以重建一次呼叫的資訊：

- 請求與追蹤識別碼。
- 已認證的主體與簽發者。
- 公開工具與後端路由。
- 描述固定值的版本。
- 政策決策與原因。
- 延遲與結果類別。
- 適用時的 MRTR 回合或任務識別碼。

遮蔽 bearer token、授權碼、更新權杖、原始機密，以及不必要的敏感參數。

### 請求範圍的 SSE

當工作是在那一則請求期間串流產出時，一次普通的 POST 可以回傳請求範圍的 SSE。關閉回應串流即取消那則在途的現代 HTTP 請求。

不要另外建一條 GET 串流，也不要承諾 Last-Event-ID 重播。那些是較舊的傳輸假設。

### 長時間存活的變更通知

對於清單與資源的變更通知，現行客戶端透過 POST 送出 `subscriptions/listen`，並收到一則 SSE 回應。通知過濾條件使用確切的扁平欄位 `toolsListChanged`、`promptsListChanged`、`resourcesListChanged` 與 `resourceSubscriptions`：

```json
{
  "jsonrpc": "2.0",
  "id": "listen-tools",
  "method": "subscriptions/listen",
  "params": {
    "notifications": {
      "toolsListChanged": true
    },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

第一則事件確認被支援的子集。它的訂閱識別碼，就是開啟那條串流的那則請求的 JSON-RPC id：

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/subscriptions/acknowledged",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/subscriptionId": "listen-tools"
    },
    "notifications": {
      "toolsListChanged": true
    }
  }
}
```

接著閘道只轉發已確認的那些變更類型。那條串流上的每一則通知，都在 `params._meta` 裡帶著同一個 `io.modelcontextprotocol/subscriptionId`。沒有自動重播，也沒有自動重新 listen。重連時，客戶端重新開啟訂閱，並重新整理它所依賴的那些清單。由伺服器發起的優雅關閉，會回傳一則帶著同一個訂閱 id 的最終完整結果。

現代路徑取代了 `resources/subscribe`、`resources/unsubscribe` 與未經請求的獨立 GET 串流。那些只保留在一條有版本關卡的舊路徑裡。

### 穿過閘道的 MRTR

當後端回傳 `resultType: input_required` 時，只有在外層客戶端支援所需的輸入請求時，閘道才能轉發那個結果。除非閘道刻意終止並重新發起這次互動，否則要逐位元組保留 `requestState`。

客戶端用一個新的 JSON-RPC id 與 `inputResponses` 重試原本的公開工具。閘道對那次重試重新授權、檢查同一條公開路由，然後轉發一則全新的後端請求。它不得假設先前某一回合已經授予了無限的核准。

### Tasks 擴充的路由

Tasks 是一個由 `io.modelcontextprotocol/tasks` 標識的官方擴充。它不是核心工作階段的替代品。

客戶端在每請求的客戶端能力裡宣告這個擴充，而閘道只有在能端到端保住整個生命週期時，才在發現裡公告它。對一次受支援的 `tools/call`，是否回傳一般結果或 `resultType: task`，完全由後端決定。任務結果會直接在結果裡帶著 `taskId`、`status`、時間戳記、`ttlMs`，以及選用的 `pollIntervalMs`。在那個結果送出之前，任務必須已經能被持久讀取。

閘道會為那個不透明的任務識別碼，記下已認證的主體與後端路由。後續的 `tasks/get`、`tasks/update` 與 `tasks/cancel` 呼叫，都用 `params.taskId` 當作 `Mcp-Name`，這給了中介者一把路由鍵。`tasks/get` 回傳 `resultType: complete` 與當前任務狀態，並在終局狀態時把最終結果或協定錯誤內嵌進來。`tasks/update` 為仍待處理的任務輸入送出帶鍵的 `inputResponses`，並回傳一則空的完整確認。`tasks/cancel` 是一次協同式的意圖表達，回傳空的完整確認，不保證工作會停下。

不要實作新的 `tasks/list` 或 `tasks/result` 方法。它們屬於較舊的實驗性模型。需要輸入的任務，會透過 `tasks/get` 暴露完整的內嵌請求；客戶端用 `tasks/update` 回答它們，而不是重試原本的工具呼叫。客戶端仍然照建議的間隔輪詢；任務建立仍然由伺服器主導。

持久的任務路由狀態，是以任務把手為鍵的應用資料，不是協定工作階段。

### 相容性邊界

如果閘道必須服務較舊的客戶端或後端：

- 明確偵測時代。
- 把初始化、傳輸工作階段、GET 串流、資源訂閱與舊的任務詞彙，都留在一個舊版轉接層裡。
- 絕不要讓舊版工作階段 id 洩漏進現代的路由或授權。
- 優先採用有界限的發現探測與明確的退路政策，而不是無聲降級。

```figure
t3-gateway-funnel
```

## 動手實作

`code/main.py` 實作了一個行程內的協定閘道與兩台後端伺服器。每個後端都收到一則全新的、當前協定的請求。閘道提供發現、依使用者過濾的確定性 `tools/list`、帶命名空間的路由、登錄檔 `server.json` 加上外部准入狀態、描述固定、RBAC、以主體為鍵的速率限制、稽核決策，以及一段模擬的 `subscriptions/listen` SSE 確認。

這個模型收到的是已解析的請求主體、路由標頭，以及一個已認證的 bearer 身分。它不是完整的 HTTP 轉接層，也不解析 `Content-Type` 或完整的 `Accept` 契約。把它接到單元 09 的 Streamable HTTP 轉接層，那裡會要求 `Content-Type: application/json`，以及同時包含 `application/json` 與 `text/event-stream` 的 `Accept` 值。

執行它：

```bash
cd phases/13-tools-and-protocols/17-mcp-gateways-and-registries
python3 code/main.py
python3 -m unittest discover code/tests -v
```

這份示範會印出外層請求 id 與全新的後端請求 id，讓那一跳的無狀態性看得見。

## 框架應用

把行程內的後端物件換成真正的當前協定客戶端。保留同樣的接縫：

- 連線之前先有准入紀錄。
- 暴露能力之前先做後端發現。
- 授權之前先有限定過的公開名稱。
- 列清單或呼叫之前先做描述固定。
- 轉發之前先組出全新的每請求中繼資料。
- 回傳之前先驗證結果。

## 產出交付

這一課交付 `outputs/skill-gateway-bootstrap.md`。它會產出一份現代閘道設計，涵蓋入口、發現、准入、命名空間、授權、快取、串流、訂閱、MRTR、Tasks、可觀測性與舊版隔離。

## 練習

1. 把追蹤脈絡加進外層與轉發後的請求中繼資料，並在稽核事件裡記下那個對應關係。
2. 加一個支援 Tasks 的後端，並用 `Mcp-Name` 裡的任務 id 路由 `tasks/get`。
3. 改動一個後端描述，並證明發現與直接呼叫都被擋下。
4. 加上一項因主體而異的伺服器能力，並說明為什麼發現必須維持私有快取。
5. 寫一個舊版轉接層介面，過程中不對現代的 `Gateway` 類別加上任何舊版狀態。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| MCP 閘道 | 坐在客戶端與後端 MCP 伺服器之間的政策與路由伺服器 |
| 准入紀錄 | 允許某個後端進入閘道的證據與政策決策 |
| 限定工具名稱 | 像 `notes.search` 這樣的穩定公開路由 |
| 描述固定 | 在發現與分派時檢查的已核准摘要值 |
| 私有快取範圍 | 限制在單一授權脈絡內的快取結果 |
| 請求範圍 SSE | 附在單一 POST 請求上的串流回應 |
| `subscriptions/listen` | 由客戶端開啟、用於選定之長時間存活變更通知的 SSE 串流 |
| 任務路由 | 從不透明任務 id 到其後端的應用層映射 |
| 舊版轉接層 | 針對舊握手與工作階段行為、明確且有版本關卡的邊界 |

## 延伸閱讀

- [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Server discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [Official Registry server.json requirements](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/official-registry-requirements.md)
- [MCP Tasks extension](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks)
