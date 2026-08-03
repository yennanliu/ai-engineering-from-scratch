# A2A —— 代理對代理協定

> MCP 是代理對工具。A2A（Agent2Agent）則是代理對代理 —— 一套讓建構在不同框架上的不透明代理彼此協作的開放協定。由 Google 於 2025 年 4 月釋出，2025 年 6 月捐給 Linux Foundation，並在 2026 年 4 月抵達 v1.0，擁有 150 個以上的支持者，包括 AWS、Cisco、Microsoft、Salesforce、SAP 與 ServiceNow。它吸收了 IBM 的 ACP，並加上了 AP2 付款擴充。這一課會走過 Agent Card、Task 生命週期，以及兩種傳輸繫結。

**類型：** 實作
**程式語言：** Python (stdlib, Agent Card + Task harness)
**先修單元：** 階段 13 · 06（MCP 基礎）、階段 13 · 08（MCP 客戶端）
**時間：** 約 75 分鐘

## 學習目標

- 分辨代理對工具（MCP）與代理對代理（A2A）的使用情境。
- 在 `/.well-known/agent.json` 發布一份帶技能與端點中繼資料的 Agent Card。
- 走過 Task 生命週期（submitted → working → input-required → completed／failed／canceled／rejected）。
- 使用帶 Part（text、file、data）的 Message，以及作為輸出的 Artifact。

## 問題所在

一個客服代理需要把撰寫報告委派給一個專門的寫作代理。A2A 之前的選項有：

- 客製 REST API。可行，但每一組配對都是一次性的。
- 共用同一份程式碼庫。這要求兩個代理跑同一個框架。
- MCP。不合適：MCP 是用來呼叫工具的，不是用來讓兩個代理在各自保有不透明內部推理的前提下協作的。

A2A 補上了這道缺口。它把互動建模成一個代理把一個 Task 送給另一個代理，並帶有生命週期、訊息與 artifact。被呼叫代理的內部狀態保持不透明 —— 呼叫方只看得到任務狀態的轉移與最終的輸出。

A2A 就是那套「讓跨框架的代理彼此對話」的協定。它並不取代 MCP；兩者是互補的。

## 核心概念

### Agent Card

每個符合 A2A 的代理都在 `/.well-known/agent.json` 發布一張卡片：

```json
{
  "schemaVersion": "1.0",
  "name": "research-agent",
  "description": "Summarizes academic papers and drafts citations.",
  "url": "https://research.example.com/a2a",
  "version": "1.2.0",
  "skills": [
    {
      "id": "summarize_paper",
      "name": "Summarize a paper",
      "description": "Read a paper PDF and produce a 3-paragraph summary.",
      "inputModes": ["text", "file"],
      "outputModes": ["text", "artifact"]
    }
  ],
  "capabilities": {"streaming": true, "pushNotifications": true}
}
```

探索是以 URL 為基礎的：抓取那張卡片、得知 A2A 端點的 URL、列舉技能。

### 簽章的 Agent Card（AP2）

AP2 擴充（2025 年 9 月）為 Agent Card 加上密碼學簽章。發布者用一個 JWT 為自己的卡片簽章；使用者驗證它。這能防止冒充。

### Task 生命週期

```
submitted -> working -> completed | failed | canceled | rejected
             -> input_required -> working (loop via message)
```

客戶端以 `tasks/send` 發起。被呼叫的代理在各狀態間轉移；客戶端則透過 SSE 訂閱狀態更新，或輪詢。

### Message 與 Part

一則訊息承載一個以上的 Part：

- `text` —— 純內容。
- `file` —— 帶 mimeType 的 base64 blob。
- `data` —— 定型的 JSON 酬載（給被呼叫代理的結構化輸入）。

範例：

```json
{
  "role": "user",
  "parts": [
    {"type": "text", "text": "Summarize this paper."},
    {"type": "file", "file": {"name": "paper.pdf", "mimeType": "application/pdf", "bytes": "..."}},
    {"type": "data", "data": {"targetLength": "3 paragraphs"}}
  ]
}
```

### Artifact

輸出是 Artifact，不是裸字串。一個 Artifact 是一份具名、定型的輸出：

```json
{
  "name": "summary",
  "parts": [{"type": "text", "text": "..."}],
  "mimeType": "text/markdown"
}
```

Artifact 可以分塊串流。呼叫方負責累積。

### 兩種傳輸繫結

1. **跑在 HTTP 上的 JSON-RPC。** `/a2a` 端點，用 POST 送請求，串流則選配 SSE。預設的繫結。
2. **gRPC。** 給那些原生就用 gRPC 的企業環境。

兩種繫結承載的邏輯訊息形狀相同。

### 不透明性的保留

一項關鍵的設計原則：被呼叫代理的內部狀態是不透明的。呼叫方看到的是任務狀態與 artifact。被呼叫代理的思維鏈、它的工具呼叫、它對子代理的委派 —— 全都看不見。這與 MCP 不同，MCP 的工具呼叫是透明的。

