# 總結專案 —— 打造一套完整的工具生態系

> 階段 13 把每一塊零件都教過了。這個總結專案要把它們接成一套生產形狀的系統：一台帶工具 + 資源 + 提示詞 + task + UI 的 MCP 伺服器、邊緣的 OAuth 2.1、一個 RBAC 閘道、一個多伺服器客戶端、一次 A2A 子代理呼叫、送進收集器的 OTel 追蹤、CI 中的工具下毒偵測，以及一份 AGENTS.md + SKILL.md 套組。做完之後，你能為每一項架構選擇辯護。

**類型：** 實作
**程式語言：** Python (stdlib, end-to-end ecosystem harness)
**先修單元：** 階段 13 · 01 到 21
**時間：** 約 120 分鐘

## 學習目標

- 組出一台暴露工具、資源、提示詞，以及一個帶 `ui://` 應用之 task 的 MCP 伺服器。
- 在伺服器前面擺一個強制 RBAC 與釘選雜湊的 OAuth 2.1 閘道。
- 寫一個多伺服器客戶端，用 OTel GenAI 屬性做端到端追蹤。
- 把部分工作負載委派給一個 A2A 子代理；驗證不透明性有被保留。
- 用 AGENTS.md + SKILL.md 把整套堆疊打包起來，好讓其他代理也能驅動它。

## 問題所在

出貨這套「研究並產出報告」系統：

- 使用者問：「摘要 2026 年 arXiv 上關於代理協定、被引用最多的三篇論文。」
- 系統：透過 MCP 搜尋 arXiv；透過 A2A 把論文摘要委派給一個專門的寫作代理；彙總結果；把互動式報告渲染成一個 MCP Apps 的 `ui://` 資源；並把每一步都記進 OTel。

階段 13 的所有原語都登場了。這不是玩具 —— 2026 年由 Anthropic（Claude Research 產品）、OpenAI（搭配 Apps SDK 的 GPTs）與第三方出貨的生產級研究助理系統，形狀就是這樣。

## 核心概念

### 架構

```
[user] -> [client] -> [gateway (OAuth 2.1 + RBAC)] -> [research MCP server]
                                                      |
                                                      +- MCP tool: arxiv_search (pure)
                                                      +- MCP resource: notes://recent
                                                      +- MCP prompt: /research_topic
                                                      +- MCP task: generate_report (long)
                                                      +- MCP Apps UI: ui://report/current
                                                      +- A2A call: writer-agent (tasks/send)
                                                      |
                                                      +- OTel GenAI spans
```

### 追蹤階層

```
agent.invoke_agent
 ├── llm.chat (kick off)
 ├── mcp.call -> tools/call arxiv_search
 ├── mcp.call -> resources/read notes://recent
 ├── mcp.call -> prompts/get research_topic
 ├── a2a.tasks/send -> writer-agent
 │    └── task transitions (opaque internals)
 ├── mcp.call -> tools/call generate_report (task-augmented)
 │    └── tasks/status polling
 │    └── tasks/result (completed, returns ui:// resource)
 └── llm.chat (final synthesis)
```

單一個 trace id。每個 span 都帶著正確的 `gen_ai.*` 屬性。

### 安全態勢

- OAuth 2.1 + PKCE，並以資源指示子把受眾釘在閘道上。
- 閘道持有上游憑證；使用者永遠看不到它們。
- RBAC：`alice` 有 `research:read`、`research:write`，可以呼叫所有工具。`bob` 只有 `research:read`，不能呼叫 `generate_report`。
- 釘選的描述清單：任何工具雜湊變動過的伺服器都會被丟掉。
- 二選二規則的稽核：沒有任何工具同時湊齊不可信輸入、敏感資料與有後果的動作。

### 渲染

最後那個 `generate_report` task 回傳的是內容區塊，加上一個 `ui://report/current` 資源。客戶端的宿主（Claude Desktop 等）會在沙箱 iframe 中渲染那個互動式儀表板。儀表板裡有一份排序過的論文清單、引用次數，以及一個按鈕 —— 使用者點任何一篇論文，它就呼叫 `host.callTool('summarize_paper', {arxiv_id})`。

### 打包

整套東西以這樣的形式出貨：

```
research-system/
  AGENTS.md                     # project conventions
  skills/
    run-research/
      SKILL.md                  # the top-level workflow
  servers/
    research-mcp/               # the MCP server
      pyproject.toml
      src/
  agents/
    writer/                     # the A2A agent
  gateway/
    config.yaml                 # RBAC + pinned manifest
```

