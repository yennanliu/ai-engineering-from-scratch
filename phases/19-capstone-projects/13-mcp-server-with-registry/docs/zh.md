# 綜合專案 13 —— 帶登錄庫與治理的 MCP 伺服器

> Model Context Protocol 在 2026 年不再是未來，而成了預設的工具使用規格。Anthropic、OpenAI、Google，以及每一個主要 IDE 都出貨了 MCP 客戶端。Pinterest 發表了它內部的 MCP 伺服器生態系。AAIF 登錄庫把能力中繼資料形式化到 `.well-known` 上。AWS ECS 發表了那份參考的無狀態部署。Block 的 goose-agent 把同一套協定放進了一個託管助理裡。2026 年的生產形狀是：StreamableHTTP 傳輸、OAuth 2.1 範圍、OPA 政策把關，以及一個讓平台團隊得以發現、驗證與啟用伺服器的登錄庫。把這一整套從頭到尾建出來。

**類型：** 綜合專案
**程式語言：** Python (server, via FastMCP) or TypeScript (@modelcontextprotocol/sdk), Go (registry service)
**先修單元：** 階段 11（LLM 工程）、階段 13（工具與 MCP）、階段 14（代理）、階段 17（基礎設施）、階段 18（安全）
**演練到的階段：** P11 · P13 · P14 · P17 · P18
**時間：** 25 小時

## 問題

MCP 成了工具使用的通用語。Claude Code、Cursor 3、Amp、OpenCode、Gemini CLI，以及每一個託管代理現在都消費 MCP 伺服器。生產上的挑戰不在寫伺服器（FastMCP 讓那件事很簡單），而在帶著企業需求把它們大規模部署出去：逐租戶的 OAuth 範圍、對破壞性工具的 OPA 政策、StreamableHTTP 的無狀態擴縮、一個供發現用的登錄庫、逐工具呼叫的稽核日誌。Pinterest 的內部 MCP 生態系與 AAIF 登錄庫規格立下了 2026 年的標準。

你會建一台暴露 10 個內部工具（Postgres 唯讀、S3 列表、Jira、Linear、Datadog 等等）的 MCP 伺服器、一個供平台發現用的登錄庫 UI，以及一道給破壞性工具用的人類核可閘門。負載測試示範 StreamableHTTP 的水平擴縮。稽核軌跡則要通得過企業資安審查。

## 概念

MCP 2026 修訂版把 StreamableHTTP 定為預設傳輸。與早先那套 stdio 加 SSE 的形狀不同，StreamableHTTP 預設是無狀態的：單一個 HTTP 端點接受 JSON-RPC 請求、串流回應，並支援供通知使用的長生命週期連線。無狀態意味著可以在負載平衡器後面水平擴縮。

授權是 OAuth 2.1 配逐工具的範圍。一個權杖帶著像 `jira:read`、`s3:list`、`postgres:query:readonly` 這樣的範圍。MCP 伺服器在工具呼叫當下檢查範圍，不只是在工作階段開始時檢查。對高風險工具，伺服器會拒絕任何「範圍未在最近 N 分鐘內被提升為 `approved:by:human`」的呼叫 —— 而那次提升來自一張 Slack 審查卡片。

登錄庫是一個獨立的服務。每一台 MCP 伺服器都暴露一份 `.well-known/mcp-capabilities` 文件，帶著它的工具清單、傳輸網址、認證需求。登錄庫去輪詢、驗證並建索引。平台團隊透過登錄庫 UI 看見有哪些工具可用、它們需要什麼範圍，以及哪個團隊擁有它們。

## 架構

```
MCP client (Claude Code, Cursor 3, ...)
          |
          v
StreamableHTTP over HTTPS (JSON-RPC + streaming)
          |
          v
MCP server (FastMCP) behind load balancer
          |
   +------+------+---------+----------+------------+
   v             v         v          v            v
Postgres    S3 listing  Jira       Linear     Datadog
(read-only) (paged)     (read)     (read)     (query)
          |
   +------+-------------+
   v                    v
 OPA policy gate   destructive tool MCP (separate server)
                        |
                        v
                   human approval via Slack
                        |
                        v
                   audit log (append-only, per-tenant)

  registry service
     |
     v  GET /.well-known/mcp-capabilities from each server
     v
     UI: search / validate / enable-disable / ownership
```

## 技術堆疊

- 伺服器框架：FastMCP（Python）或 `@modelcontextprotocol/sdk`（TypeScript）
- 傳輸：跑在 HTTPS 上的 StreamableHTTP（無狀態）
- 認證：OAuth 2.1，工作負載身分透過 SPIFFE / SPIRE
- 政策：逐工具的 OPA / Rego 規則；每個請求都呼叫政策決策服務
- 登錄庫：自架，消費 `.well-known/mcp-capabilities` 清單
- 人類核可：破壞性工具走 Slack 互動訊息
- 部署：AWS ECS Fargate 或 Fly.io，每租戶一台伺服器，或共用但做租戶範圍隔離
- 稽核：逐租戶儲存桶的結構化 JSONL，帶逐次呼叫的血統

## 動手建

1. **工具介面。** 暴露 10 個內部工具：Postgres 唯讀查詢、S3 列出物件、Jira 搜尋／取回、Linear 搜尋／取回、Datadog 指標查詢、PagerDuty 待命查詢、GitHub 唯讀、Notion 搜尋、Slack 搜尋、Salesforce 讀取。每個工具都有一份有型別的 schema 與一個範圍標籤。

2. **FastMCP 伺服器。** 掛載那些工具。設定 StreamableHTTP 傳輸。加上一層中介軟體做 OAuth 權杖內省與範圍強制。