理由是：A2A 讓競爭對手能在不揭露內部的前提下協作。A2A 可以是「呼叫這個客服代理」，而呼叫方無從得知那個代理是怎麼實作這項服務的。

### 時間軸

- **2025-04-09。** Google 宣布 A2A。
- **2025-06-23。** 捐給 Linux Foundation。
- **2025-08。** 吸收 IBM 的 ACP。
- **2025-09。** AP2 擴充（Agent Payments）出貨。
- **2026-04。** v1.0 釋出，擁有 150 個以上的支持組織。

### 與 MCP 的關係

| 面向 | MCP | A2A |
|-----------|-----|-----|
| 使用情境 | 代理對工具 | 代理對代理 |
| 不透明性 | 透明的工具呼叫 | 不透明的內部推理 |
| 典型呼叫方 | 代理執行環境 | 另一個代理 |
| 狀態 | 工具呼叫的結果 | 帶生命週期的 Task |
| 授權 | OAuth 2.1（階段 13 · 16） | JWT 簽章的 Agent Card（AP2） |
| 傳輸 | Stdio／Streamable HTTP | 跑在 HTTP 上的 JSON-RPC／gRPC |

想呼叫某個特定工具時用 MCP。想把一整項任務委派給另一個代理時用 A2A。許多生產系統兩者都用：一個代理在工具層用 MCP，在協作層用 A2A。

```figure
a2a-task-lifecycle
```

## 框架應用

`code/main.py` 實作了一套最小的 A2A 測試框架：一個研究代理發布它的卡片，一個寫作代理收到一次 `tasks/send`，其中的 part 包含一份 PDF 與一段文字指令，接著它在 working → input_required → working → completed 之間轉移，最後回傳一份文字 artifact。全部用 stdlib；並用一個記憶體內傳輸，好把焦點放在訊息形狀上。

要看的地方有：

- Agent Card 的 JSON 形狀。
- Task id 的指派與狀態轉移。
- 帶混合型別 part 的訊息。
- 任務中途的 input-required 分支。
- 完成時回傳的 artifact。

## 產出交付

這一課產出 `outputs/skill-a2a-agent-spec.md`。給定一個應該能被其他代理呼叫的新代理，這項技能會產出 Agent Card 的 JSON、技能 schema 與端點藍圖。

## 練習

1. 跑一次 `code/main.py`。追蹤完整的 Task 生命週期，包括被呼叫代理索取澄清時那次 input-required 的暫停。

2. 加上一張簽章的 Agent Card。用 HMAC 對該卡片的標準 JSON 簽章。寫一個驗證器，確認它對被竄改的卡片會失敗。

3. 實作任務串流：寫作代理透過 SSE 吐出三個增量的 artifact 分塊，呼叫方把它們累積起來。

4. 設計一個包住某台 MCP 伺服器的 A2A 代理。把每一個 MCP 工具對映到一項 A2A 技能。記下其中的取捨 —— 什麼樣的不透明性被犧牲了？

5. 讀 A2A v1.0 的發布公告，找出截至 2026 年 4 月尚未被任何框架實作的那項功能。（提示：它和多跳任務委派有關。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| A2A | 「代理對代理協定」 | 供不透明代理協作的開放協定 |
| Agent Card | 「`.well-known/agent.json`」 | 描述一個代理的技能與端點的公開中繼資料 |
| Skill | 「一個可呼叫的單位」 | 該代理支援的具名操作（類比於 MCP 的工具） |
| Task | 「委派的單位」 | 帶生命週期與最終 artifact 的一件工作 |
| Message | 「任務輸入」 | 承載各個 Part（text、file、data） |
| Part | 「定型的一塊」 | 訊息中的 `text`／`file`／`data` 元素 |
| Artifact | 「任務輸出」 | 完成時回傳的具名、定型輸出 |
| AP2 | 「Agent Payments Protocol」 | 用於信任與付款的簽章 Agent Card 擴充 |
| 不透明性 | 「黑箱協作」 | 被呼叫代理的內部對呼叫方是隱藏的 |
| Input-required | 「任務暫停」 | 代理需要更多資訊時的生命週期狀態 |

## 延伸閱讀

- [a2a-protocol.org](https://a2a-protocol.org/latest/) —— 權威的 A2A 規格
- [a2aproject/A2A — GitHub](https://github.com/a2aproject/A2A) —— 參考實作與 SDK
- [Linux Foundation — A2A launch press release](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents) —— 2025 年 6 月的治理移轉
- [Google Cloud — A2A protocol upgrade](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade) —— 路線圖與夥伴動能
- [Google Dev — A2A 1.0 milestone](https://discuss.google.dev/t/the-a2a-1-0-milestone-ensuring-and-testing-backward-compatibility/352258) —— v1.0 發布說明與向後相容的指引
