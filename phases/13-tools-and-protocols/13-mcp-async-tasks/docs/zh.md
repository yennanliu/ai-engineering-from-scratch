# MCP Tasks 擴充：無狀態核心上的持久工作

> 無狀態的 MCP 不代表每個操作都得在一則請求裡做完。官方的 Tasks 擴充給長時間執行的工作一個明確的持久把手。伺服器可以從 `tools/call` 回傳那個把手，任何實例都能回答 `tasks/get`，而客戶端的輸入透過 `tasks/update` 送達，過程中不需要復活協定工作階段。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 · 09（傳輸）、階段 13 · 11（無狀態 MRTR）、階段 13 · 12（elicitation）
**時間：** 約 90 分鐘

## 學習目標

- 分辨無狀態的協定傳輸，與持久的應用任務狀態。
- 在每請求的能力宣告與 `server/discover` 裡協商 `io.modelcontextprotocol/tasks` 擴充。
- 只有在持久化建立完成之後，才回傳由伺服器主導的 `CreateTaskResult`（`resultType: "task"`）。
- 用 `tasks/get` 輪詢、用 `tasks/update` 提供任務輸入，並用 `tasks/cancel` 請求協同式取消。
- 移除較舊的 `tasks/status`、`tasks/result` 與 `tasks/list` 假設。
- 在 POST 回應的 SSE 串流上，透過 `subscriptions/listen` 訂閱選用的任務通知。
- 正確地為任務到期、重啟復原、輸入鍵去重與執行錯誤建模。

## 為什麼 Tasks 是一個擴充

Tasks 最早在 2025-11-25 以實驗性核心功能的身分登場。2026 年 7 月的重新設計把它們搬進官方的 `io.modelcontextprotocol/tasks` 擴充，讓客戶端與伺服器可以自行選入這套額外的生命週期，而不必為了所有人擴張核心協定。

即使這個擴充規格已是 Tasks 目前的官方歸屬，它仍然是一份草案介面。請把你的 SDK 支援的擴充版本固定住，跑一致性情境，並把線路轉接層跟你的 worker 與儲存領域隔離開來。

當操作具備下列一項以上的性質時，就用任務：

- 它可能撐過一般請求的逾時。
- 執行已經由某個 worker 佇列或外部工作系統掌管。
- 客戶端需要在自己重啟之後復原。
- 操作在執行過程中會暫停，等待使用者或模型輸入。
- 取消與持久取回結果是產品需求。

不要為一次便宜的確定性查表建立任務。把手、持久化、輪詢、到期與取消，都是實實在在的複雜度。

## 無狀態核心，有狀態應用

MCP 2026-07-28 移除了 `initialize`、`notifications/initialized`、協定工作階段與 `Mcp-Session-Id`。這並不禁止有狀態的產品。

任務 id 是明確的應用狀態：

- 伺服器在回傳它之前就先持久化它。
- 客戶端可以存起來，並在重啟之後再次輪詢。
- 那個 id 可以路由到任何一個由同一份持久儲存區支撐的副本。
- 每一個任務方法都會檢查授權。
- 到期與刪除是由任務欄位定義的，不是由傳輸生命期定義。

這跟「掛在連線上的隱藏狀態」在運維上完全不同。

讓四種生命期保持分離：

| 狀態 | 生命期 | 該放在哪裡 |
|---|---|---|
| 協定中繼資料 | 一則請求 | `params._meta`，每次呼叫都重新驗證 |
| 傳輸工作 | 一次 stdio 請求或一則 HTTP 回應 | 帶有明確期限的在途協調器 |
| MRTR 續行 | 一段重試序列 | 有完整性保護的 `requestState`，必要時加上重播控制 |
| 持久任務 | 跨請求、跨副本、跨重啟與跨重連 | 以已授權的 `taskId` 為鍵的共用應用儲存區 |

把任務紀錄搬進行程記憶體，並不會讓 MCP 變成有狀態。它只會讓應用變得不可靠。協定依然無狀態，但後續被路由到另一個副本的 `tasks/get` 就找不回那筆紀錄了。先持久化再回傳把手，然後讓每一個任務方法都在租戶與主體檢查之下，解析到同一筆共用紀錄。

## 能力協商

客戶端在每一則符合條件的請求上公告支援：

