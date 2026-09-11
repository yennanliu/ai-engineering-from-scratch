# 生產環境的 MCP 認證：綁定簽發者的註冊與權杖

> 單元 16 建了 OAuth 2.1 的狀態機。這一課為 MCP 2026-07-28 強化它的生產邊界：Client ID Metadata Document 優先、已棄用的動態註冊只做相容、驗證授權回應的簽發者、以簽發者為鍵的客戶端憑證、JWKS 刷新，以及在每一則無狀態請求上釘住受眾的權杖。
>
> **規格註記（2026-07-28）：** 動態客戶端註冊已被棄用，改採 Client ID Metadata Document。DCR 仍是一種相容機制。使用它時，客戶端要宣告正確的 `application_type`。客戶端會驗證出現的 RFC 9207 `iss` 值，而且絕不跨授權伺服器簽發者重用憑證。

**類型：** 實作
**程式語言：** Python（標準函式庫）
**先修單元：** 階段 13 · 16（OAuth 2.1 狀態機）、階段 13 · 17（閘道）
**時間：** 約 90 分鐘

## 學習目標

- 透過 RFC 8414 中繼資料發現授權伺服器，並驗證那份契約。
- 用 Client ID Metadata Document 註冊，並把已棄用的 DCR 隔離成退路。
- 驗證 RFC 9207 `iss`、以授權伺服器簽發者為鍵存放註冊資料，並以簽發者加資源為鍵存放綁定資源的權杖。
- 依排程快取並刷新 JWKS 金鑰，讓簽章驗證能撐過金鑰輪替。
- 用 RFC 8707 資源指示器把權杖釘在單一個 MCP 資源上，並拒絕混淆代理式的重用。
- 在 JWT 驗證與權杖自省之間做選擇、定義撤銷的新鮮度，並在身分相依元件不可用時安全地失敗。
- 讓授權伺服器、資源伺服器與客戶端各自分離，各自只執行屬於自己的檢查。
- 依部署檢查表稽核一台授權伺服器，並拒絕不安全的註冊或權杖重用。

## 問題所在

單元 16 的模擬器是在記憶體裡跑 OAuth 2.1。生產環境有三道只在記憶體裡跑看不到的運維缺口。

第一道缺口是註冊與憑證隔離。真實的組織可能跑上百台 MCP 伺服器與上千個 MCP 客戶端。2026-07-28 修訂版偏好 **Client ID Metadata Document**：客戶端拿一個自己控制、帶路徑的 HTTPS URL 當識別碼，由授權伺服器去拉那份中繼資料。RFC 7591 動態註冊只以一條已棄用的相容路徑留著。當 DCR 無可避免時，那則請求要宣告正確的 `application_type`。客戶端把註冊資料存在授權伺服器簽發者底下，把存取權杖存在 `(issuer, resource)` 這個組合底下。簽發者換了就代表要重新註冊，資源不同就代表要一個另外綁受眾的權杖。

第二道缺口是金鑰輪替。JWT 驗證仰賴授權伺服器的簽章金鑰，它們以 JSON Web Key Set（JWKS）形式發布。授權伺服器會依排程輪替它們（常常是每小時，事故應變時可能更快）。一台只在開機時抓一次 JWKS 的 MCP 伺服器，在輪替窗口之前都驗得好好的 —— 然後每一則請求都會失敗，直到重啟為止。生產環境會把 JWKS 接成一個帶刷新工作的快取值，在前一批金鑰過期之前覆蓋掉快取，再加上一次快取未命中時的補抓，用來處理「權杖是用比快取更新的金鑰簽的」這種情況。

第三道缺口是受眾綁定。單元 16 介紹了 RFC 8707 資源指示器。在生產環境裡，那個指示器會變成每一則請求上一道硬性的宣告檢查。MCP 伺服器拿 `token.aud` 去比對自己的標準資源 URL，不符就以 HTTP 401 拒絕。這是唯一能防止上游 MCP 伺服器（或持有某台伺服器專用權杖的惡意客戶端），把那個權杖重播到同一信任網格中另一台伺服器的防禦。

這一課把每一道缺口對應到介面上一塊具體的東西。中繼資料文件是一個 HTTP 端點。JWKS 快取刷新是一個排程工作加上一個鍵值快取。JWT 驗證是資源伺服器在分派任何工具之前跑的一段常式。讓三個角色保持分離，各自只執行自己擁有的檢查：授權伺服器負責簽發與輪替金鑰，資源伺服器負責快取與驗證，客戶端負責發現與註冊。

## 範圍：單元 16 之後的生產執行

