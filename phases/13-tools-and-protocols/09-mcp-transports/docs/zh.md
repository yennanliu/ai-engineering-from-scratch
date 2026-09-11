# MCP 傳輸：stdio 與無狀態的 Streamable HTTP

> 傳輸負責搬運 MCP 訊息。它不會補上缺漏的協定狀態。在 `2026-07-28` 裡，本機的 stdio 與遠端的 Streamable HTTP 搬的都是自我描述的請求。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 13，單元 07 與 08
**時間：** 約 65 分鐘

## 學習目標

- 本機子行程選 stdio，網路服務選 Streamable HTTP。
- 實作現代的單一端點、只收 POST 的 Streamable HTTP 契約。
- 把 MCP 版本、方法與名稱標頭對照 JSON-RPC 主體做鏡射與驗證。
- 正確地送出請求範圍的 SSE，以及長時間存活的 `subscriptions/listen` 串流。
- 遷移以工作階段為基礎的、以及舊版 HTTP+SSE 的部署，且不把舊行為包裝成現代行為。

## 問題所在

較早的 Streamable HTTP 修訂版，把協定協商跟連線與工作階段行為混在一起。伺服器可以鑄造 `Mcp-Session-Id`、暴露一條獨立的 GET 串流、接受 DELETE 來終止工作階段，還能用 `Last-Event-ID` 續傳 SSE。

MCP `2026-07-28` 把那些機制從現代線路上移除了。每一則請求都能落在任何一個健康的 worker 上，因為它的協定版本與客戶端能力就在請求主體裡。HTTP 標頭為了路由與政策而鏡射部分欄位，但伺服器會在執行之前，拿那些標頭跟主體互相驗證。

結果是更容易擴展，也更容易推理。這也意味著：一台把 2025 年的傳輸方式當成現行做法在教的伺服器，教的是錯的失敗模型與安全模型。

## 核心概念

### stdio

stdio 綁定適用於由客戶端啟動的子行程：

- 客戶端每行寫一則 UTF-8 JSON-RPC 訊息到 stdin。
- 伺服器每行寫一則 UTF-8 JSON-RPC 訊息到 stdout。
- 伺服器把診斷訊息寫到 stderr。
- 伺服器在 stdin 收到 EOF 時立刻結束。
- 每一則現代請求都在 `params._meta` 裡帶著版本與客戶端能力。

這個行程可能撐過很多次呼叫，但它不是現代的協定工作階段。如果它意外結束，在途的請求就遺失了。重啟行程、重新發現、重新列清單、重新開啟訂閱，並用新的請求 id 重試安全的操作。

### 2026-07-28 的 Streamable HTTP

現代伺服器暴露單一個 MCP 端點，例如 `/mcp`，只接受 POST。

每一則 JSON-RPC 請求或通知都是一次新的 HTTP POST。主體裡放一則 JSON-RPC 訊息。客戶端不會送 JSON-RPC 回應給伺服器。

對於請求，伺服器回傳以下兩者之一：

- `Content-Type: application/json`，內含一則 JSON-RPC 回應；或
- `Content-Type: text/event-stream`，內含與該請求相關的通知，最後接上最終的 JSON-RPC 回應。

對於被接受的通知，伺服器回傳 `202 Accepted`，沒有主體。

客戶端會同時公告兩種回應型別：

```http
Accept: application/json, text/event-stream
```

### 只收 POST 就是只收 POST

現代 Streamable HTTP 沒有獨立的 GET 串流，也沒有 DELETE 工作階段端點。

- `GET /mcp` 回傳 `405 Method Not Allowed`。
- `DELETE /mcp` 回傳 `405 Method Not Allowed`。
- `Mcp-Session-Id` 會被忽略，永遠不鑄造、也不回送。
- `Last-Event-ID` 會被忽略，因為現代串流不可續傳。

如果請求範圍的串流在最終回應之前就斷了，客戶端就是遺失了那則在途請求。在重試安全的前提下，它可以用一個新的 JSON-RPC id 發出新請求。它不得嘗試續傳串流。

### Origin 驗證

伺服器會對進來的連線驗證 `Origin`，以防 DNS 重新綁定攻擊。如果標頭存在但未被明確允許，回傳 `403 Forbidden`。非瀏覽器的客戶端可以省略 `Origin`，官方的傳輸規則允許這一點。

本機伺服器應該綁在 `127.0.0.1`，而不是每一張網卡上。網路服務仍然需要在每一則請求上做認證與授權。Origin 驗證不是認證。

