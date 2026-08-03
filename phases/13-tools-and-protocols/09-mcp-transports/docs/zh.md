# MCP 傳輸 —— stdio 對 Streamable HTTP 對 SSE 遷移

> stdio 在本機能用，在其他地方都不能。Streamable HTTP（2025-03-26）是遠端的標準。舊的 HTTP+SSE 傳輸已被棄用，並將在 2026 年年中移除。挑錯傳輸的代價是一次遷移；挑對的話，你買到的是一台可遠端託管、具備工作階段連續性與 DNS 重繫結防護的 MCP 伺服器。

**類型：** 學習
**程式語言：** Python (stdlib, Streamable HTTP endpoint skeleton)
**先修單元：** 階段 13 · 07、08（MCP 伺服器與客戶端）
**時間：** 約 45 分鐘

## 學習目標

- 依部署形狀（本機對遠端、單行程對機隊），在 stdio 與 Streamable HTTP 之間做選擇。
- 實作 Streamable HTTP 的單端點模式：用 POST 處理請求、用 GET 開工作階段串流。
- 落實 `Origin` 驗證與工作階段 id 語意，以擊退 DNS 重繫結。
- 在 2026 年年中的移除期限之前，把一台舊的 HTTP+SSE 伺服器遷移到 Streamable HTTP。

## 問題所在

第一版 MCP 遠端傳輸（2024-11）是 HTTP+SSE：兩個端點，一個接客戶端的 POST，一個是伺服器對客戶端串流用的 Server-Sent-Events 通道。它能用。但也很笨拙：每個工作階段兩個端點、在某些 CDN 前面會弄壞快取，還硬性依賴長連線的 SSE，而某些 WAF 會很積極地把它切斷。

2025-03-26 版規格用 Streamable HTTP 取代了它：一個端點，POST 給客戶端請求，GET 用來建立工作階段串流，兩者共用一個 `Mcp-Session-Id` 標頭。從那時起打造或遷移的每一台伺服器都用 Streamable HTTP。舊的 SSE 模式正在被棄用 —— Atlassian Rovo 於 2026 年 6 月 30 日移除；Keboola 是 2026 年 4 月 1 日；其餘多數企業伺服器則在 2026 年底前完成。

而 stdio 對本機伺服器仍然重要。Claude Desktop、VS Code，以及每一個 IDE 形狀的客戶端，都是透過 stdio 啟動伺服器的。正確的心智模型是：stdio 給「這台機器」，Streamable HTTP 給「跨網路」。兩者不交叉。

## 核心概念

### stdio

- 子行程傳輸。客戶端啟動伺服器，透過 stdin／stdout 溝通。
- 每行一個 JSON 物件。以換行分隔。
- 沒有工作階段 id；行程的身分就是那個工作階段。
- 不需要認證（子行程繼承了父行程的信任邊界）。
- 絕不要用在遠端伺服器上 —— 那會需要 SSH 或 socat 來做隧道，而既然如此，不如直接用 Streamable HTTP。

### Streamable HTTP

單一端點 `/mcp`（或任何路徑）。支援三種 HTTP 方法：

- **POST /mcp。** 客戶端送出一則 JSON-RPC 訊息。伺服器回覆單一份 JSON 回應，或一道包含一則以上回應的 SSE 串流（對批次回應與該請求相關的通知很有用）。
- **GET /mcp。** 客戶端開啟一條長連線的 SSE 通道。伺服器用它來發出伺服器對客戶端的請求（sampling、通知、elicitation）。
- **DELETE /mcp。** 客戶端明確終止該工作階段。

工作階段以 `Mcp-Session-Id` 標頭識別 —— 伺服器在第一次回應時設定它，客戶端在之後每次請求都回敘它。工作階段 id「必須」是密碼學隨機的（128 位元以上）；為了安全，由客戶端指定的 id 會被拒絕。

### 單端點對雙端點

舊規格的雙端點模式在 2026 年仍可呼叫 —— 規格宣告它為「相容舊版」。但所有新伺服器都該用單端點。官方 SDK 產出的是單端點；只有在跟一個尚未遷移的遠端對話時，才使用舊版模式。

### `Origin` 驗證與 DNS 重繫結