[單元 16：用 OAuth 2.1 保護 MCP](../../16-mcp-security-oauth-2-1/docs/en.md) 掌管授權碼狀態機、PKCE、受保護資源發現、資源指示器與範圍決策。這一課不會再定義第二套 OAuth 流程。它從那些契約已經存在之後開始，追問一台已部署的資源伺服器，如何在金鑰輪替、不透明權杖驗證、撤銷、相依元件失效、上線與事故應變的過程中，持續執行那些契約。

生產邊界更窄，也更偏運維：

- JWT 路徑在每一則請求上驗證固定的簽發者、演算法、簽章金鑰、受眾、時間宣告與範圍，同時安全地刷新 JWKS。
- 不透明權杖路徑呼叫簽發者已認證的自省端點，並驗證回傳的 active 狀態、受眾或資源、到期、主體與範圍。
- 撤銷政策定義一份憑證必須多快失效，以及哪個快取可以延遲那個事實。
- 失敗政策決定當發現、JWKS、自省或撤銷基礎設施不可用時會發生什麼。
- 證據記下是哪份簽發者中繼資料、哪組金鑰或哪則自省回應、哪些權杖宣告、哪個政策版本與哪個拒絕理由造就了那個結果 —— 而且不存下權杖本身。

這個區分讓兩課可以組合。單元 16 證明流程成立。單元 18 證明權杖在抵達真實的 MCP 請求路徑之後，仍然值得信任，或是被拒絕。

## 核心概念

### RFC 8414 —— OAuth 授權伺服器中繼資料

放在 `/.well-known/oauth-authorization-server` 的文件，描述了客戶端需要的一切：

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/authorize",
  "token_endpoint": "https://auth.example.com/token",
  "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
  "client_id_metadata_document_supported": true,
  "registration_endpoint": "https://auth.example.com/register",
  "authorization_response_iss_parameter_supported": true,
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": ["mcp:tools.read", "mcp:tools.invoke"],
  "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"]
}
```

拿到 MCP 資源 URL 的客戶端會串起發現流程：RFC 9728 的 `oauth-protected-resource`（資源伺服器那份文件）指出簽發者，然後 `oauth-authorization-server`（本 RFC）指出每一個端點。客戶端永遠不寫死授權 URL。

對於帶路徑的資源識別碼，把 well-known 片段插在那個路徑之前。舉例來說，`https://mcp.example.com/team/server` 的受保護資源中繼資料位在 `https://mcp.example.com/.well-known/oauth-protected-resource/team/server`。把 `/.well-known/...` 接在資源路徑後面是錯的。

在信任某家 IdP 之前要驗證的契約：

- `code_challenge_methods_supported` 包含 `S256`（依 RFC 7636 的 PKCE）。規格講得很明白：如果這個欄位**不存在**，代表授權伺服器不支援 PKCE，客戶端**必須**拒絕繼續。
- `grant_types_supported` 包含 `authorization_code`，並拒絕 `password` 與 `implicit`。
- 至少有一條註冊路徑可用：`client_id_metadata_document_supported: true`（CIMD，優先）、預先註冊的客戶端，或 `registration_endpoint`（已棄用的 RFC 7591 相容路徑）。
- 如果 `authorization_response_iss_parameter_supported` 為 true，客戶端就要求回傳的 RFC 9207 `iss`，並拿它跟重導前記下的簽發者做精確比對。
- 對 OAuth 2.1 而言，`response_types_supported` 恰好是 `["code"]`。

如果少了 `S256`，MCP 伺服器就拒絕對這家 IdP 部署 —— PKCE 沒有降級模式。如果**兩條**註冊路徑都沒公告，而你也沒有預先註冊的 `client_id`，那你同樣無法註冊；錯的是部署清單，不是程式碼。

### RFC 9728（回顧）—— 受保護資源中繼資料

單元 16 講過 RFC 9728。生產環境的差別在於：這份文件是客戶端唯一能查到「**這台** MCP 伺服器信任哪些授權伺服器」的地方。單一台 MCP 伺服器可能接受來自多家 IdP 的權杖（一家給員工，一家給夥伴）。RFC 9728 宣告那個集合；RFC 8414 說明每一家 IdP 支援什麼。

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

CIMD 把註冊從*推*翻轉成*拉*。客戶端不再去請授權伺服器鑄造一個 `client_id`，而是拿一個自己控制的 HTTPS URL **當作** `client_id`。那個 URL 解析出一份 JSON 中繼資料文件；授權伺服器在 OAuth 流程中按需去抓它。信任的根是 DNS：如果伺服器維運方信任 `app.example.com`，它就信任由 `https://app.example.com/client.json` 提供的那個客戶端。不需要註冊往返、不需要一個會被耗盡的 `client_id` 命名空間，也不需要為每台伺服器保持同步的狀態。

客戶端託管的那份中繼資料文件：

