# MCP 授權：CIMD、簽發者綁定、PKCE 與權限升級

> 遠端 MCP 請求是無狀態的，但它的授權不是匿名的。把每一份憑證綁到造出它的那個簽發者，把每一個權杖綁到收下它的那個資源。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 · 09（傳輸）、階段 13 · 15（安全）
**時間：** 約 90 分鐘

## 學習目標

- 透過受保護資源中繼資料發現授權伺服器。
- 優先採用 Client ID Metadata Document，而非已棄用的動態客戶端註冊。
- 在無可避免要走 DCR 相容路徑時，宣告正確的 `application_type`。
- 驗證授權回應的 `iss`，並依簽發者隔離憑證。
- 使用 PKCE、資源指示器、受眾驗證與漸進式範圍。
- 在沒有協定工作階段的情況下，送出已授權的 MCP 2026-07-28 請求。

## 問題所在

遠端 MCP 伺服器可能讀取私密紀錄、寫入外部系統，或觸發昂貴的工作。認證告訴它是誰出示了憑證。授權還必須回答：

- 是哪一台授權伺服器簽發了這份憑證？
- 這個權杖是給哪一個 MCP 資源用的？
- 是哪一個客戶端與哪一個重導 URI 完成了這條流程？
- 使用者核准了哪些操作？
- 當下這則確切的請求，仍然符合那份核准嗎？

2026-07-28 的授權輪廓，強化了客戶端註冊與簽發者的處理方式。它優先採用 Client ID Metadata Document、棄用動態客戶端註冊、在 DCR 上要求正確的 `application_type`、驗證 RFC 9207 的簽發者回應，並禁止跨簽發者重用憑證。

這些規則與無狀態核心互補。它們不會讓核心握手或 `Mcp-Session-Id` 復活。

## 核心概念

### 認清三個角色

- **MCP 客戶端：** 代表資源擁有者送出請求。
- **MCP 資源伺服器：** 接受存取權杖，並提供 MCP 端點。
- **授權伺服器：** 認證資源擁有者、蒐集同意，並簽發權杖。

資源伺服器與授權伺服器可以一起運營，但要讓它們的識別碼與驗證責任保持分離。

### 授權適用於 HTTP

MCP 的授權規格適用於以 HTTP 為基礎的傳輸。本機的 stdio 伺服器跑在行程與作業系統的信任邊界之下。不要只為了對稱，就替 stdio 加上一條假的瀏覽器 OAuth 流程。

對於遠端 Streamable HTTP，在每一則請求的 `Authorization` 標頭裡送出 bearer token。絕不要把它放進 URL。

### 從受保護資源中繼資料開始

資源伺服器發布 RFC 9728 中繼資料：

```json
{
  "resource": "https://notes.example.com/mcp",
  "authorization_servers": ["https://auth.example.com"],
  "scopes_supported": ["notes:delete", "notes:read", "notes:write"]
}
```

客戶端從 MCP 資源 URL 出發，抓取這份文件、挑一台被公告的授權伺服器，再去抓那台伺服器的 OAuth 或 OpenID Connect 中繼資料。

組出 RFC 9728 well-known URL 時要保留資源路徑。對資源 `https://notes.example.com/mcp` 而言，這一課用的是 `https://notes.example.com/.well-known/oauth-protected-resource/mcp`。把 `/mcp` 後綴丟掉，可能會選到同一個來源上另一個受保護資源的中繼資料。

不要從主機名稱猜授權伺服器。也不要跟隨從未經驗證的錯誤主體裡發現的簽發者。要為「客戶端願意信任哪些簽發者」訂一條政策。

### 驗證授權伺服器中繼資料