3. **OPA 政策。** 逐工具的 Rego 政策：什麼範圍才准許呼叫、套用什麼 PII 遮蔽、套用什麼酬載大小上限。每次工具呼叫都呼叫決策服務。

4. **登錄庫服務。** 一個獨立的 Go 或 TS 服務，向已註冊的伺服器輪詢 `.well-known/mcp-capabilities`、用 JSON Schema 驗證，並暴露一個列出／搜尋／驗證／啟用停用的 UI。

5. **能力清單。** 每台伺服器都暴露 `.well-known/mcp-capabilities`，帶著：工具清單、認證需求、傳輸網址、擁有團隊、SLO。

6. **破壞性工具的分離。** 會改變狀態的工具（Jira 建立、Linear 建立、Postgres 寫入）放在第二台 MCP 伺服器上，走更嚴的認證流程：權杖必須帶著在 15 分鐘內經 Slack 卡片提升的 `approved:by:human` 範圍。

7. **稽核日誌。** 逐租戶、只能追加的 JSONL：`{timestamp, user, tool, args_redacted, response_redacted, outcome}`。寫入前先用 Presidio 做 PII 遮蔽。

8. **負載測試。** 100 個並行客戶端跑 StreamableHTTP。加上第二個副本以示範水平擴縮；展示負載平衡器在沒有工作階段黏著的情況下重新分配流量。

9. **一致性測試。** 對這兩台伺服器跑官方的 MCP 一致性測試套件。通過所有必要章節。

## 動手用

```
$ curl -H "Authorization: Bearer eyJhbGc..." \
       -X POST https://mcp.internal.example.com/ \
       -d '{"jsonrpc":"2.0","method":"tools/call",
            "params":{"name":"postgres.readonly","arguments":{"sql":"SELECT 1"}}}'
[registry]   capability validated: postgres.readonly v1.2
[policy]    scope postgres:query:readonly present; allowed
[audit]     logged: user=u42 tool=postgres.readonly outcome=ok
response:    { "result": { "rows": [[1]] } }
```

## 產出交付

`outputs/skill-mcp-server.md` 描述那份交付物。一台供內部工具使用、帶 OAuth 2.1 範圍與 OPA 把關的生產級 MCP 伺服器 + 登錄庫 + 稽核層。

| 權重 | 判準 | 怎麼量 |
|:-:|---|---|
| 25 | 規格一致性 | StreamableHTTP + 能力清單通過 MCP 一致性測試 |
| 20 | 安全性 | 範圍強制、OPA 對每個工具的涵蓋率、密鑰衛生 |
| 20 | 可觀測性 | 帶 PII 遮蔽的逐工具呼叫稽核日誌 |
| 20 | 規模 | 100 客戶端負載測試的水平擴縮示範 |
| 15 | 登錄庫使用體驗 | 發現／驗證／啟用停用的工作流程 |
| **100** | | |

## 練習

1. 加上一個新工具（Confluence 搜尋）。讓它走完登錄庫的驗證流程出貨，而不動到核心伺服器。

2. 寫一條 OPA 政策，把 Postgres 查詢結果中欄位名為 `email`、`ssn` 或 `phone` 的內容遮掉。用一則探測查詢演練它。

3. 在本地延遲上對 StreamableHTTP 與 stdio 做基準測試。回報逐次呼叫的 p50/p95。

4. 實作逐租戶配額：每租戶每工具每分鐘最多 N 次呼叫。用第二條 OPA 規則強制執行。

5. 從 [mcp-conformance-tests](https://github.com/modelcontextprotocol/conformance) 跑 MCP 一致性測試套件，並把每一項失敗都修掉。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|-----------------|------------------------|
| StreamableHTTP | 「2026 年的 MCP 傳輸」 | 無狀態 HTTP + 串流；替網路伺服器取代了 SSE + stdio |
| 能力清單 | 「well-known 文件」 | `.well-known/mcp-capabilities`，帶工具清單、認證、傳輸網址 |
| OPA / Rego | 「政策引擎」 | Open Policy Agent，依外部規則替工具呼叫做授權 |
| 範圍提升 | 「經人類核可」 | 透過 Slack 核可授予的短生命週期範圍，破壞性工具必備 |
| 登錄庫 | 「工具發現」 | 從各台 MCP 伺服器的能力清單建索引的服務 |
| 工作負載身分 | 「SPIFFE / SPIRE」 | 供 OAuth 權杖簽發使用的密碼學服務身分 |
| 一致性套件 | 「規格測試」 | 官方的 MCP 測試組，檢驗 StreamableHTTP + 工具清單的正確性 |

## 延伸閱讀

- [Model Context Protocol 2026 Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) —— StreamableHTTP、能力中繼資料、登錄庫
- [AAIF MCP Registry spec](https://github.com/modelcontextprotocol/registry) —— 2026 年的登錄庫規格
- [AWS ECS reference deployment](https://aws.amazon.com/blogs/containers/deploying-model-context-protocol-mcp-servers-on-amazon-ecs/) —— 參考用的生產部署
- [Pinterest internal MCP ecosystem](https://www.infoq.com/news/2026/04/pinterest-mcp-ecosystem/) —— 內部部署的參考
- [Block `goose` MCP usage](https://block.github.io/goose/) —— 代理端消費模式的參考
- [FastMCP](https://github.com/jlowin/fastmcp) —— Python 的伺服器框架
- [Open Policy Agent](https://www.openpolicyagent.org/) —— 政策引擎的參考
- [SPIFFE / SPIRE](https://spiffe.io) —— 工作負載身分的參考