```json
{
  "client_id": "https://app.example.com/oauth/client.json",
  "client_name": "Example MCP Client",
  "client_uri": "https://app.example.com",
  "application_type": "native",
  "redirect_uris": ["http://127.0.0.1:7333/callback", "http://localhost:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

文件裡的 `client_id` 值**必須**等於它被提供出來的那個 URL（授權伺服器會驗證這一點；不符就拒絕）。授權伺服器會在它的 RFC 8414 中繼資料裡，用 `client_id_metadata_document_supported: true` 公告支援。

以現行的 CIMD 契約而言，`client_id`、`client_name` 與一個非空的 `redirect_uris` 陣列是必填的。客戶端識別碼是一個帶路徑的絕對 HTTPS URL。`application_type` 可以放，但它不是 CIMD 的必填欄位。不要把 DCR 對 `application_type` 的要求，複製到偏好的 CIMD 路徑上。

規格對兩件安全事實講得很直白：

- **SSRF。** 授權伺服器會去抓一個由對方提供的 URL。它必須防禦伺服器端請求偽造（不得去抓內部／管理端點）。
- **localhost 冒充。** 光靠 CIMD 擋不住本機攻擊者宣稱某個正當客戶端的中繼資料 URL，並綁定任意的 `localhost` 重導。授權伺服器在取得同意時**必須**清楚顯示重導 URI 的主機名稱，並且**應該**對「只有 localhost 重導」提出警告。

因為 CIMD 不需要伺服器端狀態，就不必像 DCR 那樣架起一個註冊器。客戶端那一側是唯讀的：從一個靜態 HTTPS 端點提供你的中繼資料文件，讓授權伺服器去拉。

如果授權伺服器的維運方已經配發過客戶端識別碼，就在嘗試自動註冊之前先用那份綁定簽發者的註冊資料。否則優先用 CIMD。只有在該簽發者既不能預先註冊、也不能用 CIMD 時，才用已棄用的 DCR。

### RFC 7591：已棄用的相容註冊

DCR 在 2026-07-28 修訂版裡被棄用了。只在授權伺服器無法消化 CIMD、而預先註冊又不切實際時才保留它。相容用的客戶端會 POST：

```json
POST /register
Content-Type: application/json