在把設定正規化之後，採用精確的 origin 比對。像 `origin.startswith("https://trusted.example")` 這種前綴檢查並不安全，因為它可能接受由攻擊者控制的後綴。

### 必填的 HTTP 中繼資料標頭

每一則現代 POST 請求都包含：

```http
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: notes_search
```

標頭規則：

- `MCP-Protocol-Version` 必填，且必須等於 `params._meta.io.modelcontextprotocol/protocolVersion`。
- `Mcp-Method` 必填，且必須等於 JSON-RPC 的 `method`。
- `Mcp-Name` 在 `tools/call`、`resources/read` 與 `prompts/get` 上必填。
- `Mcp-Name` 等於 `params.name`，`resources/read` 則等於 `params.uri`。
- 標頭名稱不分大小寫，但標頭值是分大小寫的。

不安全或非 ASCII 的 `Mcp-Name` 值，使用精確的 UTF-8 Base64 標記形式：

```text
=?base64?{Base64EncodedValue}?=
```

伺服器會先解碼那個值，再拿去跟主體比對。

鏡射標頭缺漏、格式錯誤或內容不符，回傳 HTTP `400` 與 JSON-RPC 錯誤碼 `-32020`。如果標頭與主體對某個伺服器不支援的版本取得一致，回傳 HTTP `400` 與 `-32022`，並附上精確的錯誤資料，例如 `{"supported":["2026-07-28"],"requested":"2027-01-01"}`。

未知的現代方法回傳 HTTP `404` 與 JSON-RPC `-32601`。那個 JSON-RPC 主體很重要，因為跨時代的客戶端要靠它分辨「現代錯誤」與「舊版端點沒找到」。

### 請求範圍的 SSE

伺服器可以對某一則長時間執行的請求選用 SSE：

```text
POST tools/call id=41
  <- notifications/progress related to id=41
  <- notifications/progress related to id=41
  <- JSON-RPC response id=41
stream closes
```

伺服器不得在這條串流上送出獨立的 JSON-RPC 請求。Sampling、elicitation 與 roots 的互動一律走 Multi Round-Trip Request 結果。關閉回應串流即取消該請求。

不要為了重播而加上 SSE 事件 id。`Last-Event-ID` 續傳不屬於現代修訂版。

### 長時間存活的變更走 subscriptions/listen

變更通知使用由客戶端開啟的請求，而不是獨立的 GET：

