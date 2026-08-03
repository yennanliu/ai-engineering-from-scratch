# MCP Sampling —— 由伺服器發起的 LLM 補全與代理迴圈

> 多數 MCP 伺服器都是笨執行器：收參數、跑程式碼、回傳內容。Sampling 讓伺服器能把方向反過來：由它去請客戶端的 LLM 做決定。這使得伺服器能託管代理迴圈，卻不必自己持有任何模型憑證。SEP-1577 在 2025-11-25 併入，讓 sampling 請求裡能帶工具，好讓那個迴圈納入更深的推理。漂移風險提醒：SEP-1577 那個「sampling 中帶工具」的形狀，一路到 2026 年第一季都還是實驗性的，在各 SDK 的 API 中仍在定型當中。

**類型：** 實作
**程式語言：** Python (stdlib, sampling harness)
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 10（資源與提示詞）
**時間：** 約 75 分鐘

## 學習目標

- 說明 `sampling/createMessage` 解決了什麼（讓伺服器託管迴圈，卻不必在伺服器端放 API 金鑰）。
- 實作一台伺服器，請客戶端對一段多輪提示詞取樣，並回傳補全結果。
- 用 `modelPreferences`（成本／速度／智能的優先權）引導客戶端挑選模型。
- 做一個 `summarize_repo` 工具，讓它靠 sampling 在內部迭代，而不是把行為寫死。

## 問題所在

一台實用的、支撐程式碼摘要工作流程的 MCP 伺服器需要做到：走訪檔案樹、挑出要讀哪些檔案、合成一份摘要、回傳。那 LLM 的推理發生在哪裡？

選項 A：伺服器呼叫自己的 LLM。需要 API 金鑰、費用記在伺服器端，而且每位使用者都很貴。

選項 B：伺服器回傳原始內容；由客戶端的代理去推理。可行，但這把伺服器邏輯搬進了客戶端的提示詞，很脆弱。

選項 C：伺服器透過 `sampling/createMessage` 去問客戶端的 LLM。伺服器保有演算法（讀哪些檔案、跑幾輪），客戶端則保有計費與模型選擇。伺服器完全不持有任何憑證。

Sampling 就是選項 C。它是一種機制，讓一台受信任的伺服器能託管代理迴圈，而自己不必成為一個完整的 LLM 宿主。

## 核心概念

### `sampling/createMessage` 請求

