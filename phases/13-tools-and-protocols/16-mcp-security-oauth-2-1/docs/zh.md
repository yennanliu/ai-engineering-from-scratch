# MCP 安全 II —— OAuth 2.1、資源指示子、增量式範圍

> 遠端 MCP 伺服器需要的是授權，不只是認證。2025-11-25 版規格對齊了 OAuth 2.1 + PKCE + 資源指示子（RFC 8707）+ 受保護資源中繼資料（RFC 9728）。SEP-835 則加上了增量式範圍同意，並在收到 403 WWW-Authenticate 時做提升式授權。這一課會把提升流程實作成一台狀態機，好讓你看見每一次跳轉。

**類型：** 實作
**程式語言：** Python (stdlib, OAuth state machine simulator)
**先修單元：** 階段 13 · 09（傳輸）、階段 13 · 15（安全 I）
**時間：** 約 75 分鐘

## 學習目標

- 區分資源伺服器與授權伺服器各自的職責。
- 走過受 PKCE 保護的 OAuth 2.1 授權碼流程。
- 用 `resource`（RFC 8707）與受保護資源中繼資料（RFC 9728）防範混淆代理人攻擊。
- 實作提升式授權：伺服器以 403 加 WWW-Authenticate 回應並索取更高的範圍；客戶端重新徵求使用者同意，然後重試。

## 問題所在

早期的 MCP（2025 年之前）出貨的遠端伺服器用的是臨時湊出來的 API 金鑰，甚至根本沒有認證。2025-11-25 版規格用一份完整的 OAuth 2.1 profile 補上了這道缺口。

三個真實世界的需求：

- **一般的遠端伺服器。** 使用者安裝一台會存取他們 Notion／GitHub／Gmail 的遠端 MCP 伺服器。搭配 PKCE 的 OAuth 2.1 是正確的形狀。
- **範圍提升。** 一台被授予 `notes:read` 的筆記伺服器，之後可能為了某個特定動作需要 `notes:write`。與其把整套流程重跑一遍，提升（SEP-835）只索取那項額外的範圍。
- **防範混淆代理人。** 客戶端持有一個受眾範圍限定給伺服器 A 的 token。伺服器 A 是惡意的，試圖把該 token 出示給伺服器 B。資源指示子（RFC 8707）把 token 釘在它預期的受眾上。

OAuth 2.1 不是新東西。新的是 MCP 的 profile：規定必用的流程（只有授權碼 + PKCE；預設不用 implicit、不用 client credentials）、每次 token 請求都強制帶資源指示子，以及公開受保護資源中繼資料好讓客戶端知道該去哪裡。

## 核心概念

### 角色

- **客戶端。** 那個 MCP 客戶端（Claude Desktop、Cursor 等）。
- **資源伺服器。** 那台 MCP 伺服器（筆記、GitHub、Postgres，隨便什麼）。
- **授權伺服器。** 簽發 token。它可以與資源伺服器是同一個服務，也可以是獨立的 IdP（Auth0、Keycloak、Cognito）。

在 MCP 的 profile 中，資源伺服器與授權伺服器「可以」是同一台宿主，但「應該」用 URL 區分開來。

### 授權碼 + PKCE

流程是：

1. 客戶端產生 `code_verifier`（隨機）與 `code_challenge`（SHA256）。
2. 客戶端把使用者轉址到 `/authorize?response_type=code&client_id=...&redirect_uri=...&scope=notes:read&code_challenge=...&resource=https://notes.example.com`。
3. 使用者同意。授權伺服器轉址到 `redirect_uri?code=...`。
4. 客戶端 POST 到 `/token?grant_type=authorization_code&code=...&code_verifier=...&resource=...`。
5. 授權伺服器拿 verifier 的雜湊去對存下的 challenge 驗證，然後簽發一個存取 token。
6. 客戶端使用該 token：對資源伺服器的每一次請求都帶上 `Authorization: Bearer ...`。

PKCE 防範授權碼攔截攻擊。資源指示子則讓該 token 在別處無效。

### 受保護資源中繼資料（RFC 9728）

資源伺服器發布一份 `.well-known/oauth-protected-resource` 文件：

```json
{
  "resource": "https://notes.example.com",
  "authorization_servers": ["https://auth.example.com"],
  "scopes_supported": ["notes:read", "notes:write", "notes:delete"]
}
```

客戶端從資源伺服器那裡探索到授權伺服器。這減少了設定 —— 客戶端只需要那個資源 URL。

### 資源指示子（RFC 8707）

token 請求中的 `resource` 參數，把 token 釘在它預期的受眾上。簽發出的 token 內含 `aud: "https://notes.example.com"`。另一台 MCP 伺服器收到這個 token 時會檢查 `aud` 並拒絕它。

### 範圍模型

範圍是以空白分隔的字串。常見的 MCP 慣例有：

- `notes:read`、`notes:write`、`notes:delete`
- 管理能力用 `admin:*`（請節制使用）
- 身分用 `profile:read`

範圍的挑選應該最小權限：現在需要什麼就要什麼，需要更多時再提升。

### 提升式授權（SEP-835）

使用者授予了 `notes:read`。他們之後要求代理刪除一則筆記。伺服器回應：

```
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
    scope="notes:delete", resource="https://notes.example.com"
```

