# 生產環境中的 MCP 認證 —— 登錄註冊、JWKS 刷新、受眾釘選的 token

> 單元 16 在記憶體中把 OAuth 2.1 的狀態機立了起來。到了 2026 年，你出貨給真實組織的每一台 MCP 伺服器，背後都坐著生產級的認證：一套能擴展到無界客戶端族群的登錄註冊機制（優先用 Client ID Metadata Document，動態客戶端註冊作為向後相容的退路）、授權伺服器的中繼資料探索（RFC 8414「或」OpenID Connect Discovery）、一套不會在凌晨三點把 token 驗證搞壞的 JWKS 快取刷新，以及能拒絕跨資源重放的受眾釘選 token。這一課會用三個角色 —— 一台授權伺服器、一台資源伺服器（就是那台 MCP 伺服器），以及一個客戶端 —— 把整個表面建模出來，好讓你能從探索一路追到一次通過驗證的工具呼叫。
>
> **規格註記（2025-11-25）：** 2025 年 11 月的 MCP 授權規格，把動態客戶端註冊從 `SHOULD` 降級為 `MAY`，並讓 **Client ID Metadata Document（CIMD）** 成為建議的預設登錄註冊機制。這一課會依規格的優先順序把兩者都教一遍，而程式碼在走查時保留 DCR，因為它在單一行程內完全自足。

**類型：** 實作
**程式語言：** Python (stdlib)
**先修單元：** 階段 13 · 16（OAuth 2.1 狀態機）、階段 13 · 17（閘道）
**時間：** 約 90 分鐘

## 學習目標

- 透過 RFC 8414 中繼資料探索一台授權伺服器，並驗證那份契約。
- 實作 RFC 7591 的動態客戶端註冊，好讓 MCP 客戶端不必管理員介入就能登錄註冊。
- 依排程快取並刷新 JWKS 金鑰，讓簽章驗證撐得過金鑰輪替。
- 用 RFC 8707 的資源指示子把 token 釘在單一個 MCP 資源上，並拒絕混淆代理人式的重用。
- 把三個角色乾淨地分開 —— 授權伺服器、資源伺服器、客戶端 —— 讓每一個只執行屬於自己的檢查。
- 讀懂一張 IdP 能力矩陣，並在該 IdP 滿足不了 MCP 認證 profile 時拒絕部署。

## 問題所在

單元 16 的模擬器在記憶體中跑 OAuth 2.1。生產環境有三道純記憶體模擬器看不見的維運缺口。

第一道缺口是登錄註冊。一個真實的組織跑著數百台 MCP 伺服器與數千個 MCP 客戶端。維運人員不會把每一位 Cursor 使用者都手動註冊成一個 OAuth 客戶端。2025-11-25 版規格給了客戶端一套解法的優先順序：如果你有預先註冊的 `client_id` 就用它，否則用 **Client ID Metadata Document**（客戶端用一個自己掌控的 HTTPS URL 來標識自己，由授權伺服器「拉取」那份中繼資料），再否則退回 **RFC 7591 的動態客戶端註冊**（客戶端「推送」一次 `POST /register` 並當場收到一個 `client_id`），再不然就詢問使用者。CIMD 是建議的預設，因為它徹底免除了逐伺服器的註冊，同時保有以 DNS 為根的信任模型；DCR 則為了向後相容而保留。兩者都從授權伺服器的中繼資料中探索自己的進入點：CIMD 看 `client_id_metadata_document_supported`，DCR 看 `registration_endpoint`。

第二道缺口是金鑰輪替。JWT 驗證仰賴授權伺服器的簽章金鑰，它們以 JSON Web Key Set（JWKS）的形式發布。授權伺服器會依排程輪替這些金鑰（通常每小時一次，在事故應變時可能更快）。一台在開機時只抓一次 JWKS 的 MCP 伺服器，在輪替視窗到來之前都驗得很好 —— 然後每一次請求都失敗，直到重啟為止。生產環境會把 JWKS 接成一個帶快取的值，配上一個在前一批金鑰過期之前就覆寫快取的刷新工作，另外還有一條快取未命中時的退路抓取，用來應付「一個由比快取更新的金鑰簽出的 token」抵達的情況。