```json
{
  "_meta": {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {
      "extensions": {
        "io.modelcontextprotocol/tasks": {}
      }
    },
    "io.modelcontextprotocol/clientInfo": {
      "name": "lesson-client",
      "version": "1.0.0"
    }
  }
}
```

伺服器從 `server/discover` 回傳精確的 `supportedVersions`、能力、`ttlMs` 與 `cacheScope`，並在 capabilities 底下放上同一個擴充。因為它公告了工具，所以也實作必備的 `tools/list`。那個結果會回傳一份確定性的 `generate_report` 描述、有效的物件型 `inputSchema`、`resultType: "complete"`、伺服器身分中繼資料，以及公開的快取提示。

來自未宣告該擴充之客戶端的任務方法，會回傳 `-32021`（Missing Required Client Capability），並把 `data.requiredCapabilities` 設為 `{"extensions":{"io.modelcontextprotocol/tasks":{}}}`。不受支援的協定字串回傳 `-32022`，附上精確的 `supported` 與 `requested` 資料；版本缺漏或不是字串則回傳 `-32602`。

沒有 JSON-RPC `id` 的信封是通知。接收方可以處理它，但不會發出 JSON-RPC 的結果或錯誤。Streamable HTTP 轉接層對被接受的通知回傳 `202 Accepted` 且沒有主體。

目前只有 `tools/call` 支援任務增強執行。設計你的內部抽象時，要讓未來新增的請求型別不需要重寫儲存層。

## 由伺服器主導的任務建立

舊的客戶端旗標 `params._meta.task.required` 已經沒了。客戶端宣告擴充支援，接著由伺服器決定某一次 `tools/call` 是否要變成任務。

請求：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "generate_report",
    "arguments": {"size": "large"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
          "io.modelcontextprotocol/tasks": {}
        }
      }
    }
  }
}
```

回應：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "task",
    "taskId": "tsk_786512e29e0d",
    "status": "working",
    "statusMessage": "Preparing report outline.",
    "createdAt": "2026-08-21T10:30:00Z",
    "lastUpdatedAt": "2026-08-21T10:30:00Z",
    "ttlMs": 900000,
    "pollIntervalMs": 1000
  }
}
```

在針對該 id 的 `tasks/get` 能夠解析成功之前，伺服器不得回傳這個把手。在最終一致性的儲存區裡，要等到讀取可見之後再回答。否則客戶端可能拿到一個看起來有效的 id，卻立刻收到「找不到」。

任務回應是「未經請求」的，意思是客戶端並沒有要求任務模式。但它不是「未經協商」的：當前這則請求仍然必須公告該擴充。

## 任務的形狀

每一個任務都帶著：

- `taskId`：由伺服器產生的穩定識別碼；
- `status`：`working`、`input_required`、`completed`、`cancelled` 或 `failed`；
- `createdAt` 與 `lastUpdatedAt`：ISO 8601 時間戳記；
- `ttlMs`：自建立起算的到期時長，或 `null` 表示未公告上限；
- 選用的 `pollIntervalMs`：伺服器當前建議的最小輪詢間隔；
- 選用的 `statusMessage`：給使用者或模型看的脈絡。

狀態專屬的欄位只在相關時出現：

- `input_required` 包含 `inputRequests`。
- `completed` 包含原始請求的 `result` 形狀。
- `failed` 包含一個 JSON-RPC `error` 物件。

客戶端應該遵守 `pollIntervalMs`。伺服器可以對更激進的輪詢做速率限制，也可以在任務生命期內改變那個間隔。

## 用 `tasks/get` 輪詢

客戶端索取一份當前快照：