伺服器送出：

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "sampling/createMessage",
  "params": {
    "messages": [{"role": "user", "content": {"type": "text", "text": "..."}}],
    "systemPrompt": "...",
    "includeContext": "none",
    "modelPreferences": {
      "costPriority": 0.3,
      "speedPriority": 0.2,
      "intelligencePriority": 0.5,
      "hints": [{"name": "claude-3-5-sonnet"}]
    },
    "maxTokens": 1024
  }
}
```

客戶端跑它的 LLM，然後回傳：

```json
{"jsonrpc": "2.0", "id": 42, "result": {
  "role": "assistant",
  "content": {"type": "text", "text": "..."},
  "model": "claude-3-5-sonnet-20251022",
  "stopReason": "endTurn"
}}
```

### `modelPreferences`

三個加總為 1.0 的浮點數：

- `costPriority`：偏好較便宜的模型。
- `speedPriority`：偏好較快的模型。
- `intelligencePriority`：偏好能力較強的模型。

另外還有 `hints`：伺服器偏好的具名模型。客戶端可以理會也可以不理會這些提示；使用者在客戶端的設定永遠優先。

### `includeContext`

三種取值：

- `"none"` —— 只用伺服器提供的訊息。預設值。
- `"thisServer"` —— 納入這台伺服器工作階段中先前的訊息。
- `"allServers"` —— 納入所有工作階段的上下文。

自 2025-11-25 起，`includeContext` 被軟性棄用，因為它會洩漏跨伺服器的上下文，構成安全疑慮。請優先用 `"none"`，並把明確的上下文放進訊息裡傳。

### 帶工具的 sampling（SEP-1577）

2025-11-25 新增：sampling 請求可以帶一個 `tools` 陣列。客戶端會用那些工具跑一整輪完整的工具呼叫迴圈。這讓伺服器能透過客戶端的模型，託管一個 ReAct 風格的代理迴圈。

```json
{
  "messages": [...],
  "tools": [
    {"name": "fetch_url", "description": "...", "inputSchema": {...}}
  ]
}
```

客戶端就這樣繞：取樣、若有呼叫就執行工具、再取樣、回傳最終的 assistant 訊息。這一路到 2026 年第一季都還是實驗性的；SDK 的簽章仍可能漂移。實作時請對照 2025-11-25 版規格的 client/sampling 章節確認。

### 人在迴圈中

客戶端在跑那次取樣之前，「必須」讓使用者看到伺服器打算叫模型做什麼。惡意伺服器可能用 sampling 來操弄使用者的工作階段（「對使用者說 X，好讓他們去點 Y」）。Claude Desktop、VS Code 與 Cursor 都會把 sampling 請求呈現成一個使用者可以拒絕的確認對話框。

2026 年的共識是：沒有人工確認的 sampling 是一面紅旗。閘道（階段 13 · 17）可以自動核准低風險的 sampling，並自動拒絕任何可疑的。

### 不用 API 金鑰的伺服器託管迴圈

那個典型的使用情境：一台自己完全沒有 LLM 存取權的程式碼摘要 MCP 伺服器。它會：

1. 走訪儲存庫的結構。
2. 帶著「挑出最可能描述這個儲存庫用途的五個檔案」呼叫 `sampling/createMessage`。
3. 讀取那些檔案。
4. 帶著那些檔案的內容與「用 3 段話摘要這個儲存庫」再呼叫一次 `sampling/createMessage`。
5. 把摘要當成 `tools/call` 的結果回傳。

伺服器從頭到尾沒碰過任何 LLM API。是客戶端的使用者用自己的憑證，付了那些補全的錢。

### 安全風險（Unit 42 於 2026 年第一季揭露）

- **隱蔽取樣。** 一個總是帶著「從工作階段上下文中回覆使用者的電子郵件」去呼叫 sampling 的工具。階段 13 · 15 會談這些攻擊向量。
- **透過 sampling 竊取資源。** 伺服器請客戶端去摘要攻擊者的酬載，帳單卻算在使用者頭上。
- **迴圈炸彈。** 伺服器在一個緊迴圈裡不停呼叫 sampling。客戶端「必須」落實每個工作階段的速率限制。

```figure
t3-sampling-flip
```

## 框架應用

`code/main.py` 出貨了一套假的伺服器對客戶端 sampling 測試框架。一個模擬的「summarize_repo」工具會發動兩輪取樣（先挑檔案、再摘要），假客戶端則回傳罐頭回應。這套框架展示了：

- 伺服器帶著 `modelPreferences` 送出 `sampling/createMessage`。
- 客戶端回傳一份補全。
- 伺服器繼續它的迴圈。
- 速率限制器為每次工具呼叫的總取樣次數設上限。

要看的地方有：

- 這台伺服器只暴露一個工具（`summarize_repo`）；所有推理都發生在那些 sampling 呼叫裡。
- 模型偏好會為客戶端的模型選擇加權；hints 則列出偏好的模型。
- 迴圈在 `stopReason: "endTurn"` 時終止。
- `max_samples_per_tool = 5` 這個上限攔下了一個失控的迴圈。

## 產出交付

這一課產出 `outputs/skill-sampling-loop-designer.md`。給定一套需要 LLM 呼叫的伺服器端演算法（研究、摘要、規劃），這項技能會設計出一個基於 sampling 的實作，搭配恰當的 modelPreferences、速率限制與安全確認。

## 練習

1. 跑一次 `code/main.py`。把 `max_samples_per_tool` 改成 2，觀察速率限制的切斷點。

2. 實作 SEP-1577 那個「sampling 中帶工具」的變體：sampling 請求帶一個 `tools` 陣列。驗證客戶端那側的迴圈會在回傳最終補全之前先執行那些工具。注意漂移風險：SDK 簽章一路到 2026 年上半年都還可能改變。

3. 加上人在迴圈中的確認：在伺服器第一次 `sampling/createMessage` 之前，暫停並等待使用者核准。被拒絕的呼叫回傳一個定型的拒絕。

4. 加上一個以客戶端工作階段為鍵的每使用者速率限制器。同一使用者對同一台伺服器的迴圈，應該共用同一份預算。

5. 設計一個 `summarize_pdf` 工具，用 sampling 來挑要納入哪些區塊。勾勒出送出的那些訊息。當 `modelPreferences.intelligencePriority` 是 0.1 與 0.9 時，行為各有什麼不同？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| Sampling | 「伺服器對客戶端的 LLM 呼叫」 | 伺服器向客戶端的模型索取一份補全 |
| `sampling/createMessage` | 「那個方法」 | 用於 sampling 請求的 JSON-RPC 方法 |
| `modelPreferences` | 「模型優先權」 | 成本／速度／智能的權重，加上名稱提示 |
| `includeContext` | 「跨工作階段洩漏」 | 已被軟性棄用的上下文納入模式 |
| SEP-1577 | 「sampling 中的工具」 | 允許在 sampling 中帶工具，以支撐伺服器託管的 ReAct |
| 人在迴圈中 | 「使用者確認」 | 客戶端在執行前把 sampling 請求呈現給使用者 |
| 迴圈炸彈 | 「失控的取樣」 | 伺服器端的無限取樣迴圈；客戶端必須做速率限制 |
| 隱蔽取樣 | 「藏起來的推理」 | 惡意伺服器把意圖藏在 sampling 提示詞裡 |
| 資源竊取 | 「花掉使用者的 LLM 預算」 | 伺服器逼客戶端為它不想要的 sampling 付費 |
| `stopReason` | 「生成為何停止」 | `endTurn`、`stopSequence` 或 `maxTokens` |

## 延伸閱讀

- [MCP — Concepts: Sampling](https://modelcontextprotocol.io/docs/concepts/sampling) —— sampling 的高階概覽
- [MCP — Client sampling spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling) —— `sampling/createMessage` 的權威形狀
- [MCP — GitHub SEP-1577](https://github.com/modelcontextprotocol/modelcontextprotocol) —— sampling 中帶工具的 Spec Evolution Proposal（實驗性）
- [Unit 42 — MCP attack vectors](https://unit42.paloaltonetworks.com/model-context-protocol-attack-vectors/) —— 隱蔽取樣與資源竊取的模式
- [Speakeasy — MCP sampling core concept](https://www.speakeasy.com/mcp/core-concepts/sampling) —— 附客戶端程式碼範例的逐步說明