客戶端看到 insufficient_scope 錯誤，就為那項額外範圍向使用者跳出同意對話框，跑一次小型的 OAuth 流程，再帶著新 token 重試該請求。

### token 受眾驗證

每一次請求：伺服器檢查 `token.aud == self.resource_url`。不符就 401。這擋掉了跨伺服器的 token 重用。

### 短生命週期 token 與輪替

存取 token「應該」是短生命週期的（預設 1 小時）。刷新 token 則在每次刷新時輪替。客戶端在背景處理靜默刷新。

### 不得直傳 token

Sampling 伺服器（階段 13 · 11）「絕不可」把客戶端的 token 直接傳給其他服務。那個 sampling 請求就是邊界。

### 防範混淆代理人

token 綁在 `aud` 上。客戶端綁在 `client_id` 上。每一次請求都對兩者驗證。規格明文禁止了那個在 MCP 之前的遠端工具生態系中很常見的舊「傳遞 token」模式。

### Client ID 探索

每個 MCP 客戶端都在一個固定的 URL 上發布它的中繼資料。授權伺服器可以抓取客戶端的中繼資料文件，藉此探索轉址 URI 與聯絡資訊。這免去了手動註冊客戶端的步驟。

### 閘道與 OAuth

階段 13 · 17 會展示企業閘道如何處理 OAuth：閘道持有上游伺服器的憑證，發給客戶端的 token 由閘道簽發，而上游的 token 從不離開閘道。這翻轉了信任模型 —— 使用者只需向閘道認證一次；閘道則負責處理 N 台伺服器的授權。

## 框架應用

`code/main.py` 把完整的 OAuth 2.1 提升流程模擬成一台狀態機。它實作了：

- PKCE 的 code-verifier／challenge 產生。
- 帶資源指示子的授權碼流程。
- 受保護資源中繼資料端點。
- 帶受眾檢查的 token 驗證。
- `insufficient_scope` 時的提升。

這一課沒有 HTTP 伺服器；狀態機在記憶體中跑，好讓你追蹤每一次跳轉。階段 13 · 17 的閘道那一課會把它接到真正的傳輸上。

## 產出交付

這一課產出 `outputs/skill-oauth-scope-planner.md`。給定一台帶工具的遠端 MCP 伺服器，這項技能會設計出範圍集合、釘選規則與提升政策。

## 練習

1. 跑一次 `code/main.py`。追蹤那個兩段範圍的提升流程。記下提升時哪些跳轉重複了。

2. 加上刷新 token 輪替：每次刷新都簽發一個新的刷新 token 並讓舊的失效。模擬一個被竊的刷新 token 在輪替之後被使用，確認它會失敗。

3. 用 stdlib 的 http.server，把受保護資源中繼資料端點實作成一個真正的 HTTP 回應。比照單元 09 的 /mcp 端點。

4. 為一台 GitHub MCP 伺服器設計一套範圍階層：讀儲存庫、寫 PR、核准 PR、合併 PR、管理。在每一級之間使用提升。

5. 讀 RFC 8707 與 RFC 9728。找出 9728 中那個 MCP 用法與 RFC 範例不同的欄位。（提示：跟 `scopes_supported` 有關。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| OAuth 2.1 | 「現代版 OAuth」 | 整併過的 RFC，強制 PKCE 並禁用 implicit 流程 |
| PKCE | 「持有證明」 | code verifier + challenge，用以擊敗授權碼攔截 |
| 資源指示子 | 「token 受眾」 | RFC 8707 的 `resource` 參數，把 token 釘到單一台伺服器 |
| 受保護資源中繼資料 | 「探索文件」 | RFC 9728 的 `.well-known/oauth-protected-resource` |
| 提升式授權 | 「增量式同意」 | SEP-835 用來依需求追加範圍的流程 |
| `insufficient_scope` | 「帶 WWW-Authenticate 的 403」 | 伺服器發出的訊號，要求為更大的範圍重新徵求同意 |
| 混淆代理人 | 「跨服務重用 token」 | 一種攻擊：受信任的持有者不當地轉發了 token |
| 短生命週期 token | 「存取 token 的 TTL」 | 很快就過期的 bearer；由刷新 token 續期 |
| 範圍階層 | 「最小權限的階梯」 | 分級的範圍集合，各級之間以提升銜接 |
| Client ID 中繼資料 | 「客戶端探索文件」 | 客戶端發布自身 OAuth 中繼資料的那個 URL |

## 延伸閱讀

- [MCP — Authorization spec](https://modelcontextprotocol.io/specification/draft/basic/authorization) —— 權威的 MCP OAuth profile
- [den.dev — MCP November authorization spec](https://den.dev/blog/mcp-november-authorization-spec/) —— 2025-11-25 變動的逐步說明
- [RFC 8707 — Resource indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707) —— 受眾釘選的那份 RFC
- [RFC 9728 — OAuth 2.0 protected resource metadata](https://datatracker.ietf.org/doc/html/rfc9728) —— 探索文件的那份 RFC
- [Aembit — MCP OAuth 2.1, PKCE and the future of AI authorization](https://aembit.io/blog/mcp-oauth-2-1-pkce-and-the-future-of-ai-authorization/) —— 提升流程的實務逐步說明