使用者以 `docker compose up` 部署。Claude Code、Cursor、Codex 與 opencode 的使用者，只要調用 `run-research` 這項技能就能驅動整套系統。

### 階段 13 各課各貢獻了什麼

| 單元 | 總結專案用到了什麼 |
|--------|------------------------|
| 01-05 | 工具介面、供應商可攜性、平行呼叫、schema、lint |
| 06-10 | MCP 原語、伺服器、客戶端、傳輸、資源 + 提示詞 |
| 11-14 | Sampling、roots + elicitation、非同步 task、`ui://` 應用 |
| 15-17 | 工具下毒、OAuth 2.1、閘道 + 登錄 |
| 18 | A2A 子代理委派 |
| 19 | OTel GenAI 追蹤 |
| 20 | LLM 層的路由閘道 |
| 21 | SKILL.md + AGENTS.md 打包 |

## 框架應用

`code/main.py` 把前面各課的模式縫成一份可執行的示範。全部 stdlib、全部在同一個行程內，好讓你從頭讀到尾。它把「研究並產出報告」這個情境的完整流程跑一遍：與閘道握手、模擬 OAuth 2.1、合併 tools/list、把 generate_report 當成 task、對寫作代理發 A2A 呼叫、回傳 ui:// 資源、吐出 OTel span。

要看的地方有：

- 橫跨每一次跳轉的單一個 trace id。
- 閘道政策擋下第二位使用者的寫入。
- Task 生命週期走過 working → completed，並同時回傳文字與 ui:// 內容。
- A2A 呼叫的內部狀態對編排者是不透明的。
- AGENTS.md 與 SKILL.md 是另一個代理重現這套工作流程時唯一需要的檔案。

## 產出交付

這一課產出 `outputs/skill-ecosystem-blueprint.md`。給定一項產品需求（研究、摘要、自動化），這項技能會產出完整的架構：用哪些 MCP 原語、哪些閘道控制、哪些 A2A 呼叫、哪些遙測、以及怎麼打包。

## 練習

1. 跑一次 `code/main.py`。留意那個單一的 trace id 與 span 如何巢狀。數一數這份示範觸及了階段 13 的多少個原語。

2. 擴充這份示範：加上第二台後端 MCP 伺服器（例如 `bibliography`），並確認閘道把它的工具合併進同一個命名空間。

3. 把那個假的 A2A 寫作代理換成一個真正跑在子行程上的。用單元 19 的測試框架。

4. 在編排者與 LLM 之間的路由閘道裡，加上一道 PII 遮蔽步驟。確認使用者查詢中的電子郵件會被清掉。

5. 為一位將要維護這套系統的隊友寫一份 AGENTS.md。它應該五分鐘之內讀得完，並給他們在 Cursor 或 Codex 中驅動這個總結專案所需的一切。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| 總結專案 | 「階段 13 的整合示範」 | 用上每一個原語的端到端系統 |
| 研究並產出報告 | 「那個情境」 | 搜尋、摘要、渲染這套模式 |
| 生態系 | 「所有零件湊在一起」 | 伺服器 + 客戶端 + 閘道 + 子代理 + 遙測 + 打包 |
| 追蹤階層 | 「單一個 trace id」 | 每一次跳轉的 span 共用同一條追蹤；父子關係靠 span id |
| 閘道簽發的 token | 「遞移式認證」 | 客戶端只看得到閘道的 token；閘道持有上游憑證 |
| 合併命名空間 | 「所有工具攤成一份清單」 | 在閘道做多伺服器合併，衝突時加前綴 |
| 不透明邊界 | 「A2A 呼叫藏住內部」 | 子代理的推理對編排者不可見 |
| 三層堆疊 | 「AGENTS.md + SKILL.md + MCP」 | 專案上下文 + 工作流程 + 工具 |
| 縱深防禦 | 「多層安全」 | 釘選雜湊、OAuth、RBAC、二選二規則、稽核日誌 |
| 規格合規矩陣 | 「我們出貨的東西對上規格的要求」 | 把交付物對映到 2025-11-25 各項要求的檢查清單 |

## 延伸閱讀

- [MCP — Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) —— 整併過的參考
- [MCP blog — 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) —— 這份協定要往哪裡走
- [a2a-protocol.org](https://a2a-protocol.org/latest/) —— A2A v1.0 參考
- [OpenTelemetry — GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/) —— 權威的追蹤慣例
- [Anthropic — Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) —— 生產級代理執行環境的模式