{
  "application_type": "native",
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

伺服器回應一個 `client_id`，以及一個供日後更新用的 `registration_access_token`：

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

`application_type` 不是裝飾。回送式的桌面客戶端宣告 `native`；伺服器託管的客戶端宣告 `web`，並使用 HTTPS 重導 URI。對公開的原生客戶端而言，`token_endpoint_auth_method: none` 是正確的預設。它只拿到一個 `client_id`，由 PKCE 提供持有證明。

三個生產環境的坑：

- 註冊端點必須依來源 IP 做速率限制。少了這個，敵意行為者就能腳本化幾百萬筆假註冊，把 `client_id` 命名空間耗盡。在註冊器處理請求之前先跑一次速率限制檢查。
- 有些企業 IdP 要求 `software_statement`（一份為客戶端背書的已簽章 JWT）。這一課的模擬版跳過它；生產環境會接上一道驗證步驟，拒絕來自 localhost 重導 URI 以外、未簽章的註冊。
- `registration_access_token` 必須以雜湊形式存放，不能存明文。這個權杖被竊，代表攻擊者可以改寫該客戶端的重導 URI。

### RFC 8707（回顧）—— 資源指示器

單元 16 立好了形狀。生產規則是：每一則權杖請求都包含 `resource=<canonical-mcp-url>`，而 MCP 伺服器在每一次呼叫上驗證 `token.aud` 與自己的資源 URL 相符。標準 URI 是那台伺服器*最具體*的識別碼：使用小寫的 scheme 與主機、沒有片段，慣例上也沒有尾斜線。路徑部分**不會**依規則被剝掉 —— 當它是用來標識個別 MCP 伺服器時，規格會保留它。`https://mcp.example.com`、`https://mcp.example.com/mcp`、`https://mcp.example.com:8443` 與 `https://mcp.example.com/server/mcp` 都是有效的標準 URI。每台伺服器挑一個，並把 `aud` 精確釘在它上面。（為了簡潔，這一課的模擬版使用像 `https://notes.example.com` 這種裸主機受眾；若一次部署在同一個來源底下併置多台 MCP 伺服器，就用路徑來區分它們。）

### RFC 7636（回顧）—— PKCE

PKCE 在 OAuth 2.1 裡是強制的。這一課的授權碼流程一律帶著 `code_challenge` 與 `code_verifier`。伺服器會拒絕任何沒有 verifier、或 verifier 雜湊後對不上已儲存 challenge 的權杖請求。

### MCP 2026-07-28 的授權輪廓

現行的 MCP 修訂版保留了 OAuth 的資源伺服器邊界，同時讓 MCP 傳輸變成無狀態。已經沒有協定工作階段可以拿來快取身分決策了。因此授權層要各自獨立驗證每一則請求：

- 實作 RFC 9728 受保護資源中繼資料，並透過 401 上的 `WWW-Authenticate: Bearer resource_metadata="..."` 標頭，**或**透過 well-known URI `/.well-known/oauth-protected-resource` 提供它的位置（SEP-985 讓那個標頭變成選用的，並提供 well-known 退路）。中繼資料的 `authorization_servers` 欄位**必須**至少列出一台伺服器。
- 只透過**每一則**請求上的 `Authorization: Bearer ...` 接受權杖 —— 絕不放在查詢字串裡，也絕不只在工作階段開始時驗證一次。
- 每則請求都驗證 `aud`、`iss`、`exp` 與必要範圍。伺服器**必須**驗證這個權杖確實是專門簽給它的（受眾）；`aud` 缺漏或不符就拒絕，絕不當成萬用字元。
- 在 401／403 時，回傳帶著 `error=...` 的 `WWW-Authenticate: Bearer`、`resource_metadata="<PRM-URL>"` 參數（中繼資料文件的 URL，*不是*裸資源），以及在 `insufficient_scope`（403）時的 `scope="..."`。注意：那個參數是 `resource_metadata`，一個發現指標 —— 這則挑戰裡沒有 `resource` 參數。
- 授權伺服器發現同時接受 RFC 8414 OAuth 中繼資料**或** OpenID Connect Discovery 1.0；客戶端必須依優先序把兩個 well-known 後綴都試過。
- 防禦**混合攻擊（mix-up）**的是客戶端，不是伺服器：它在重導之前記下預期的 `issuer`，並在兌換授權碼之前，驗證實際授權回應裡回傳的 `iss` 值（RFC 9207）。光靠 PKCE 擋不住混合攻擊，因為客戶端會把自己的 `code_verifier` 交給它被導去的那個權杖端點。
- 一份客戶端憑證屬於一個授權伺服器簽發者。如果發現解析出不同的簽發者，客戶端要重新註冊，而不是拿出舊的 `client_id`、註冊權杖或存取權杖。
- CIMD 是偏好的註冊機制。DCR 已棄用；相容用的 DCR 請求仍然要宣告正確的 `application_type`。

OAuth 2.1 草案是基底；RFC 8414／7591／8707／9728／9207 加 RFC 7636 加 CIMD 是介面；MCP 規格是輪廓。

### 部署能力檢查表

廠商的功能對照表很快就會過時。改為檢視你實際要部署的那台授權伺服器所回傳的中繼資料。這道關卡是機械式的：

| 檢查 | 必要決策 |
|---|---|
| 發現到的簽發者 | 政策所預期的確切 HTTPS 簽發者 |
| PKCE | 有公告 `S256`；否則停止 |
| 註冊 | CIMD 優先，接受預先註冊，DCR 只做已棄用的相容 |
| 授權回應 | 當 `iss` 存在或已被公告時要驗證 RFC 9207 `iss` |
| 資源綁定 | 權杖請求帶上 `resource`；資源伺服器要求相符的 `aud` |
| 憑證儲存 | 以簽發者為鍵存放客戶端 ID 與註冊憑證；以簽發者加資源為鍵存放存取權杖 |
| DCR 相容 | 宣告 `native` 或 `web`；拒絕與所宣告 application type 不符的重導 URI |

不要從產品名稱或方案等級去推斷支援與否。把發現到的那份文件收進部署證據，並在必填欄位缺漏時 fail closed。

### JWKS 刷新模式（在 AS 端輪替，在資源伺服器端刷新）

把兩個動詞分清楚，因為把它們混為一談是真實會發生的生產漏洞：

- **輪替（Rotate）**是*授權伺服器*做的事：鑄造一把新的簽章金鑰、把它發布到 JWKS，之後再淘汰舊的。資源伺服器在這件事上沒有角色，也做不到 —— 它沒有 IdP 的私鑰。
- **刷新（Refresh）**是*資源伺服器*做的事：重新 `GET` 已發布的 JWKS 進自己的快取。那是資源伺服器唯一會對 JWKS 做的動作。

生產環境的失敗模式是快取過期。用一個排程刷新工作加上一個鍵值快取來解。資源伺服器跑一個工作（cron、timer，你的執行環境有什麼都行），依固定間隔抓 `<issuer>/.well-known/jwks.json`，並覆蓋 `cache[issuer] = {keys, fetched_at}`。驗證器從那個快取讀。當某個權杖的 `kid` 不在快取裡時，觸發**一次**同步刷新作為補救，然後重新檢查。這一次處理兩種情況：排程刷新，以及「用全新金鑰簽的權杖，在下一次排程刷新前就抵達」的金鑰重疊窗口。

那個補救**必須是重新抓取，絕不是輪替**。如果你把快取未命中的路徑接到「輪替並鑄造」，有兩件事會壞掉：（1）鑄造出的新金鑰產生的 `kid`，*仍然*對不上那個權杖，所以查找還是失敗；（2）攻擊者只要撒出一堆帶隨機 `kid` 的權杖，就能逼出無上限的一連串金鑰建立 —— 一次自作自受的 DoS。重新抓取是冪等的，所以一個假 `kid` 最多只浪費一次抓取。

快取的形狀：

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

同時存在兩把金鑰是穩定狀態。授權伺服器的輪替做法是先引入下一把金鑰（`k_2026_04`），之後才淘汰前一把（`k_2026_03`），這樣用舊金鑰簽出的權杖在到期前仍然有效。快取持有兩者的聯集；驗證器依 `kid` 挑選。

### 那段驗證常式

MCP 伺服器在分派任何工具之前先跑驗證。`code/main.py` 用的形狀是：

```python
result = server.validate(bearer_token, required_scope="mcp:tools.invoke")
if not result["valid"]:
    return {"status": result["status"], "WWW-Authenticate": result["www_authenticate"]}
```

`validate` 會解碼 JWT、從 JWKS 快取解析出簽章金鑰（未命中時刷新一次）、驗證簽章，然後檢查 `iss` 是否在允許清單裡、`aud` 是否等於這台伺服器的標準資源、`exp`，以及必要範圍 —— 並在第一次失敗時回傳一則 `WWW-Authenticate` 挑戰。把它保持成資源伺服器上的單一常式，意味著每一個入口（每一次工具呼叫、每一種傳輸）都走同一批檢查；沒有任何一條路徑能在不驗證的情況下抵達工具。

### 不透明權杖用自省，不用猜

不是每一個存取權杖都是 JWT。如果簽發者文件說明它是不透明權杖，資源伺服器就無法把它解碼成值得信任的宣告。它要透過一條已認證的後端通道，把權杖送到簽發者的 RFC 7662 自省端點，並要求 `active: true`、預期的簽發者脈絡、確切的 MCP 受眾或資源、尚未過期的時間宣告，以及該具體工具所需的範圍。

自省結果要以簽發者、權杖的單向摘要值與 MCP 資源為鍵來快取。絕不要拿明文權杖當成日誌或快取的標籤。正向快取條目的存活時間，取「權杖到期」「簽發者的快取指引」「該部署的撤銷新鮮度目標」三者中最早的那一個。負向快取要夠短，才不會讓一個剛簽發的權杖持續被誤判為 inactive。就算不透明權杖的字串完全相同，針對某個資源的結果也不能拿去授權另一個資源。

不要從攻擊者可控的權杖內容去挑選驗證模式。把「走 JWT 還是走自省」釘在已驗證的簽發者中繼資料與部署組態上。走 JWT 路徑時，釘住可接受的演算法與受信任的 `jwks_uri`；絕不要跟隨只由權杖標頭選定的金鑰 URL 或演算法。

### 撤銷是一份新鮮度契約

RFC 7009 讓客戶端可以請授權伺服器撤銷一個權杖。那則請求不會抹掉每一台資源伺服器已經快取的副本。要定義可接受的最大撤銷延遲，並讓每一個快取都遵守它。

用不透明權杖的部署，可以靠在每次高風險呼叫時自省、或用很短的正向快取，達成更緊的撤銷。自成一體的 JWT 部署，通常結合短命的存取權杖、更新權杖撤銷、針對簽發者層級事故的金鑰淘汰，以及一份選用的主體、工作階段或權杖 id 拒絕清單，用於緊急的本地拒絕。除非資源伺服器握有當前的外部撤銷證據，否則一個已簽章的 JWT 在到期前，在密碼學上都仍然有效。

登出、帳號停用、撤回同意與事故應變是不同的觸發點，但它們都必須收斂到同一句可量測的陳述：至多經過所宣告的撤銷窗口之後，每一個副本都拒絕那份憑證。透過負載平衡器去測那句陳述，不要只對單一個熱行程測。

### 相依元件失效需要一個明訂的決定

絕不要在例外處理器裡臨時發明可用性政策。

| 失效 | 安全的生產行為 |
|---|---|
| 排程 JWKS 刷新失敗，但已知的 `kid` 仍在一個尚未失效的有界快取裡 | 只在所宣告的 stale-on-error 窗口內繼續，並發出降級的健康證據 |
| 權杖帶著未知的 `kid`，而那唯一一次允許的刷新失敗了 | 拒絕；絕不接受一個無法驗證的簽章 |
| 自省不可用 | 對受保護的呼叫 fail closed；不要把網路失敗轉譯成 `active: true` |
| 受保護資源或簽發者中繼資料意外改變 | 停止新的註冊與權杖取得；在一份有界限的事故政策底下，只保留明確固定且未過期的組態 |
| 撤銷端點不可用 | 把登出或撤銷回報為未完成，可行時在本地把憑證標記為不可用，並且不要宣稱全域撤銷已成功 |
| 時鐘來源或宣告型別無效 | 拒絕，而不是把時間偏差放寬到讓權杖通過為止 |

把失效跟無效憑證分開歸類。相依元件停擺是一個帶有健康與重試政策的運維錯誤。簽章、簽發者、受眾、到期或範圍不對，則是一次授權拒絕。兩者都不會抵達工具處理器，而且兩者都不該把權杖內容洩漏進稽核證據裡。

### 受眾重播逐步走查（存取權杖權限限縮）

伺服器 A（`notes.example.com`）與伺服器 B（`tasks.example.com`）都向同一台授權伺服器註冊。伺服器 A 被攻陷了。攻擊者拿走某位使用者的 notes 權杖，把它重播到伺服器 B。

伺服器 B 的驗證器：

1. 解碼 JWT、依 `kid` 抓 JWKS、驗證簽章。
2. 拿 `iss` 去比對它那份受保護資源中繼資料裡的 `authorization_servers`。（通過 —— 同一家 IdP。）
3. 檢查 `aud == "https://tasks.example.com"`。（失敗 —— 權杖的 `aud` 是 `https://notes.example.com`。）
4. 回傳 401，帶著 `WWW-Authenticate: Bearer error="invalid_token", error_description="audience mismatch", resource_metadata="https://tasks.example.com/.well-known/oauth-protected-resource"`。

在協定層上，受眾宣告是對這種攻擊唯一的防禦。為了效能而跳過它，是最常見的生產錯誤；驗證器必須在每一則請求上跑，不是只在工作階段開始時跑。規格把這件事叫做**存取權杖權限限縮**：MCP 伺服器 `MUST` 拒絕任何沒有在受眾裡點名它的權杖。

> **名詞註記。** 規格把*混淆代理（confused deputy）*這個詞，保留給一個相關但不同的問題：一台 MCP 伺服器擔任對第三方 API 的 OAuth **代理**，使用一個靜態的客戶端 ID，在未取得逐客戶端使用者同意的情況下轉發權杖。受眾綁定修的是上面那個重播；混淆代理的解法是逐客戶端同意，**再加上**絕不把進站權杖直接透傳給上游 API（MCP 伺服器 `MUST` 自己另外取得上游權杖）。

### 混合攻擊（一種伺服器提供不了的客戶端側防禦）

客戶端一生中會跟很多台授權伺服器打交道。惡意的 AS 可以試著讓客戶端把一台誠實 AS 的授權碼，拿去攻擊者的權杖端點兌換。受眾綁定在這裡幫不上忙 —— 攻擊發生在任何權杖存在之前。防禦住在客戶端（RFC 9207）：

1. 重導之前，客戶端從已驗證的 AS 中繼資料記下預期的 `issuer`。
2. 收到授權回應時，客戶端在把授權碼送去任何地方之前，先拿回傳的 `iss` 參數跟那個記下的簽發者比對（單純字串比對，不做正規化）。
3. 不符（或 AS 公告了 `authorization_response_iss_parameter_supported` 卻沒有 `iss`）→ 拒絕，甚至不要顯示那些 `error` 欄位。

光靠 PKCE 擋不住混合攻擊，因為客戶端會把自己的 `code_verifier` 交給它被導去的那個權杖端點。這就是為什麼規格會把簽發者跟 PKCE verifier 與 `state` 一起，逐請求地記下來。

### 失敗模式

- **JWKS 過期。** AS 輪替金鑰之後，驗證器開始拒絕有效的權杖。解法就是上面那套「排程刷新 + 未命中補抓」模式。絕不要在沒有刷新工作的情況下快取 JWKS。
- **拿輪替當補救。** 把快取未命中的路徑接到「輪替並鑄造」而不是重新抓取，是一個真實的漏洞：它永遠生不出那個缺少的 `kid`，而且會把攻擊者可控的 `kid` 值變成一場金鑰建立 DoS。那個補救必須是冪等的 `refresh-jwks`。
- **缺少 `aud` 宣告。** 有些 IdP 在權杖請求裡沒有 `resource` 時，預設就不放 `aud`。驗證器必須拒絕缺少 `aud` 的權杖，而不是把「沒有」當成萬用字元。
- **少了 `iss` 檢查而中招的混合攻擊。** 一個沒有拿 RFC 9207 `iss` 授權回應參數，去跟重導前記下的簽發者比對的客戶端，可能被導去把一台誠實 AS 的授權碼，拿到攻擊者的權杖端點兌換。這是客戶端側的失敗；資源伺服器補不了。
- **範圍升級競態。** 同一位使用者的兩條並行升級流程可能都成功，產出兩個範圍不同的存取權杖。驗證器必須用「這則請求所出示的權杖」，而不是去查「這位使用者當前的範圍」—— 那會製造一個 TOCTOU 窗口。
- **註冊權杖被竊。** 洩漏的 `registration_access_token` 讓攻擊者可以改寫重導 URI。這些權杖靜態存放時要雜湊；每次更新都要求客戶端出示明文；一有懷疑就輪替。
- **`iss` 沒有釘住。** 一個接受任意 `iss` 的驗證器，等於讓攻擊者可以架自己的授權伺服器、為目標受眾註冊一個客戶端，然後簽發權杖。受保護資源中繼資料裡的 `authorization_servers` 清單就是那份允許清單；把它執行起來。
- **憑證或權杖快取撞鍵。** 一個只以資源為鍵存放註冊資料的客戶端，可能把某台授權伺服器的身分出示給另一台。一個只以簽發者為鍵存放存取權杖的客戶端，可能把權杖重播到錯的受眾上。以已驗證的簽發者為鍵存放註冊資料、以 `(issuer, resource)` 為鍵存放存取權杖，並在簽發者改變時一律重新註冊。

```figure
t3-jwks-rotate
```

## 框架應用

`code/main.py` 用標準函式庫 Python 與三個角色 —— `AuthorizationServer`、`ResourceServer` 與 `Client` —— 走完整條生產流程。流程是：

從版本庫根目錄執行：

```bash
cd phases/13-tools-and-protocols/18-mcp-auth-production
python3 code/main.py
python3 -m unittest discover -s code/tests -v
```

第一道指令會印出綁定簽發者的註冊與權杖驗證
逐字紀錄。第二道會回報十八項檢查通過。兩道指令都不會開啟
網路監聽埠，也不會寫入憑證。

1. 授權伺服器在 `/.well-known/oauth-authorization-server` 發布 RFC 8414 中繼資料。
2. MCP 客戶端呼叫中繼資料端點，檢查它的註冊選項（CIMD 看 `client_id_metadata_document_supported`，DCR 看 `registration_endpoint`）與 `S256` PKCE 支援。
3. 客戶端先找有沒有綁定簽發者的預先註冊，否則就用它的 HTTPS Client ID Metadata Document 註冊。已棄用的 DCR 保留成一個可獨立測試的相容方法。
4. 客戶端記下已驗證的簽發者、建立一個 S256 challenge、收到一次性的授權碼加上 `iss`、驗證那個回傳的簽發者，然後用原本的 verifier 與 RFC 8707 `resource` 指示器兌換授權碼。
5. MCP 客戶端帶著 `Authorization: Bearer ...` 呼叫 MCP 伺服器上的工具。
6. MCP 伺服器跑 `validate`，從 JWKS 快取解析出簽章金鑰。
7. IdP 輪替一把金鑰；排程刷新把 JWKS 重新拉進快取。
8. 下一次呼叫不必重啟就能對刷新後的金鑰驗證通過，而先前那個權杖在重疊窗口內仍然有效。
9. 一次針對不同 MCP 資源的受眾重播嘗試，會拿到 401 與 `audience mismatch`，以及一個 `resource_metadata` 指標。

這裡的 JWT 用 HS256 加上一份共享密鑰（好讓這一課只靠標準函式庫就能跑）。生產環境會搭配上面那套 JWKS 模式使用 RS256 或 EdDSA；除此之外驗證邏輯完全相同。因為 IdP 與資源伺服器住在同一個行程裡，`refresh_jwks` 是直接讀授權伺服器的金鑰清單；走線路時它是一次對 `jwks_uri` 的 HTTP `GET`。

## 產出交付

這一課產出 `outputs/skill-mcp-auth.md`。給定一份 MCP 伺服器組態與一組 IdP 能力，這個技能會輸出該架起來的認證介面 —— 受保護資源中繼資料、該採用的註冊路徑（CIMD、預先註冊或 DCR 退路）、JWKS 刷新排程、範圍對應，以及當 IdP 不支援完整 RFC 輪廓時該套用的拒絕規則。

## 練習

1. 執行 `code/main.py`。追蹤那條流程。留意 IdP 在第 6 步輪替一把金鑰、排程的 `refresh_jwks` 重新拉取已發布的金鑰組，而舊權杖（重疊窗口內）與新權杖都不必重啟就能驗證通過。

2. 在受保護資源中繼資料的 `authorization_servers` 清單裡加一家新的 IdP。簽發一個由新 IdP 簽章的權杖，確認驗證器接受它。再簽發一個由未列出之 IdP 簽章的權杖，確認驗證器以 `WWW-Authenticate: Bearer error="invalid_token", error_description="iss not allowed"` 拒絕。

3. 為 `register_client` 加上一道在註冊器接受請求之前執行的速率限制檢查。用一個以來源 IP 為鍵、放在小字典裡的 token bucket。

4. 讀 RFC 7591，找出這一課的 `/register` 處理器沒有驗證的兩個欄位。把驗證加上去。（提示：`software_statement` 與 `redirect_uris` 的 URI scheme。）

5. 加上第二台授權伺服器。確認客戶端存的是另一份以簽發者為鍵的註冊資料，並且拒絕重用第一個簽發者的權杖或 `client_id`。

6. 證明那個 DoS 修法有效。送給驗證器一個帶隨機 `kid` 的權杖，確認 `refresh_jwks` 最多只跑一次，而且授權伺服器的金鑰數量沒有成長。接著刻意把補救路徑改接成「輪替並鑄造」，看著金鑰數量隨著每個假權杖往上爬 —— 之後記得把重新抓取改回來。

7. 用 `native` 與 `web` 兩種客戶端各跑一次已棄用的 DCR。確認「帶 HTTP 重導 URI 的 web 客戶端」與「沒有精確回送重導的 native 客戶端」都被拒絕。

## 關鍵術語

| 術語 | 大家嘴上說的 | 實際上是什麼 |
|------|----------------|------------------------|
| ASM | 「OAuth 中繼資料文件」 | RFC 8414 的 `/.well-known/oauth-authorization-server` JSON |
| CIMD | 「客戶端中繼資料 URL」 | Client ID Metadata Document：一個當成 `client_id` 的 HTTPS URL，由 AS 去拉那份 JSON。MCP 2026-07-28 偏好的註冊方式 |
| DCR | 「自助式客戶端註冊」 | RFC 7591 的 `POST /register`；對現行 MCP 已棄用，僅為相容保留 |
| JWKS | 「驗證 JWT 用的公鑰」 | JSON Web Key Set，從 `jwks_uri` 抓取，以 `kid` 索引 |
| 輪替 vs 刷新 | 「更新金鑰」 | *輪替* = AS 鑄造／淘汰簽章金鑰；*刷新* = 資源伺服器重新抓取已發布的金鑰組。資源伺服器永遠只做刷新 |
| 資源指示器 | 「受眾參數」 | RFC 8707 的 `resource` 參數，把權杖釘在單一台伺服器上 |
| `aud` 宣告 | 「受眾」 | 驗證器拿去跟標準資源 URL 比對的 JWT 宣告 |
| 受眾重播 | 「權杖重播」 | 簽給伺服器 A 的權杖被出示給伺服器 B；靠受眾驗證防禦（規格稱：存取權杖權限限縮） |
| 混淆代理 | 「代理權杖濫用」 | 使用靜態客戶端 ID 的 MCP 代理，未取得逐客戶端同意就轉發權杖；與受眾重播不同 |
| 混合攻擊 | 「錯的權杖端點」 | 客戶端被導去把誠實 AS 的授權碼拿到攻擊者端點兌換；靠客戶端側的 RFC 9207 `iss` 防禦 |
| `iss` 允許清單 | 「受信任的授權伺服器」 | 受保護資源中繼資料的 `authorization_servers` 所列出的那個集合 |
| `resource_metadata` | 「PRM 文件在哪」 | 401／403 上的 `WWW-Authenticate` 參數，指出 RFC 9728 中繼資料 URL |
| 公開客戶端 | 「原生或瀏覽器客戶端」 | 沒有 `client_secret` 的 OAuth 客戶端；由 PKCE 補償 |
| `WWW-Authenticate` | 「401／403 回應標頭」 | 承載驅動客戶端復原的 `Bearer error=...` 指示 |

## 延伸閱讀

- [MCP authorization specification (2026-07-28)](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) - 現行的 MCP 授權輪廓
- [MCP 2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) - CIMD、簽發者驗證、DCR 棄用，以及以簽發者為鍵的憑證變更
- [OAuth Client ID Metadata Document (draft-ietf-oauth-client-id-metadata-document-00)](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-client-id-metadata-document-00) —— CIMD
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://datatracker.ietf.org/doc/html/rfc8414) —— 發現契約
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://datatracker.ietf.org/doc/html/rfc7591) —— DCR（退路）
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://datatracker.ietf.org/doc/html/rfc7636) —— 公開客戶端的持有證明
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707) —— 受眾釘選
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728) —— 資源伺服器發現
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://datatracker.ietf.org/doc/html/rfc9207) —— 防禦混合攻擊的 `iss` 參數
- [RFC 7662: OAuth 2.0 Token Introspection](https://datatracker.ietf.org/doc/html/rfc7662)
- [RFC 7009: OAuth 2.0 Token Revocation](https://datatracker.ietf.org/doc/html/rfc7009)