中繼資料應該公開端點與支援的控制項：

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/authorize",
  "token_endpoint": "https://auth.example.com/token",
  "code_challenge_methods_supported": ["S256"],
  "authorization_response_iss_parameter_supported": true,
  "client_id_metadata_document_supported": true
}
```

PKCE 一律要求 S256。記下那個確切的簽發者字串。那個確切的值，之後就是註冊與權杖儲存的鍵。

### 遵守註冊優先序

當客戶端跟選定的簽發者已經有明確的關係時，使用預先註冊的客戶端資訊。否則，在授權伺服器公告支援時，優先採用 Client ID Metadata Document。只有在需要相容性時才用已棄用的 DCR 作為退路，若以上機制都不可用，再提示使用者輸入客戶端資訊。

### 優先採用 Client ID Metadata Document

Client ID Metadata Document 給授權伺服器一個 HTTPS URL，它同時是客戶端識別碼，也是它中繼資料的所在位置：

```json
{
  "client_id": "https://client.example.com/oauth/metadata.json",
  "client_name": "Notes desktop client",
  "application_type": "native",
  "redirect_uris": ["http://127.0.0.1:8765/callback"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"]
}
```

授權伺服器會抓取並驗證這份文件。`client_id` 必須是一個帶路徑的 HTTPS URL，而文件裡的那個值必須跟該 URL 完全相同。必填的文件欄位是 `client_id`、`client_name` 與 `redirect_uris`。`application_type` 出現在這個範例裡，但它不是 CIMD 的必要條件。它新增的強制用途，特指的是 DCR 那條路徑。

把抓取這份文件當成一次對 SSRF 敏感的操作。解析並驗證目的地、拒絕回送位址、私有位址、link-local 位址與其他不被允許的位址，在重導與 DNS 變更之後重新檢查，限制重導次數、位元組數與時間，要求 JSON，並且只依照已驗證的 HTTP 快取控制來快取。把 `client_name` 與其他顯示欄位當成不可信的文字。

CIMD 讓你不必為每一次初次接觸都鑄造一個全新的動態識別碼。它並沒有讓重導 URI 驗證、簽發者政策或使用者同意變得不必要。

### DCR 是一條相容路徑

動態客戶端註冊對較舊的授權伺服器仍然可用，但對新的 MCP 實作而言已被棄用。

使用 DCR 時要宣告 `application_type`：

```json
{
  "client_name": "Notes desktop client",
  "application_type": "native",
  "redirect_uris": ["http://127.0.0.1:8765/callback"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"]
}
```

- 桌面、行動、命令列與回送（loopback）客戶端用 `native`。
- 遠端託管的瀏覽器應用用 `web`，搭配遠端 HTTPS 重導。

省略這個欄位，在某些 OpenID Connect 註冊實作裡會預設成 `web`，讓一個本來正當的回送重導失敗。

把 DCR 程式碼放在一個明確的退路決策後面。不要在任意一次 CIMD 驗證失敗之後就悄悄退回去。那會把一次安全失敗，變成一條更弱的註冊路徑。

### 把憑證綁到簽發者

把簽發者鑄造的註冊材料，存在那個確切的簽發者底下：

```text
issuer_credentials[issuer] = pre_registered_or_dcr_client
tokens[(issuer, resource)] = access_token
```

如果受保護資源發現的結果從 `https://auth-one.example` 變成 `https://auth-two.example`，就要重新評估信任。絕不要把第一個簽發者的客戶端密鑰、DCR 客戶端 id、註冊存取權杖、更新權杖或存取權杖，送給第二個。預先註冊與 DCR 的客戶端，必須使用為新簽發者所簽發的憑證。

CIMD 的客戶端 id 不一樣，因為它是一個自行託管的 HTTPS URL，不是由授權伺服器鑄造的憑證。同一個 CIMD URL 是可攜的：一個新的、受信任的簽發者會去抓取並驗證那份文件，不需要重新做 DCR 註冊。授權回應與權杖仍然要驗證，並存在新簽發者底下。

### 帶 PKCE 的授權碼流程

互動流程是：

1. 產生一個高熵的 `code_verifier`。
2. 導出 S256 的 `code_challenge`。
3. 送出授權請求，帶著確切的 `client_id`、`redirect_uri`、`scope`、`code_challenge` 與 `resource`。
4. 收到一則包含 `code`，以及（若有提供）`iss` 的授權回應。
5. 在使用任何回應欄位之前，先拿 `iss` 去跟記錄下來的確切簽發者比對。
6. 用 `code_verifier`、同一個重導 URI 與同一個 `resource` 交換那個授權碼。
7. 把換到的權杖存在 `(issuer, resource)` 底下。

來自 RFC 8707 的 `resource` 參數，會同時出現在授權請求與權杖請求裡。它標識的是那台 MCP 伺服器的標準 URI。

### 精確驗證 `iss`

RFC 9207 防止某個簽發者的授權回應被誤認成另一個簽發者的回應。

當 `iss` 存在時，拿它跟記錄下來的簽發者比對，過程中不做大小寫折疊、不改動尾斜線、不移除預設埠、也不做百分比編碼正規化。不一致時，不要對那個授權碼採取任何行動，甚至不要顯示那則回應裡由攻擊者控制的錯誤細節。

會附上 `iss` 的授權伺服器，會公告 `authorization_response_iss_parameter_supported: true`。即使少了那項公告，現行客戶端仍然要驗證出現的 `iss`。

### 在 MCP 伺服器上驗證受眾

資源伺服器只接受簽發給它自己的權杖：

```text
token.issuer == configured_authorization_server
token.audience == canonical_mcp_resource
```

無效、過期、簽發者錯誤或受眾錯誤的權杖，都收到 401。MCP 伺服器不得接受、也不得轉送一個給別的服務用的權杖。

### 只索取當下最小的範圍

從當下需要的範圍開始。如果後續某個工具需要更多，伺服器回傳 403，附上一則具權威性的範圍挑戰：

```text
WWW-Authenticate: Bearer error="insufficient_scope",
  scope="notes:delete",
  resource_metadata="https://notes.example.com/.well-known/oauth-protected-resource/mcp"
```

客戶端解釋這項新權限、取得同意、用合併後的範圍集合走一次新的授權流程，然後用一個新的 JSON-RPC id 重試那則 MCP 請求。

不要假設被挑戰的範圍是 `scopes_supported` 的子集合。對當下這個操作而言，那則挑戰才是權威。

### 授權與無狀態的 MCP 線路

一次已授權的工具呼叫，仍然帶著完整的當前請求信封：

```text
POST /mcp
Authorization: Bearer <access-token>
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: notes.delete
```

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "tools/call",
  "params": {
    "name": "notes.delete",
    "arguments": {"id": "note-7"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
      "io.modelcontextprotocol/clientInfo": {
        "name": "oauth-lesson-client",
        "version": "1.0.0"
      }
    }
  }
}
```

權杖授權的是主體。請求中繼資料協商的是協定行為。兩者不能互相取代。

用固定的順序驗證線路：JSON-RPC 與中繼資料型別、標頭與主體是否相等，然後才是協定支援。路由或版本標頭不一致，回傳 HTTP 400 與 `-32020`。如果標頭與主體對一個不受支援的版本取得一致，回傳 HTTP 400 與 `-32022`，`data` 精確為 `{"supported":["2026-07-28"],"requested":"<actual>"}`。未知的方法回傳 HTTP 404 與 `-32601`。

每一個請求錯誤，包含 401 無效權杖與 403 範圍不足，都是一個帶著原始請求 `id` 的 JSON-RPC 錯誤信封。結構化的復原資訊放在選用的錯誤 `data` 裡；`WWW-Authenticate` 仍然是一個 HTTP 回應標頭。通知沒有 `id`，所以它不會收到 JSON-RPC 主體。被接受的 HTTP 通知回傳 202 與空主體。

伺服器實作 `server/discover` 並公告工具，所以它也實作必備的 `tools/list` 方法。它的工具描述有穩定的名稱、描述，以及根節點為物件的 `inputSchema` 值。那份清單具確定性，並回傳 `resultType`、伺服器身分中繼資料、一個有界限的 `ttlMs` 與 `cacheScope`。發現，以及與使用者無關的工具清單，可以在授權之前就提供。若其中任一項會因主體而異，就套用一般政策與私有快取。

### 不做權杖穿透

MCP 伺服器不得把客戶端的 MCP 存取權杖轉發給下游 API。要另外取得一個受眾正確的下游權杖，或採用明確的權杖交換設計。受眾驗證只有在各服務都拒絕「鑄造給別人的權杖」時才有用。

### 更新權杖

更新權杖是選用的。簽發之後要以機密方式保存，並以簽發者與資源為鍵。不要假設它一定存在。當授權伺服器支援輪換時就輪換它們，並偵測已失效值的重用。

```figure
t3-scope-stepup
```

## 動手實作

`code/main.py` 是一個行程內的協定與授權模擬器。它實作了受保護資源發現、授權伺服器中繼資料、CIMD 註冊、有版本關卡的 DCR 退路、application type 檢查、PKCE、簽發者驗證、綁定資源的權杖、範圍升級、`server/discover`、`tools/list`，以及一則無狀態的工具請求。

這個模型收到的是已解析的請求主體與路由標頭。它不是完整的 HTTP 轉接層，也不解析 `Content-Type` 或 `Accept`。把它接到單元 09 的 Streamable HTTP 轉接層，那裡會要求 `Content-Type: application/json`，以及同時包含 `application/json` 與 `text/event-stream` 的 `Accept` 值。

執行它：

```bash
cd phases/13-tools-and-protocols/16-mcp-security-oauth-2-1
python3 code/main.py
python3 -m unittest discover code/tests -v
```

輸出會先顯示發現，接著是 CIMD 註冊、一次普通的讀取、兩次各自獨立的範圍升級，以及以簽發者為鍵的憑證儲存。

## 框架應用

把模擬器裡的物件對應到正式環境的元件：

- `ResourceServer.protected_resource_metadata` 變成 RFC 9728 端點。
- `AuthorizationServer.metadata` 變成 RFC 8414 或 OpenID Connect 發現。
- `Client.enroll` 變成 CIMD 解析，加上一條明確的 DCR 相容分支。
- 由簽發者鑄造的客戶端憑證與 `tokens_by_issuer_resource` 變成加密紀錄。CIMD URL 可以維持可攜，但它的授權結果仍然綁定簽發者。
- `ResourceServer.handle` 變成一層中介軟體：在分派之前驗證當前的 MCP 標頭、權杖與工具範圍，同時讓每一個請求錯誤都留在相對應的 JSON-RPC 信封裡。

## 產出交付

這一課交付 `outputs/skill-oauth-scope-planner.md`。它現在會設計註冊優先序、綁定簽發者的憑證儲存、application type、PKCE、資源指示器、範圍挑戰，以及當前的無狀態請求邊界。

## 練習

1. 加上更新權杖輪換，並拒絕重用前一個更新權杖。
2. 加上一份簽發者允許清單。簽發者改變時，只重用可攜的 CIMD URL；拒絕所有先前由簽發者鑄造的憑證與權杖。
3. 為授權碼加上到期時間，並確認太晚的交換會失敗。
4. 建一個 web 客戶端變體，使用遠端 HTTPS 重導，並把它的 DCR 中繼資料跟原生客戶端做比較。
5. 在同一個簽發者底下加上第二個資源。確認它的存取權杖無法用在第一個資源上。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| 受保護資源中繼資料 | RFC 9728 文件，標明資源與授權伺服器 |
| CIMD | HTTPS 中繼資料文件，其 URL 就是 OAuth 客戶端識別碼 |
| DCR | 已棄用的動態客戶端註冊，為相容性而保留 |
| `application_type` | `native` 或 `web`，用來驗證重導 URI 規則 |
| PKCE | verifier 與 S256 challenge，保護被攔截的授權碼 |
| `iss` | RFC 9207 的授權回應簽發者識別碼 |
| 資源指示器 | RFC 8707 參數，把權杖請求綁到某個 MCP 資源 |
| 受眾（Audience） | 權杖有效的目標資源 |
| 權限升級（Step-up） | 為當前操作額外需要的範圍，重新取得同意與簽發權杖 |
| 綁定簽發者的憑證 | 依確切授權伺服器簽發者隔離的註冊與權杖紀錄 |

## 延伸閱讀

- [MCP 2026-07-28 authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
- [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [RFC 8707: Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9207: OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [OAuth Client ID Metadata Document draft](https://datatracker.ietf.org/doc/draft-ietf-oauth-client-id-metadata-document/)