```http
POST /mcp HTTP/1.1
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tasks/get
Mcp-Name: tsk_786512e29e0d
```

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tasks/get",
  "params": {
    "taskId": "tsk_786512e29e0d",
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
          "io.modelcontextprotocol/tasks": {}
        }
      }
    }
  }
}
```

`tasks/get` 這則 RPC 本身完成了，所以它的結果永遠是 `resultType: "complete"`。裡面那個任務仍然可以是 `status: "working"` 或 `status: "input_required"`。

這個區分能避免一個常見的解析錯誤：

```text
result.resultType = complete    means the tasks/get RPC finished
result.status = working        means the represented job is still running
```

沒有 `tasks/result` 這個呼叫。任務完成時，下一次 `tasks/get` 的回應會把原本的 `CallToolResult` 內嵌在 `result` 底下：

```json
{
  "resultType": "complete",
  "taskId": "tsk_786512e29e0d",
  "status": "completed",
  "createdAt": "2026-08-21T10:30:00Z",
  "lastUpdatedAt": "2026-08-21T10:34:12Z",
  "ttlMs": 900000,
  "result": {
    "resultType": "complete",
    "content": [
      {"type": "text", "text": "Generated large report with approved outline."}
    ],
    "structuredContent": {"size": "large", "approved": true},
    "isError": false,
    "_meta": {
      "io.modelcontextprotocol/serverInfo": {
        "name": "tasks-demo",
        "version": "1.0.0"
      }
    }
  },
  "_meta": {
    "io.modelcontextprotocol/serverInfo": {
      "name": "tasks-demo",
      "version": "1.0.0"
    }
  }
}
```

外層的 `resultType` 說的是 `tasks/get` 這則 RPC 完成了。內層的 `result.resultType` 說的是原本那次工具呼叫完成了。內層那個判別欄位是必填的。內層的 `CallToolResult` 也「應該」帶上自己的 `io.modelcontextprotocol/serverInfo`；這一課選擇附上它，而不是存一份沒有型別的負載。

沒有 `tasks/list`。沒有工作階段的伺服器，無法安全地推斷哪些任務該出現在一份以連線為範圍的清單裡。需要歷史紀錄的應用，應該暴露一個已授權的領域工具，附帶明確的過濾條件與擁有權規則。

## 任務執行期間的輸入

任務輸入與核心 MRTR 看起來很像，但使用的是不同的續行機制。

### 任務建立之前需要的輸入

從原本的 `tools/call` 回傳核心的 `resultType: "input_required"`。客戶端滿足它，然後重試那次原始呼叫。等那些同步的 MRTR 回合結束之後，再建立任務。

### 任務建立之後需要的輸入

把任務設為 `input_required`。`tasks/get` 會暴露仍待處理的 `inputRequests`，客戶端則透過 `tasks/update` 送出回應。客戶端不會重試原本的 `tools/call`。

快照：

```json
{
  "resultType": "complete",
  "taskId": "tsk_786512e29e0d",
  "status": "input_required",
  "createdAt": "2026-08-21T10:30:00Z",
  "lastUpdatedAt": "2026-08-21T10:31:00Z",
  "ttlMs": 900000,
  "inputRequests": {
    "approve_outline": {
      "method": "elicitation/create",
      "params": {
        "mode": "form",
        "message": "Approve the generated report outline?",
        "requestedSchema": {
          "type": "object",
          "properties": {"approved": {"type": "boolean"}},
          "required": ["approved"]
        }
      }
    }
  }
}
```

更新：

```http
POST /mcp HTTP/1.1
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tasks/update
Mcp-Name: tsk_786512e29e0d
```

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tasks/update",
  "params": {
    "taskId": "tsk_786512e29e0d",
    "inputResponses": {
      "approve_outline": {
        "action": "accept",
        "content": {"approved": true}
      }
    },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
          "io.modelcontextprotocol/tasks": {}
        }
      }
    }
  }
}
```

成功的回應是一則空的確認，加上 `resultType: "complete"`。狀態變更可能是最終一致的，所以客戶端要繼續輪詢或繼續監聽。

每一個 `inputRequests` 的鍵，在整個任務生命期內都必須是唯一的。重複的 `tasks/get` 快照可能顯示同一個仍待處理的鍵；客戶端要在 UI 上去重，伺服器則忽略針對未知、已被取代或已滿足之鍵的回應。一次部分更新可能讓任務停在 `input_required`，直到所有必填的鍵都被回答。

## 取消是協同式的

`tasks/cancel` 表達的是意圖，回傳一則空的完整確認。那則確認並不保證 worker 已經停下。工作可能先完成、可能忽略取消，也可能稍後才轉換狀態。