第三道缺口是受眾繫結。單元 16 引介了 RFC 8707 的資源指示子。在生產環境中，那個指示子變成每一次請求上的一項硬性 claim 檢查。MCP 伺服器拿 `token.aud` 去對照自己那個標準資源 URL，不符就以 HTTP 401 拒絕。這是唯一能防禦下述情況的手段：一台上游的 MCP 伺服器（或一個持有本該給某台伺服器的 token 的惡意客戶端），把那個 token 重放到同一個信任網格中的另一台伺服器上。

這一課會把每一道缺口對映到這片表面上的一塊具體零件。中繼資料文件是一個 HTTP 端點。JWKS 快取刷新是一個排程工作加上一份鍵值快取。JWT 驗證是資源伺服器在分派任何工具之前會跑的一段常式。把三個角色分開，每一個就只執行自己該管的檢查：授權伺服器負責簽發與輪替金鑰，資源伺服器負責快取與驗證，客戶端負責探索與登錄註冊。

## 核心概念

### RFC 8414 —— OAuth 授權伺服器中繼資料

位於 `/.well-known/oauth-authorization-server` 的一份文件，描述了客戶端需要的一切：

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/authorize",
  "token_endpoint": "https://auth.example.com/token",
  "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
  "registration_endpoint": "https://auth.example.com/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": ["mcp:tools.read", "mcp:tools.invoke"],
  "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"]
}
```

拿到一個 MCP 資源 URL 的客戶端，會把探索串起來：先由 RFC 9728 的 `oauth-protected-resource`（資源伺服器那份文件）點名 issuer，再由 `oauth-authorization-server`（本 RFC）點名每一個端點。客戶端永遠不會把授權 URL 寫死。

在信任某個 IdP 能承接 MCP 之前，你要驗證的那份契約是：

- `code_challenge_methods_supported` 含有 `S256`（RFC 7636 的 PKCE）。規格說得很明白：如果這個欄位**缺席**，那台授權伺服器就不支援 PKCE，客戶端**必須**拒絕繼續下去。
- `grant_types_supported` 含有 `authorization_code`，並排除 `password` 與 `implicit`。
- 至少公告了一條登錄註冊路徑：`client_id_metadata_document_supported: true`（CIMD，優先）**或** `registration_endpoint`（RFC 7591 DCR，退路）。任一者都滿足契約；你不再硬性要求 DCR。
- 就 OAuth 2.1 而言，`response_types_supported` 恰好是 `["code"]`。

如果 `S256` 缺席，MCP 伺服器就拒絕對這個 IdP 部署 —— PKCE 沒有降級模式。如果「兩條」登錄註冊路徑都沒公告，而你又沒有預先註冊的 `client_id`，那你也沒辦法登錄註冊；此時錯的是部署清單，不是程式碼。

### RFC 9728（回顧）—— 受保護資源中繼資料

單元 16 談過 RFC 9728。在生產環境中的差異在於：這份文件是客戶端唯一會去查找「「這台」MCP 伺服器所信任的授權伺服器」的地方。單一台 MCP 伺服器可能接受來自多個 IdP 的 token（一個給員工、一個給合作夥伴）。RFC 9728 宣告的是那個集合；RFC 8414 則記載每個 IdP 各自支援什麼。

```json
{
  "resource": "https://notes.example.com",
  "authorization_servers": ["https://auth.example.com", "https://partners.example.com"],
  "scopes_supported": ["mcp:tools.invoke"],
  "bearer_methods_supported": ["header"],
  "resource_documentation": "https://notes.example.com/docs"
}
```

### Client ID Metadata Document（建議的預設）

CIMD 把註冊從「推送」翻轉成「拉取」。客戶端不再請授權伺服器鑄造一個 `client_id`，而是「拿」一個自己掌控的 HTTPS URL「當作」它的 `client_id`。那個 URL 會解析到一份 JSON 中繼資料文件；授權伺服器在 OAuth 流程中依需要去抓取它。信任以 DNS 為根：如果伺服器維運方信任 `app.example.com`，它就信任從 `https://app.example.com/client.json` 提供出來的那個客戶端。不必來回註冊、沒有會被耗盡的 `client_id` 命名空間、也沒有逐伺服器的狀態要同步。

客戶端託管的那份中繼資料文件：