瀏覽器（在今天）不是 MCP 客戶端，但攻擊者可以打造一個網頁，說服瀏覽器去 POST 到 `localhost:1234/mcp` —— 也就是使用者本機 MCP 伺服器監聽的地方。如果伺服器不檢查 `Origin`，瀏覽器的同源政策救不了它，因為 `Origin: http://evil.com` 是一個合法的跨來源值。

2025-11-25 版規格要求伺服器拒絕 `Origin` 不在白名單上的請求。白名單通常包含 MCP 客戶端的宿主（`https://claude.ai`、`vscode-webview://*`）以及給本機 UI 用的 localhost 變體。

### 工作階段 id 的生命週期

1. 客戶端送出第一次請求，不帶 `Mcp-Session-Id`。
2. 伺服器指派一個隨機 id，並在回應標頭中設上 `Mcp-Session-Id`。
3. 客戶端在之後所有請求，以及開串流的 `GET /mcp` 上，都回敘那個標頭。
4. 工作階段可被伺服器撤銷；客戶端在後續請求上會看到 404，必須重新初始化。
5. 客戶端可以明確 DELETE 該工作階段以乾淨地關閉。

### Keepalive 與重連

SSE 連線會斷。客戶端靠帶著同一個 `Mcp-Session-Id` 重新 GET 來重建它。伺服器「必須」把中斷期間錯過的事件排入佇列（在合理的視窗內），並透過客戶端回敘的 `last-event-id` 標頭重播。

階段 13 · 13 會談 Tasks，它能讓長時間執行的工作，連整個工作階段重連都活得下來。

### 向後相容的探測

一個想同時支援新舊伺服器的客戶端會這樣做：

1. POST 到 `/mcp`。
2. 如果回應是帶 JSON 或 SSE 的 `200 OK`，那就是 Streamable HTTP。
3. 如果回應是帶 `Content-Type: text/event-stream` 的 `200 OK`，「而且」有一個指向次要端點的 `Location` 標頭，那就是舊版 HTTP+SSE；跟著 `Location` 走。

### Cloudflare、ngrok 與託管

2026 年的生產級遠端 MCP 伺服器跑在 Cloudflare Workers（搭配他們的 MCP Agents SDK）、Vercel Functions，或容器化的 Node／Python 上。關鍵是：你的託管環境必須支援長連線的 HTTP，才能撐住那個 SSE GET。Vercel 的免費方案上限是 10 秒，不適用。Cloudflare Workers 支援無限期串流。

### 閘道的組合

當你用一個閘道罩住多台 MCP 伺服器時（階段 13 · 17），這個閘道就是單一個 Streamable HTTP 端點，負責改寫工作階段 id 並對上游做多工。工具在閘道層合併；客戶端看到的是單一台邏輯伺服器。

### 傳輸的失敗模式

- **stdio SIGPIPE。** 子行程在寫入途中死亡會引發 SIGPIPE；伺服器應該乾淨地結束。客戶端應該偵測到 EOF 並把工作階段標記為已死。
- **HTTP 502／504。** Cloudflare、nginx 與其他代理在上游失敗時會吐出這些。Streamable HTTP 客戶端應該在短暫退避後重試一次。
- **SSE 連線中斷。** TCP RST、代理逾時，或客戶端換網路都會關掉那道串流。客戶端帶著 `Mcp-Session-Id` 與選配的 `last-event-id` 重連以續傳。
- **工作階段撤銷。** 伺服器讓某個工作階段 id 失效；客戶端在下次請求時看到 404。客戶端必須重新握手。
- **時鐘偏移。** 客戶端的資源 TTL 計算與伺服器分歧。客戶端應該把伺服器的時間戳視為權威。

### 什麼時候該繞過 Streamable HTTP

有些企業在自家網路內，把 MCP 伺服器部署在 gRPC 或訊息佇列傳輸之後。這是非標準的 —— MCP 規格並沒有正式定義這些。閘道可以對 MCP 客戶端暴露一個 Streamable HTTP 表面，內部卻使用 gRPC。讓對外的表面保持合規；轉譯由閘道負責。

```figure
tp-transport-handshake
```

## 框架應用

