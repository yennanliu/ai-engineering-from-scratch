# MCP 閘道與登錄 —— 企業控制平面

> 企業不可能讓每位開發者隨便安裝 MCP 伺服器。閘道把認證、RBAC、稽核、速率限制、快取與工具下毒偵測集中起來，再把合併後的工具表面暴露成單一個 MCP 端點。官方 MCP 登錄（Anthropic + GitHub + PulseMCP + Microsoft，經命名空間驗證）是那個權威的上游。這一課會指出閘道該擺在哪裡、走過一份最小實作，並巡覽 2026 年的廠商版圖。

**類型：** 學習
**程式語言：** Python (stdlib, minimal gateway)
**先修單元：** 階段 13 · 15（工具下毒）、階段 13 · 16（OAuth 2.1）
**時間：** 約 45 分鐘

## 學習目標

- 說明 MCP 閘道坐落在哪裡（在 MCP 客戶端與多台後端 MCP 伺服器之間）。
- 實作閘道的五項職責：認證、RBAC、稽核、速率限制、政策。
- 在閘道層強制執行一份已釘選的工具雜湊清單。
- 分辨官方 MCP 登錄與各家後設登錄（Glama、MCPMarket、MCP.so、Smithery、LobeHub）。

## 問題所在

一家財星 500 大企業有 30 台核准的 MCP 伺服器、5000 位開發者、法遵與稽核要求，以及一支想要集中政策的安全團隊。讓每位開發者在自己的 IDE 裡安裝任意伺服器，根本不用談。

閘道模式是：

1. 閘道以單一個 Streamable HTTP 端點運行，開發者連到它。
2. 閘道持有每一台後端 MCP 伺服器的憑證。
3. 每一次開發者請求，都經由閘道自己的 OAuth 認證並界定範圍。
4. 閘道把呼叫路由到後端伺服器，並套用政策。
5. 所有呼叫都記錄下來以供稽核。

Cloudflare MCP Portals、Kong AI Gateway、IBM ContextForge、MintMCP、TrueFoundry、Envoy AI Gateway —— 全都在 2025 到 2026 年間出貨了閘道或閘道功能。

與此同時，官方 MCP 登錄作為那個權威上游上線了：經策展、命名空間驗證、以反向 DNS 命名的伺服器，閘道可以從那裡拉取。後設登錄（Glama、MCPMarket、MCP.so、Smithery、LobeHub）則跨多個來源彙整伺服器。

## 核心概念

### 閘道的五項職責

1. **認證。** 用 OAuth 2.1 辨識開發者；對映到使用者角色。
2. **RBAC。** 逐使用者的政策：哪些伺服器、哪些工具、哪些範圍。
3. **稽核。** 每一次呼叫都記錄何人、何事、何時、結果為何。
4. **速率限制。** 逐使用者／逐工具／逐伺服器的上限，以防濫用。
5. **政策。** 拒絕被下毒的描述、強制二選二規則、遮蔽 PII。

### 閘道即單一端點

對開發者來說，閘道看起來就是一台 MCP 伺服器。它在內部路由到 N 台後端。工作階段 id（階段 13 · 09）會在邊界處被改寫。

### 憑證保管

開發者永遠看不到後端的 token。閘道持有它們（或代理到一個持有它們的身分提供者）。一位在閘道上擁有 `notes:read` 的開發者，可以用閘道自己的後端憑證遞移地存取那台筆記 MCP 伺服器 —— 但只能在一份約束該遞移存取的政策之下。

### 閘道層的工具雜湊釘選

閘道持有一份已核准工具描述的清單（SHA256 雜湊）。探索時，它抓取每一台後端的 `tools/list`，把雜湊拿去對照清單，並移除任何描述已被竄改的工具。這就是把階段 13 · 15 的抽地毯防禦集中化施行。

### 政策即程式碼

進階的閘道用 OPA/Rego、Kyverno 或 Styra 來表達政策。像是「使用者 `alice` 只能在 `acme` 組織的儲存庫上呼叫 `github.open_pr`」這樣的規則，會以宣告式編碼。簡單的閘道則用手寫的 Python。兩種形狀都是有效的。

### 感知工作階段的路由

當使用者的工作階段涵蓋多台伺服器時，閘道會做多工：開發者那個單一 MCP 工作階段，底下握著 N 個後端工作階段，每台伺服器一個。來自任一後端的通知，都經由閘道路由到開發者的工作階段。

### 命名空間合併

閘道會合併所有後端的工具命名空間，通常在衝突時加前綴。像 `github.open_pr`、`notes.search`。這讓路由不再含糊。

### 登錄

- **官方 MCP 登錄（`registry.modelcontextprotocol.io`）。** 在 Anthropic、GitHub、PulseMCP、Microsoft 的託管下上線。經命名空間驗證（反向 DNS：`io.github.user/server`）。已針對基本品質做過預先篩選。
- **Glama。** 以搜尋為核心、彙整眾多來源的後設登錄。
- **MCPMarket。** 偏商業取向、附廠商列表的目錄。
- **MCP.so。** 社群目錄；開放投稿。
- **Smithery。** 套件管理器風格的安裝流程。
- **LobeHub。** 整合在他們 LobeChat 應用中的 UI 內建登錄。