```json
{
  "client_id": "https://app.example.com/oauth/client.json",
  "client_name": "Example MCP Client",
  "client_uri": "https://app.example.com",
  "redirect_uris": ["http://127.0.0.1:7333/callback", "http://localhost:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

文件中的 `client_id` 值**必須**等於它被提供出來的那個 URL（授權伺服器會驗證這件事；不符就拒絕）。授權伺服器則在它的 RFC 8414 中繼資料中以 `client_id_metadata_document_supported: true` 公告支援。

規格對兩件安全事實講得毫不含糊：

- **SSRF。** 授權伺服器會去抓取一個由攻擊者提供的 URL。它必須防禦伺服器端請求偽造（不得抓取內部／管理端點）。
- **localhost 冒充。** 單靠 CIMD 擋不住一個本機攻擊者宣稱自己是某個正當客戶端的中繼資料 URL，並繫結任意的 `localhost` 轉址。授權伺服器**必須**在同意畫面上清楚顯示轉址 URI 的主機名稱，並在只有 `localhost` 轉址時**應該**提出警告。

因為 CIMD 不需要伺服器端狀態，所以不像 DCR 那樣得立一個註冊器。客戶端這一側是唯讀的：把你的中繼資料文件從一個靜態 HTTPS 端點提供出去，讓授權伺服器自己來拉。

### RFC 7591 —— 動態客戶端註冊（退路／向後相容）

DCR 現在是 `MAY`，保留下來是為了與 2025-11-25 之前的部署，以及尚未支援 CIMD 的 IdP 相容。少了它（而且也沒有 CIMD 或預先註冊），每一個 MCP 客戶端（Cursor、Claude Desktop、一個客製代理）都得與 IdP 管理員做一次帶外的往來。有了 DCR，客戶端就 POST：

```json
POST /register
Content-Type: application/json