`code/main.py` 用 `http.server`（stdlib）實作了一個最小的 Streamable HTTP 端點。它在 `/mcp` 上處理 POST、GET 與 DELETE，在第一次回應時設上 `Mcp-Session-Id`，驗證 `Origin`，並拒絕來自非白名單來源的請求。這個處理器重用了單元 07 那台筆記伺服器的分派邏輯。

要看的地方有：

- POST 處理器讀取 JSON-RPC 主體、分派，然後寫出一份 JSON 回應（單一回應的變體；SSE 變體在結構上類似）。
- `Origin` 檢查會拒絕預設的 `http://evil.example` 探測，但接受 `http://localhost`。
- 工作階段 id 是隨機的 128 位元十六進位字串；伺服器把每個工作階段的狀態保存在記憶體中。

## 產出交付

這一課產出 `outputs/skill-mcp-transport-migrator.md`。給定一台 HTTP+SSE（舊版）MCP 伺服器，這項技能會產出一份遷移到 Streamable HTTP 的計畫，涵蓋工作階段 id 的連續性、Origin 檢查，以及向後相容的探測支援。

## 練習

1. 跑一次 `code/main.py`。用 `curl` POST 一次 `initialize`，並觀察回應中的 `Mcp-Session-Id` 標頭。再 POST 第二次請求並回敘該標頭，驗證工作階段的連續性。

2. 加上一個開啟 SSE 串流的 GET 處理器。每五秒送出一則 `notifications/progress` 事件。用同一個工作階段 id 重新 GET 來重連，並確認伺服器接受它。

3. 實作 `last-event-id` 的重播邏輯。重連時，把自那個 id 以來產生的所有事件重播一遍。

4. 擴充 `Origin` 驗證以支援萬用字元模式（`https://*.example.com`），並確認它接受 `https://app.example.com` 卻拒絕 `https://evil.example.com.attacker.net`。

5. 從官方登錄中挑一台舊版的 HTTP+SSE 伺服器（有好幾台），勾勒出遷移方案：端點處理、工作階段 id 產生與標頭語意各有什麼改變。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| stdio 傳輸 | 「本機子行程」 | 跑在 stdin／stdout 上、以換行分隔的 JSON-RPC |
| Streamable HTTP | 「那個遠端傳輸」 | 單端點的 POST + GET + 選配 SSE，2025-03-26 版規格 |
| HTTP+SSE | 「舊版」 | 將在 2026 年年中移除的雙端點模型 |
| `Mcp-Session-Id` | 「工作階段標頭」 | 由伺服器指派、客戶端在之後每次請求都回敘的隨機 id |
| `Origin` 白名單 | 「DNS 重繫結防禦」 | 拒絕 Origin 未經核准的請求 |
| 單端點 | 「一個 URL」 | 由 `/mcp` 處理所有工作階段操作的 POST／GET／DELETE |
| `last-event-id` | 「SSE 重播」 | 用來續接中斷串流而不漏事件的標頭 |
| 向後相容探測 | 「新舊偵測」 | 客戶端檢查回應形狀以自動選定傳輸 |
| 長連線 HTTP | 「SSE 串流」 | 伺服器在單一條 TCP 連線上推送數分鐘或數小時的事件 |
| 工作階段撤銷 | 「強制重新初始化」 | 伺服器讓某個工作階段 id 失效；客戶端必須重新握手 |

## 延伸閱讀

- [MCP — Basic transports spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) —— stdio 與 Streamable HTTP 的權威參考
- [MCP — Basic transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) —— 引入 Streamable HTTP 的那個修訂版
- [Cloudflare — MCP transport](https://developers.cloudflare.com/agents/model-context-protocol/transport/) —— Workers 託管的 Streamable HTTP 模式
- [AWS — MCP transport mechanisms](https://builder.aws.com/content/35A0IphCeLvYzly9Sw40G1dVNzc/mcp-transport-mechanisms-stdio-vs-streamable-http) —— 跨部署形狀的比較
- [Atlassian — HTTP+SSE deprecation notice](https://community.atlassian.com/forums/Atlassian-Remote-MCP-Server/HTTP-SSE-Deprecation-Notice/ba-p/3205484) —— 一個具體的遷移期限案例