```http
POST /mcp HTTP/1.1
Content-Type: application/json
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tasks/cancel
Mcp-Name: tsk_786512e29e0d
```

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tasks/cancel",
  "params": {
    "taskId": "tsk_786512e29e0d",
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "extensions": {
          "io.modelcontextprotocol/tasks": {}
        }
      }
    }
  }
}
```

這三個任務方法的 `Mcp-Name` 都鏡射 `params.taskId`。它不是重複那個 JSON-RPC 方法名稱。`code/main.py` 把這條規則集中在 `make_http_request` 裡。

這一課的 worker 會立刻遵從取消，因此重複呼叫是冪等的。正式環境的客戶端仍然必須把取消當成協同式的，而不是從那則確認推斷出任務的最終狀態。

不要用 `notifications/cancelled` 去取消任務。那則通知屬於請求取消，不屬於持久的 Tasks。

這個區分在路由邊界上很重要。請求取消針對的是一則在途的 JSON-RPC 操作，或它那則請求範圍的 HTTP 回應。如果 `tools/call` 已經回傳了 `resultType: "task"`，那則請求就結束了，關掉它的傳輸也無法指名或停下那個持久工作。`tasks/cancel` 是一則新的、已授權的 RPC。它帶著 `params.taskId`、在 `Mcp-Name` 裡鏡射那個 id、解析出擁有該任務的後端、記下協同式取消的意圖，然後回傳一則確認 —— 但不宣稱 worker 已經停下。

因此閘道必須把請求協調器與任務路由放在不同的表裡。請求表可以在回應結束時消失。任務路由則必須撐到終局狀態與保留期到期為止。[單元 29：MCP 可靠性、取消與流量控制](../../29-mcp-reliability-cancellation-and-flow-control/docs/en.md) 會為這兩條路徑建構競態、逾時、冪等性、反壓與重試規則。

## 選用的通知

輪詢是基準線。想要推送更新的客戶端，會帶著任務 id 送出 `subscriptions/listen`。在 Streamable HTTP 上，這是一次 POST，它的回應是一條請求範圍的 SSE 串流。沒有獨立的 GET 事件串流，也沒有需要保活的協定工作階段。

伺服器用 `notifications/subscriptions/acknowledged` 確認被接受的 id，接著就能透過 `notifications/tasks` 送出完整快照。那則確認與每一則任務通知，都在 `_meta` 裡帶著 `io.modelcontextprotocol/subscriptionId`，其值等於 `subscriptions/listen` 的請求 id。除此之外，每一則任務通知等同於當下 `tasks/get` 會回傳的內容。

客戶端仍然必須宣告 Tasks 擴充。它們應該重連，並從持久的任務 id 恢復，而不是依賴事件重播或 `Last-Event-ID`。

## 失敗語意

正確使用這兩層錯誤。

### 協定錯誤

無效的方法參數或未知的任務 id 回傳 JSON-RPC 錯誤，通常是 `-32602`。缺少擴充支援回傳 `-32021`，並附上必要能力物件。

### 任務執行結果

- 一則帶 `isError: true` 的正常工具結果，任務仍然是 `completed`，因為那次工具呼叫產出了它所定義的結果。
- 延後執行期間發生的 JSON-RPC 錯誤，會讓任務變成 `failed`，並把那個 JSON-RPC 錯誤存在 `error` 底下。
- 使用者拒絕可以產生 `cancelled`、一個已完成的拒絕結果，或另一種領域專屬的安全結果。把你的選擇寫進文件。

## 持久性、到期與擁有權

至少要持久化：任務 id、狀態、時間戳記、ttl、輪詢間隔、原始操作的擁有權、結果或錯誤、仍待處理的輸入請求，以及所有發出過的輸入鍵。

儲存鍵必須包含、或能解析出權威的租戶與主體。知道一個任務 id 不得等同於取得存取權。在每一次 `tasks/get`、`tasks/update`、`tasks/cancel` 與訂閱時都檢查擁有權。

`ttlMs` 從建立時起算，而且可能改變。當任務不再產出可觀察的更新時，客戶端可以把它當成最後防線。伺服器可以讓一個過期任務失敗，之後再把它刪掉。不要把它描述成「完成之後還會保留結果那麼多毫秒」的承諾。

使用原子寫入或交易。這一課會寫一個暫存檔，然後原子性地改名。多副本的服務應該使用共用的持久儲存區，加上 worker 租約或等價的並行控制。

```figure
tp-task-lifecycle
```

## 動手實作

`code/main.py` 實作了一個確定性的任務服務：

- `server/discover` 回傳 `supportedVersions`、快取提示與 Tasks 擴充。
- `tools/list` 回傳一份確定性、可快取的 `generate_report` 描述，附帶有效的輸入 schema。
- `tools/call` 先建立並持久化任務，才回傳 `resultType: "task"`。
- 一個新的服務實例會重新載入同一個任務，示範重啟復原。
- `tasks/get` 回傳完整的任務快照。
- worker 從 `working` 走到 `input_required`。
- `tasks/update` 接受一則表單回應，並回傳一則空的完整確認。
- worker 存下一個帶有自己 `resultType` 與伺服器身分的內嵌 `CallToolResult`，然後轉為 `completed`。
- 在這份實作裡，`tasks/cancel` 是冪等的。
- HTTP 建構器會把 `tasks/get`、`tasks/update` 與 `tasks/cancel` 的 `Mcp-Name` 設為 `params.taskId`。
- 通知輔助器使用 `notifications/subscriptions/acknowledged` 與 `notifications/tasks`，兩者都標上 listen 請求的 id。
- 沒有 id 的通知不會產生任何 JSON-RPC 回應。

worker 是明確推進的，而不是在背景執行緒裡睡覺。這讓每一次狀態轉換都具確定性，也讓協定範例跟佇列機制保持分離。

## 框架應用

從版本庫根目錄：

```bash
cd phases/13-tools-and-protocols/13-mcp-async-tasks/code
python3 main.py
python3 -m unittest discover tests -v
```

預期的結果序列：

```text
id=0 resultType=complete status=ack
id=1 resultType=task status=working
id=2 resultType=complete status=working
id=3 resultType=complete status=input_required
id=4 resultType=complete status=ack
id=5 resultType=complete status=completed
```

也請驗證在現代服務裡，`tasks/status`、`tasks/result` 與 `tasks/list` 都回傳 method-not-found。
並驗證 `tools/list` 具確定性，而且每一個現行的 HTTP 任務方法都透過 `Mcp-Name` 鏡射它的任務 id。

## 產出交付

`outputs/skill-task-store-designer.md` 現在會產出一份帶擴充意識的設計：能力協商、先持久化再回傳的建立流程、現行方法、輸入更新流程、擁有權、到期、取消、訂閱，以及從那些已移除的實驗性方法遷移過來的路徑。

## 練習

1. 加上第二個仍待處理的輸入鍵。送出一次部分的 `tasks/update`，並證明在兩個鍵都被回答之前，任務維持在 `input_required`。
2. 為儲存區加上租戶擁有權，並拒絕由錯誤的已認證主體所提出的有效任務 id。
3. 加上帶到期時間的 worker 租約。示範兩個服務實例無法同時完成同一個任務。
4. 為 `subscriptions/listen` 實作一個 POST 回應的 SSE 轉接層。不要加上 GET、`Last-Event-ID` 或工作階段標頭。
5. 加上到期清理。在不洩漏跨租戶存在性的前提下，分辨「已過期的任務」與「格式錯誤的任務 id」。

## 關鍵術語

| 術語 | 在現行擴充裡的意義 |
|------|----------------------------------|
| Tasks 擴充 | 選用的 `io.modelcontextprotocol/tasks` 能力，用於持久的非同步工作 |
| `CreateTaskResult` | 對符合條件之請求，由伺服器主導回傳的 `resultType: "task"` 回應 |
| `tasks/get` | 輪詢一份完整的當前任務快照，包含終局結果或待處理輸入 |
| `tasks/update` | 對任務仍待處理的 `inputRequests` 送出回應 |
| `tasks/cancel` | 確認協同式取消的意圖 |
| `input_required` | 表示仍有客戶端輸入待處理的任務狀態 |
| `pollIntervalMs` | 伺服器建議的、下一次輪詢前的最小延遲 |
| `ttlMs` | 自任務建立起算的到期時長 |
| 先持久化再回傳 | 在送出把手之前，任務 id 必須已能解析的規則 |
| `notifications/tasks` | 在已訂閱的 SSE 回應上送出的選用完整任務快照 |

## 舊版相容

2025-11-25 的實驗性介面使用的是由客戶端請求的任務增強、`tasks/status`、`tasks/result`，以及選用的 `tasks/list`。那些名稱只保留在一個版本固定的舊版轉接層裡。現行客戶端使用擴充能力、接受由伺服器主導的把手、輪詢 `tasks/get`、用 `tasks/update` 提供輸入，並從任務快照裡讀取最終結果。

## 延伸閱讀

- [Official MCP Tasks extension](https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks)
- [MCP 2026-07-28 Multi Round-Trip Requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 2026-07-28 Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