{
  "redirect_uris": ["http://127.0.0.1:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none",
  "scope": "mcp:tools.invoke",
  "client_name": "Cursor",
  "software_id": "com.cursor.cursor",
  "software_version": "0.42.0"
}
```

伺服器以一個 `client_id` 與一個供日後更新用的 `registration_access_token` 回應：

```json
{
  "client_id": "c_3e7f1a",
  "client_id_issued_at": 1769472000,
  "redirect_uris": ["http://127.0.0.1:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "registration_access_token": "regt_b2...",
  "registration_client_uri": "https://auth.example.com/register/c_3e7f1a"
}
```

對跑在使用者裝置上的 MCP 客戶端而言，`token_endpoint_auth_method: none` 是正確的預設。它們只拿到一個 `client_id` —— 沒有 `client_secret` 可被外洩。公開客戶端所需要的持有證明，由 PKCE 提供。

三個生產環境的坑：

- 註冊端點必須依來源 IP 做速率限制。少了它，敵對行為者就能腳本化地灌進數百萬筆假註冊，把 `client_id` 命名空間耗盡。要在註冊器處理請求之前先跑一次速率限制檢查。
- `software_statement`（一個為客戶端背書的簽章 JWT）在某些企業 IdP 上是必要的。本課的模擬版跳過了它；生產環境則要接上一道驗證步驟，拒絕任何來自非 localhost 轉址 URI 的未簽章註冊。
- `registration_access_token` 必須以雜湊形式儲存，不能存明文。這個 token 一旦被竊，攻擊者就能改寫該客戶端的轉址 URI。

### RFC 8707（回顧）—— 資源指示子

單元 16 確立了它的形狀。生產環境的規則是：每一次 token 請求都帶上 `resource=<canonical-mcp-url>`，而 MCP 伺服器在每一次呼叫上都驗證 `token.aud` 與自己的資源 URL 相符。那個標準 URI 是這台伺服器「最具體」的識別字：scheme 與主機用小寫、不帶 fragment，慣例上也不帶尾斜線。路徑元件**並不會**依規則被剝掉 —— 當需要它來指認個別的 MCP 伺服器時，規格會把它留著。`https://mcp.example.com`、`https://mcp.example.com/mcp`、`https://mcp.example.com:8443` 與 `https://mcp.example.com/server/mcp` 全都是合法的標準 URI。每台伺服器挑一個，並把 `aud` 精確釘在它上面。（本課的模擬版為求簡潔，使用像 `https://notes.example.com` 這樣的裸主機受眾；若一個部署在同一個 origin 底下同時託管多台 MCP 伺服器，就會以路徑來區分它們。）

### RFC 7636（回顧）—— PKCE

在 OAuth 2.1 中 PKCE 是強制的。本課的授權碼流程一律帶著 `code_challenge` 與 `code_verifier`。伺服器會拒絕任何沒有 verifier、或 verifier 雜湊後與所存 challenge 不符的 token 請求。

### MCP 規格 2025-11-25 的認證 profile

MCP 規格（2025-11-25）對一台 MCP 伺服器的授權層必須做到什麼，講得很精確：

- 實作 RFC 9728 的受保護資源中繼資料，並透過 401 上的 `WWW-Authenticate: Bearer resource_metadata="..."` 標頭**或**眾所周知的 URI `/.well-known/oauth-protected-resource` 提供它的位置（SEP-985 讓那個標頭變成選配，並提供 well-known 作為退路）。中繼資料的 `authorization_servers` 欄位**必須**至少點名一台伺服器。
- 只在**每一次**請求上透過 `Authorization: Bearer ...` 接受 token —— 絕不放在查詢字串中，也絕不只在工作階段開始時驗證一次。
- 每次請求都驗證 `aud`、`iss`、`exp` 與必要的範圍。伺服器**必須**驗證該 token 是專門為它簽發的（受眾）；缺席或不符的 `aud` 一律拒絕，絕不視為萬用。
- 在 401／403 時，回傳帶 `error=...`、`resource_metadata="<PRM-URL>"` 參數（那份中繼資料文件的 URL，「不是」裸資源）的 `WWW-Authenticate: Bearer`，並在 `insufficient_scope`（403）時附上 `scope="..."`。注意：那個參數叫 `resource_metadata`，是一個探索指標 —— 這個 challenge 裡沒有 `resource` 參數。
- 授權伺服器的探索**同時**接受 RFC 8414 的 OAuth 中繼資料**或** OpenID Connect Discovery 1.0；客戶端必須依優先順序把兩個 well-known 後綴都試過。
- 防禦**混合攻擊（mix-up）**是客戶端（而非伺服器）的責任：它在轉址之前記下預期的 `issuer`，並在兌換授權碼之前驗證授權回應中的 `iss` 參數（RFC 9207）。光靠 PKCE 擋不住混合攻擊，因為客戶端會把自己的 `code_verifier` 交給任何它被導向的 token 端點。

OAuth 2.1 草案是基材；RFC 8414/7591/8707/9728/9207 + RFC 7636 + CIMD 是表面；MCP 規格則是那份 profile。

### IdP 能力矩陣

不是每個 IdP 都支援完整的 MCP profile。下表記載的是截至 2025-11-25 版規格時的事實性能力陳述。它是一道「部署閘門」，不是一份推薦名單。

CIMD 隨 2025-11-25 版規格出貨，而底層的 OAuth 草案遲至 2025 年 10 月才被採納，所以廠商支援仍在陸續到位 —— 請把下表的「CIMD」欄視為「目前的狀況，請在你自己的租戶中驗證」，而不是一項永久的陳述。

| IdP 類別 | AS 中繼資料（8414/OIDC） | CIMD | RFC 7591 DCR | RFC 8707 resource | RFC 7636 S256 PKCE | 備註 |
|---|---|---|---|---|---|---|
| 自架（Keycloak） | 有 | 陸續到位 | 有 | 有（24.x 起） | 有 | 本課用來對照 MCP profile 的參考 IdP；DCR 路徑端到端完整，CIMD 正跟進新規格。 |
| 企業 SSO（Microsoft Entra ID） | 有 | 陸續到位 | 有（進階方案） | 有 | 有 | DCR 是否可用依租戶方案而異；部署前請在目標租戶中確認。 |
| 企業 SSO（Okta） | 有 | 陸續到位 | 有（Okta CIC／Auth0） | 有 | 有 | DCR 在 Auth0（現為 Okta CIC）上可用；傳統 Okta 組織則需管理員預先註冊。 |
| 社群登入 IdP（泛指） | 不一定 | 無 | 少有 | 少有 | 有 | 多數社群 IdP 把客戶端當成靜態合作夥伴；沒有自助登錄註冊。只拿它當身分來源，並在其上疊你自己那台懂 MCP 的授權伺服器。 |
| 自製／土砲 | 看情況 | 看情況 | 看情況 | 看情況 | 看情況 | 如果你要自己出貨，就把整份 profile 都做齊，並優先採用 CIMD。跳過 PKCE 或受眾繫結，就等於毀了 MCP 的認證契約。 |

部署清單的拒絕規則：如果選定的 IdP 沒有在 `code_challenge_methods_supported` 中列出 `S256`，MCP 伺服器就拒絕啟動 —— PKCE 沒有降級模式。登錄註冊則是一道較軟的閘門：你需要「一條」可行的路徑（預先註冊的 `client_id`、`client_id_metadata_document_supported: true`，或一個 `registration_endpoint`）。單單缺少 DCR 已不再是拒絕的觸發條件，因為 CIMD 或預先註冊都能補上。

### JWKS 刷新模式（在 AS 端輪替，在資源伺服器端刷新）

把兩個動詞分清楚，因為把它們混為一談是一個真實的生產 bug：

- **輪替（Rotate）**是「授權伺服器」做的事：鑄造一把新的簽章金鑰、把它發布到 JWKS，稍後再讓舊的退役。資源伺服器完全不參與，也做不到 —— 它並不持有 IdP 的私鑰。
- **刷新（Refresh）**是「資源伺服器」做的事：重新 `GET` 已發布的 JWKS 進自己的快取。這是資源伺服器唯一會做的 JWKS 動作。

生產環境的失敗模式是快取過期。用一個排程刷新工作加一份鍵值快取來解決。資源伺服器跑一個工作（cron、計時器，你的執行環境提供什麼都行），依固定間隔抓取 `<issuer>/.well-known/jwks.json` 並覆寫 `cache[issuer] = {keys, fetched_at}`。驗證器從那份快取讀取。當某個 token 的 `kid` 在快取中找不到時，就觸發**一次**同步刷新作為退路，然後重新檢查。這一招同時處理了兩種情況：排程刷新，以及「由一把全新金鑰簽出的 token，在下一次排程刷新之前就抵達」的金鑰重疊視窗。

那條退路**必須是重新抓取，絕不能是輪替**。如果你把快取未命中那條路徑接成「輪替並鑄造新金鑰」，兩件事會壞掉：(1) 鑄造一把新金鑰所產生的 `kid`「依然」對不上那個 token，所以查找還是失敗；(2) 一個灑出大量隨機 `kid` token 的攻擊者，會逼出一連串無界的金鑰建立 —— 一場自作自受的 DoS。重新抓取是冪等的，所以一個假 `kid` 最多只花掉一次白費的抓取。

那份快取的形狀：

```json
{
  "https://auth.example.com": {
    "keys": [
      {"kid": "k_2026_03", "kty": "RSA", "n": "...", "e": "AQAB", "alg": "RS256", "use": "sig"},
      {"kid": "k_2026_04", "kty": "RSA", "n": "...", "e": "AQAB", "alg": "RS256", "use": "sig"}
    ],
    "fetched_at": 1772668800
  }
}
```

同時存在兩把金鑰才是穩定狀態。授權伺服器輪替的方式，是先引入下一把金鑰（`k_2026_04`）再讓前一把（`k_2026_03`）退役，好讓以舊金鑰簽發的 token 在過期之前仍然有效。快取持有的是聯集；驗證器則依 `kid` 挑選。

### 那段驗證常式

MCP 伺服器在分派任何工具之前都會跑一次驗證。`code/main.py` 用的形狀是：

```python
result = server.validate(bearer_token, required_scope="mcp:tools.invoke")
if not result["valid"]:
    return {"status": result["status"], "WWW-Authenticate": result["www_authenticate"]}
```

`validate` 會解碼那個 JWT、從 JWKS 快取中解析出簽章金鑰（未命中時刷新一次）、驗證簽章，接著檢查 `iss` 是否在白名單內、`aud` 是否與這台伺服器的標準資源相符、`exp`，以及所需的範圍 —— 並在第一個失敗處回傳一個 `WWW-Authenticate` challenge。把它保持成資源伺服器上的單一段常式，就意味著每一個進入點（每一次工具呼叫、每一種傳輸）都走同樣那些檢查；沒有任何一條路徑能在未驗證的情況下抵達某個工具。

### 受眾重放的逐步走查（存取 token 的權限限縮）

伺服器 A（`notes.example.com`）與伺服器 B（`tasks.example.com`）都對同一台授權伺服器註冊。伺服器 A 被入侵了。攻擊者拿走使用者的 notes token，並把它重放到伺服器 B。

伺服器 B 的驗證器：

1. 解碼 JWT，依 `kid` 抓取 JWKS，驗證簽章。
2. 拿 `iss` 對照它那份受保護資源中繼資料的 `authorization_servers`。（通過 —— 同一個 IdP。）
3. 檢查 `aud == "https://tasks.example.com"`。（失敗 —— 該 token 的 `aud` 是 `https://notes.example.com`。）
4. 回傳 401，帶 `WWW-Authenticate: Bearer error="invalid_token", error_description="audience mismatch", resource_metadata="https://tasks.example.com/.well-known/oauth-protected-resource"`。

在協定層面上，受眾 claim 是防禦這種攻擊的唯一手段。為了效能而跳過它，是最常見的生產錯誤；驗證器必須在每一次請求上跑，而不是只在工作階段開始時跑。規格把這件事稱為**存取 token 的權限限縮**：MCP 伺服器 `MUST` 拒絕任何未在受眾中點名自己的 token。

> **名詞註記。** 規格把「混淆代理人」這個詞保留給一個相關但不同的問題：一台 MCP 伺服器扮演通往第三方 API 的 OAuth **代理**，使用一個靜態的 client ID，並在未取得逐客戶端使用者同意的情況下轉發 token。受眾繫結修的是上面那個重放；混淆代理人的解法則是逐客戶端同意，**再加上**絕不把入站的 token 直傳給上游 API（MCP 伺服器 `MUST` 自己另外取得一個上游 token）。

### 混合攻擊（一種伺服器提供不了的客戶端側防禦）

一個客戶端一生中會跟許多授權伺服器打交道。惡意的 AS 可以試圖讓客戶端把一台誠實 AS 的授權碼，拿到攻擊者的 token 端點去兌換。受眾繫結在這裡幫不上忙 —— 這場攻擊發生在任何 token 存在之前。防禦住在客戶端（RFC 9207）：

1. 轉址之前，客戶端從已驗證的 AS 中繼資料中記下預期的 `issuer`。
2. 收到授權回應時，客戶端在把授權碼送去任何地方之前，先拿回傳的 `iss` 參數與那個記下的 issuer 比對（單純的字串比對，不做正規化）。
3. 不符（或當 AS 已公告 `authorization_response_iss_parameter_supported` 卻沒有 `iss`）→ 拒絕，而且連 `error` 欄位都不要顯示。

光靠 PKCE 擋不住混合攻擊，因為客戶端會把自己的 `code_verifier` 交給任何它被導向的 token 端點。這正是規格為什麼要把 issuer 與 PKCE verifier、`state` 一起逐請求記下來的原因。

### 失敗模式

- **JWKS 過期。** AS 輪替金鑰之後，驗證器開始拒絕有效的 token。解法是上面那套「cron 刷新 + 快取未命中重抓」的模式。永遠不要在沒有刷新工作的情況下快取 JWKS。
- **拿輪替當退路。** 把快取未命中那條路徑接成「輪替並鑄造」而非重新抓取，是一個真實的 bug：它永遠生不出那個缺失的 `kid`，而且會把攻擊者可控的 `kid` 值變成一場金鑰建立 DoS。那條退路必須是冪等的 `refresh-jwks`。
- **缺少 `aud` claim。** 有些 IdP 在 token 請求中沒有 `resource` 時，預設就不放 `aud`。驗證器必須拒絕缺 `aud` 的 token，而不是把缺席當成萬用。
- **因未檢查 `iss` 而中招的混合攻擊。** 一個沒有拿 RFC 9207 授權回應中的 `iss` 參數，去對照它在轉址前記下的 issuer 做驗證的客戶端，可能會被導去把一台誠實 AS 的授權碼，拿到攻擊者的 token 端點兌換。這是客戶端側的失敗；資源伺服器補償不了。
- **範圍升級的競態。** 同一位使用者的兩個並行提升流程可能都成功，並產出兩個範圍不同的存取 token。驗證器必須使用請求上呈上來的那個 token，而不是去查「該使用者當前的範圍」—— 那會造出一個 TOCTOU 視窗。
- **註冊 token 遭竊。** 洩漏的 `registration_access_token` 讓攻擊者能改寫轉址 URI。這些要以雜湊形式靜態儲存；每次更新都要求客戶端出示明文；有疑慮就輪替。
- **`iss` 沒有釘住。** 一個什麼 `iss` 都接受的驗證器，會讓攻擊者立起自己的授權伺服器、為目標受眾註冊一個客戶端，然後簽發 token。受保護資源中繼資料的 `authorization_servers` 清單就是那份白名單；請把它強制執行。

```figure
t3-jwks-rotate
```

## 框架應用

`code/main.py` 用 stdlib Python 與三個角色 —— `AuthorizationServer`、`ResourceServer` 與 `Client` —— 走過完整的生產流程。流程是：

1. 授權伺服器在 `/.well-known/oauth-authorization-server` 發布 RFC 8414 中繼資料。
2. MCP 客戶端呼叫那個中繼資料端點，檢查它的登錄註冊選項（CIMD 看 `client_id_metadata_document_supported`，DCR 看 `registration_endpoint`）與 `S256` PKCE 支援。
3. 這次走查採 DCR 退路那條路徑：客戶端 POST 到 `/register`（RFC 7591）並收到一個 `client_id`。（若是 CIMD 客戶端，則會改為出示自己的 HTTPS `client_id` URL，並跳過這一步。）
4. MCP 客戶端跑受 PKCE 保護的授權碼流程（RFC 7636），並帶上 `resource` 指示子（RFC 8707）。
5. MCP 客戶端帶著 `Authorization: Bearer ...` 對 MCP 伺服器呼叫一個工具。
6. MCP 伺服器跑 `validate`，從 JWKS 快取中解析出簽章金鑰。
7. IdP 輪替一把金鑰；排程刷新把 JWKS 重新拉進快取。
8. 下一次呼叫不必重啟就能對照刷新後的金鑰通過驗證，而先前那個 token 在重疊視窗期間仍然有效。
9. 一次針對另一個 MCP 資源的受眾重放嘗試，會拿到帶 `audience mismatch` 與一個 `resource_metadata` 指標的 401。

這裡的 JWT 用的是搭配共享密鑰的 HS256（好讓本課只靠 stdlib 就能跑）。生產環境會用 RS256 或 EdDSA 搭配上面那套 JWKS 模式；除此之外驗證邏輯完全相同。由於 IdP 與資源伺服器活在同一個行程中，`refresh_jwks` 直接讀取授權伺服器的金鑰清單；在真實線路上，它會是一次對 `jwks_uri` 的 HTTP `GET`。

## 產出交付

這一課產出 `outputs/skill-mcp-auth.md`。給定一份 MCP 伺服器設定與一組 IdP 能力，這項技能會吐出該立起來的認證表面 —— 受保護資源中繼資料、該採用的登錄註冊路徑（CIMD、預先註冊，或 DCR 退路）、JWKS 刷新排程、範圍對映，以及當該 IdP 不支援完整 RFC profile 時該套用的拒絕規則。

## 練習

1. 跑一次 `code/main.py`。追蹤那條流程。注意 IdP 在第 6 步輪替了一把金鑰，排程的 `refresh_jwks` 重新拉取了已發布的金鑰集，而舊 token（重疊視窗）與新 token 都不必重啟就能通過驗證。

2. 在受保護資源中繼資料的 `authorization_servers` 清單中加入一個新的 IdP。簽發一個由該新 IdP 簽章的 token，確認驗證器接受它。再簽發一個由未列名 IdP 簽章的 token，確認驗證器以 `WWW-Authenticate: Bearer error="invalid_token", error_description="iss not allowed"` 拒絕它。

3. 在 `register_client` 中加上一道會在註冊器接受請求之前執行的速率限制檢查。用一個以 IP 為鍵、存在小 dict 裡的逐來源 IP 權杖桶。

4. 讀 RFC 7591，找出兩個本課 `/register` 處理器沒有驗證的欄位。把驗證加上去。（提示：`software_statement` 與 `redirect_uris` 的 URI scheme。）

5. 加上一條 Client ID Metadata Document 路徑。提供一份 `client.json`，其 `client_id` 等於它自己的 URL，並讓授權伺服器去抓取並驗證它（若 `client_id` ≠ URL 就拒絕）。確認一個 CIMD 客戶端不必呼叫 `register_client` 就能完成登錄註冊。

6. 證明那個 DoS 的修法。送給驗證器一個帶隨機 `kid` 的 token，確認 `refresh_jwks` 最多只跑一次，而授權伺服器的金鑰數量沒有增加。接著刻意把那條退路改接成「輪替並鑄造」，看著金鑰數量隨每個假 token 往上爬 —— 之後再把重新抓取改回來。

7. 實作混合攻擊那一節所述、客戶端側的 RFC 9207 `iss` 檢查：在授權請求之前記下預期的 issuer，然後拒絕 `iss` 不符的授權回應。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| ASM | 「OAuth 中繼資料文件」 | RFC 8414 的 `/.well-known/oauth-authorization-server` JSON |
| CIMD | 「客戶端中繼資料 URL」 | Client ID Metadata Document —— 一個當作 `client_id` 用的 HTTPS URL；由 AS 去拉那份 JSON。自 2025-11-25 起為建議的預設 |
| DCR | 「自助式客戶端註冊」 | RFC 7591 的 `POST /register` 流程；在 2025-11-25 被降級為 `MAY` 退路 |
| JWKS | 「用來驗證 JWT 的公鑰」 | JSON Web Key Set，從 `jwks_uri` 抓取，以 `kid` 索引 |
| 輪替對刷新 | 「更新金鑰」 | 「輪替」= AS 鑄造／退役簽章金鑰；「刷新」= 資源伺服器重新抓取已發布的金鑰集。資源伺服器永遠只做刷新 |
| 資源指示子 | 「受眾參數」 | RFC 8707 的 `resource` 參數，把 token 釘到單一台伺服器 |
| `aud` claim | 「受眾」 | 驗證器拿去與標準資源 URL 比對的那個 JWT claim |
| 受眾重放 | 「token 重放」 | 為伺服器 A 簽發的 token 被出示給伺服器 B；靠受眾驗證防禦（規格稱：存取 token 的權限限縮） |
| 混淆代理人 | 「代理端的 token 誤用」 | 一台使用靜態 client ID 的 MCP 代理，在未取得逐客戶端同意下轉發 token；與受眾重放不同 |
| 混合攻擊 | 「跑錯 token 端點」 | 客戶端被導去在攻擊者的端點兌換一台誠實 AS 的授權碼；由客戶端側透過 RFC 9207 的 `iss` 防禦 |
| `iss` 白名單 | 「受信任的授權伺服器」 | 受保護資源中繼資料的 `authorization_servers` 所點名的那個集合 |
| `resource_metadata` | 「上哪找那份 PRM 文件」 | 401／403 上用來點名 RFC 9728 中繼資料 URL 的 `WWW-Authenticate` 參數 |
| 公開客戶端 | 「原生或瀏覽器客戶端」 | 沒有 `client_secret` 的 OAuth 客戶端；由 PKCE 補償 |
| `WWW-Authenticate` | 「401／403 回應標頭」 | 承載驅動客戶端復原的 `Bearer error=...` 指令 |

## 延伸閱讀

- [MCP — Authorization spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) —— 本課所實作的 MCP 認證 profile
- [MCP blog — One Year of MCP: November 2025 Spec Release](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) —— 2025-11-25 改了什麼（CIMD、XAA、DCR 降級）
- [Aaron Parecki — Client Registration in the November 2025 MCP Authorization Spec](https://aaronparecki.com/2025/11/25/1/mcp-authorization-spec-update) —— CIMD 優先於 DCR 的理由
- [OAuth Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document-00)](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-client-id-metadata-document-00) —— CIMD
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://datatracker.ietf.org/doc/html/rfc8414) —— 探索契約
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://datatracker.ietf.org/doc/html/rfc7591) —— DCR（退路路徑）
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://datatracker.ietf.org/doc/html/rfc7636) —— 公開客戶端的持有證明
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707) —— 受眾釘選
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728) —— 資源伺服器的探索
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://datatracker.ietf.org/doc/html/rfc9207) —— 防禦混合攻擊的那個 `iss` 參數
- [OAuth 2.1 draft](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1) —— 整併過的 OAuth 基材