企業閘道預設從官方登錄拉取，允許管理員從後設登錄策展性地追加，並拒絕任何未經釘選的東西。

### 反向 DNS 命名

官方登錄對公開伺服器強制反向 DNS 命名：`io.github.alice/notes`。命名空間防止名稱搶註，也讓信任的委派更清楚。

### 廠商巡覽，2026 年 4 月

| 廠商 | 強項 |
|--------|----------|
| Cloudflare MCP Portals | 邊緣託管；整合 OAuth；有免費方案 |
| Kong AI Gateway | K8s 原生；細粒度政策；日誌輸出到 OpenTelemetry |
| IBM ContextForge | 企業 IAM；法遵；稽核匯出 |
| TrueFoundry | 偏 DevOps 取向；指標優先 |
| MintMCP | 面向開發者平台 |
| Envoy AI Gateway | 開源；可客製的過濾器 |

階段 17（生產基礎設施）會更深入談閘道的維運。

## 框架應用

`code/main.py` 用約 150 行出貨了一個最小閘道：以一個假的 Bearer token 認證使用者、持有逐使用者的 RBAC 政策、把請求路由到兩台後端 MCP 伺服器、把每一次呼叫寫進稽核日誌、施行速率限制，並拒絕任何描述雜湊與釘選清單不符的後端工具。

要看的地方有：

- 以 `user_id` 為鍵、內含允許的 `server_tool` 項目的 `RBAC` dict。
- `AUDIT_LOG` 是一份唯附加的事件清單。
- 速率限制用的是每位使用者一個的權杖桶。
- 釘選清單是一個 `server::tool -> hash` 的 dict。

## 產出交付

這一課產出 `outputs/skill-gateway-bootstrap.md`。給定一份企業 MCP 規劃（使用者、後端、法遵），這項技能會產出一份閘道設定規格。

## 練習

1. 跑一次 `code/main.py`。以一位被允許的使用者發出呼叫；接著以一位被禁止的使用者；然後來一波超出速率限制的爆量。驗證這三條流程。

2. 加上一項政策，在把結果回傳給客戶端之前遮蔽掉 PII。用一次簡單的正規表示式掃描抓 SSN 形狀的字串；並註明其缺口（電子郵件、電話號碼）。

3. 擴充稽核日誌，讓它吐出 OpenTelemetry 的 GenAI span。階段 13 · 20 會談確切的屬性。

4. 為一支 50 人的開發團隊與五台後端（notes、github、postgres、jira、slack）設計一份 RBAC 政策。誰在每一台上拿到唯讀？誰拿到寫入？

5. 把 Cloudflare 那篇企業 MCP 文章從頭讀到尾。找出一項 Cloudflare 有出貨、而這個 stdlib 閘道沒有的功能。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| 閘道 | 「MCP 代理」 | 位於客戶端與後端之間、負責集中管理的伺服器 |
| 憑證保管 | 「後端 token 留在伺服器端」 | 開發者永遠看不到上游的 token |
| 感知工作階段的路由 | 「多後端工作階段」 | 閘道為每個開發者工作階段多工 N 個後端工作階段 |
| 工具雜湊釘選 | 「核准清單」 | 每一份已核准工具描述的 SHA256；集中擋下抽地毯 |
| RBAC | 「逐使用者政策」 | 針對工具與伺服器的角色式存取控制 |
| 政策即程式碼 | 「宣告式規則」 | 在閘道強制執行的 OPA/Rego、Kyverno、Styra 政策 |
| 稽核日誌 | 「何人、何事、何時」 | 供法遵使用的唯附加事件日誌 |
| 速率限制 | 「逐使用者的權杖桶」 | 用以防止濫用的每分鐘上限 |
| 官方 MCP 登錄 | 「權威上游」 | `registry.modelcontextprotocol.io`，經命名空間驗證 |
| 反向 DNS 命名 | 「登錄命名空間」 | `io.github.user/server` 這個慣例 |

## 延伸閱讀

- [Official MCP Registry](https://registry.modelcontextprotocol.io/) —— 權威上游，經命名空間驗證
- [Cloudflare — Enterprise MCP](https://blog.cloudflare.com/enterprise-mcp/) —— 帶 OAuth 與政策的閘道模式
- [agentic-community — MCP gateway registry](https://github.com/agentic-community/mcp-gateway-registry) —— 開源的參考閘道
- [TrueFoundry — What is an MCP gateway?](https://www.truefoundry.com/blog/what-is-mcp-gateway) —— 功能比較的文章
- [IBM — MCP context forge](https://github.com/IBM/mcp-context-forge) —— IBM 出品的企業閘道