```json
{
  "jsonrpc": "2.0",
  "id": "listen-1",
  "method": "subscriptions/listen",
  "params": {
    "notifications": {
      "toolsListChanged": true,
      "resourceSubscriptions": ["notes://note-1"]
    },
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

這次 POST 的回應是一條長時間存活的 SSE 串流。它的第一則協定訊息是 `notifications/subscriptions/acknowledged`。這則確認、每一則變更通知，以及最終結果，都會在 `_meta` 裡帶著 `io.modelcontextprotocol/subscriptionId`，其值等於 listen 請求的 id。伺服器可以發出 SSE 註解當作保活。串流掉線時，客戶端用一個新的請求 id 重新送出 `subscriptions/listen`，並重新抓取受影響的資料。

`resources/subscribe` 與 `resources/unsubscribe` 屬於舊版時代。不要在現代連線上使用它們。

### 明確的應用狀態

移除協定工作階段，並不代表禁止有狀態的工作流程。伺服器可以鑄造一個不透明的狀態把手，並把它當成一般的工具結果回傳。客戶端在後續呼叫時，把那個把手當成明確的參數送出。

把把手綁定到已認證的主體、讓它無法被猜到、給它過期時間，並在每一次使用時做授權。這讓狀態顯露在應用層，而不是藏在傳輸親和性裡。

隱藏的副本狀態所造成的失敗是很機械式的：

1. 請求 A 抵達副本 1，在那個行程的記憶體裡建立了一份草稿。
2. 回應沒有回傳草稿把手，因為那個實作假設連線本身就足以標識草稿。
3. 請求 B 是一次全新的 POST，抵達副本 2。
4. 副本 2 有有效的協定中繼資料，卻沒有辦法指名或載入那份草稿，於是工作流程失敗，或讀到錯誤的本地物件。
5. 黏著式路由看起來把症狀解決了 —— 直到一次重啟、上線、重新排程或故障轉移，把下一則請求搬走。

正確的邊界有兩個部分。協定脈絡留在每一則請求裡。持久的應用狀態放在共用儲存區，藏在一個由伺服器鑄造、回傳給客戶端的把手底下。下一次呼叫附上那個把手，任何副本都能載入同一筆紀錄，而授權會把那筆紀錄綁到已認證的主體與租戶上。副本記憶體可以快取一筆紀錄，但它不能是正確性所需的唯一一份副本。

依生命期挑選狀態機制。請求範圍的區域變數只能服務單次呼叫。短暫的 MRTR 續行可以用有完整性保護的 `requestState`。草稿或持久任務則需要明確的把手，加上共用持久化、過期、並行控制與冪等性。這些物件沒有一個是 MCP 協定工作階段。

### HTTP 跨時代相容

同時支援現代與舊版伺服器的客戶端，會先嘗試一次現代 POST。如果收到 HTTP `400`、`404` 或 `405`，它就檢視主體：

- 可辨識的現代 JSON-RPC 錯誤，證明伺服器是現代的。修正請求，或改用它公告的某個版本重試。不要降級。
- 空主體或無法辨識的回應，可能代表對面是舊版 HTTP+SSE 伺服器。只有在這種情況下，才去試舊的 GET 端點，並預期它的舊版 `endpoint` 事件。

伺服器在遷移期間可以同時支援兩個時代：把帶有現代中繼資料的流量導向只收 POST 的現代實作，同時為舊客戶端保留獨立的舊版端點。絕不要把舊版的 GET、DELETE、工作階段 id 或重播行為，描述成 `2026-07-28` 的一部分。

```figure
tp-transport-handshake
```

## 框架應用

`code/main.py` 用 Python 標準函式庫實作了一台有限次、現代的 Streamable HTTP 伺服器。它驗證 Origin 與鏡射標頭、忽略已移除的工作階段標頭、對一般呼叫回傳 JSON，並示範一條有限次的 `subscriptions/listen` SSE 串流。

```bash
cd code
python3 main.py --probe
python3 -m unittest discover tests -v
```

這支探測會檢查：

- 無效的 Origin 會被拒絕；
- 沒有工作階段 id 也能成功發現；
- `Mcp-Session-Id` 與 `Last-Event-ID` 會被忽略；
- 標頭不一致回傳 `-32020`；
- 不支援的版本回傳 `-32022`，並附上精確的 `supported` 與 `requested` 資料；
- 被接受、沒有 id 的通知回傳 HTTP `202` 且沒有主體；
- GET 與 DELETE 回傳 `405`；
- `subscriptions/listen` 是一條 POST 回應串流，其確認、通知與最終結果都帶著它的訂閱 id。

## 產出交付

這一課交付 `outputs/skill-mcp-transport-migrator.md`。它會移除現代的協定工作階段、加上標頭與主體的比對驗證、用 `subscriptions/listen` 取代獨立的 GET，並讓任何舊版橋接維持在明顯分離的位置。

## 練習

1. 從一次 POST 裡拿掉 `Mcp-Method`。確認回傳 HTTP `400` 與錯誤 `-32020`。
2. 送出標頭與主體一致、版本為 `2027-01-01` 的請求。確認回傳 HTTP `400`、錯誤 `-32022`，以及精確的資料 `{"supported":["2026-07-28"],"requested":"2027-01-01"}`。
3. 為一個非 ASCII 的資源 URI 送出 Base64 標記形式的 `Mcp-Name`。確認解碼後的值有拿去跟 `params.uri` 比對。
4. 在有限次的 listen 串流拿到最終回應之前把它弄斷。用新的 JSON-RPC id 重新送出它，並重抓工具。
5. 為 ping 工具加上一個明確的工作流程把手。把它綁到一個授權主體上，過程中不使用連線親和性。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| stdio | 在客戶端啟動的子行程上，以換行分隔的 JSON-RPC |
| Streamable HTTP | 單一端點，每一則現代訊息都是一次新的 POST |
| 請求範圍 SSE | POST 回應串流，內含相關通知與最終回應 |
| `subscriptions/listen` | 長時間存活的 POST 請求，用於選擇性訂閱的變更通知 |
| 標頭不一致 | 鏡射標頭與主體不符時的 HTTP `400` 與 JSON-RPC `-32020` |
| Origin 驗證 | 針對進站連線的 DNS 重新綁定防禦，不是認證 |
| 明確狀態把手 | 以一般參數傳遞的應用層權杖，取代隱藏的工作階段狀態 |
| 舊版橋接 | 僅為相容性而保留、獨立存在的早期時代行為 |

## 延伸閱讀

- [MCP Transport Overview](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)
- [MCP stdio Transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
- [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [MCP Subscriptions](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/subscriptions)
- [MCP 2026-07-28 Changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
