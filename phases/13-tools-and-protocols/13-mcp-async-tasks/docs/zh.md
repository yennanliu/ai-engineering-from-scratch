# 非同步 Tasks（SEP-1686）—— 長時間工作的「先呼叫、後取回」

> 真正的代理工作要跑上幾分鐘到幾小時：CI 執行、深度研究的合成、批次匯出。同步的工具呼叫會斷線、逾時，或把 UI 卡住。SEP-1686 在 2025-11-25 併入，加上了 Tasks 這個原語：任何請求都能被加值成一個 task，其結果可以稍後取回，或透過狀態通知串流出來。漂移風險提醒：Tasks 一路到 2026 年上半年都還是實驗性的；SDK 的表面仍在圍繞規格設計當中。

**類型：** 實作
**程式語言：** Python (stdlib, async task state machine)
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 09（傳輸）
**時間：** 約 75 分鐘

## 學習目標

- 判斷什麼時候該把一個工具從同步升級成 task 加值型（伺服器端工作超過 30 秒）。
- 走過 task 的生命週期：`working` → `input_required` → `completed`／`failed`／`cancelled`。
- 把 task 狀態持久化，好讓崩潰不會弄丟進行中的工作。
- 正確地輪詢 `tasks/status` 並取回 `tasks/result`。

## 問題所在

一個 `generate_report` 工具跑的是一條要好幾分鐘的抽取管線。在同步模型下的選項有：

1. 讓連線開著三分鐘。遠端傳輸會把它切掉；客戶端會逾時；UI 會凍住。
2. 立刻回傳一個佔位符；要求客戶端去輪詢一個自訂端點。這破壞了 MCP 的一致性。
3. 射後不理；沒有結果。

沒有一個是好的。SEP-1686 加上了第四種：task 加值。任何請求（通常是 `tools/call`）都能被標記成一個 task。伺服器立刻回傳一個 task id。客戶端輪詢 `tasks/status`，完成後再取回 `tasks/result`。伺服器端的狀態能撐過重啟。

## 核心概念

### Task 加值

把 `params._meta.task.required` 設成 `true`（或 `optional: true`，由伺服器決定），一個請求就成了 task。伺服器立刻回應：

```json
{
  "jsonrpc": "2.0", "id": 1,
  "result": {
    "_meta": {
      "task": {
        "id": "tsk_9f7b...",
        "state": "working",
        "ttl": 900000
      }
    }
  }
}
```

`ttl` 是伺服器對保留狀態的承諾；ttl 之後 task 結果就會被丟棄。

### 逐工具選擇加入

工具註記可以宣告 task 支援：

- `taskSupport: "forbidden"` —— 這個工具永遠同步執行。對快速工具是安全的。
- `taskSupport: "optional"` —— 客戶端可以請求 task 加值。
- `taskSupport: "required"` —— 客戶端「必須」使用 task 加值。

一個 `generate_report` 工具會是 `required`。一個 `notes_search` 工具會是 `forbidden`。

### 狀態

```
working  -> input_required -> working  (loop via elicitation)
working  -> completed
working  -> failed
working  -> cancelled
```

這個狀態機是唯附加的：一旦進入 `completed`、`failed` 或 `cancelled`，該 task 就是終態。

### 方法

- `tasks/status {taskId}` —— 回傳當前狀態與一個進度提示。
- `tasks/result {taskId}` —— 阻塞等待，或在尚未完成時回 404。
- `tasks/cancel {taskId}` —— 冪等；終態會忽略它。
- `tasks/list` —— 選配；列舉活躍與最近完成的 task。

### 串流狀態變化

當伺服器支援時，客戶端可以訂閱狀態通知：

```
server -> notifications/tasks/updated {taskId, state, progress?}
```

改用串流而非輪詢的客戶端，UX 會更好。輪詢則永遠作為最小表面被支援。

### 持久化狀態

規格要求宣告支援 task 的伺服器必須把狀態持久化。在 ttl 之內，一次崩潰不應該弄丟已完成的結果。儲存方案從 SQLite 到 Redis 到檔案系統都有。單元 13 的測試框架用的是檔案系統。

### 取消的語意

`tasks/cancel` 是冪等的。如果那個 task 正在執行中，伺服器會嘗試把它停下來（要看執行器是否配合取消）。如果已經是終態，這個請求就是空操作。

### 崩潰復原

當伺服器行程重啟時：

1. 載入所有持久化的 task 狀態。
2. 把任何行程已死的 `working` task 標記成 `failed`，錯誤為 `CRASH_RECOVERY`。
3. 在 ttl 之內保留 `completed`／`failed`／`cancelled`。

### 非同步 tasks 加上 sampling

一個 task 本身也能呼叫 `sampling/createMessage`。長時間執行的研究型 task 就是這樣運作的：伺服器的 task 執行緒依需要對客戶端的模型取樣，而客戶端的 UI 則把那個 task 顯示成 `working`，並定期更新進度。

### 這為什麼還是實驗性的

SEP-1686 在 2025-11-25 出貨，但更大的路線圖點出了三個未決問題：持久化訂閱的原語、子任務（父子 task 關係），以及結果 TTL 的標準化。預期這份規格在 2026 年間還會演化。生產程式碼只該把 Tasks 當成在常見情境下穩定，並為子任務相關的未來 SDK 變動做好防護。

```figure
tp-task-lifecycle
```

## 框架應用

`code/main.py` 實作了一個持久化的 task 儲存（以檔案系統為後端），以及一個跑在背景執行緒的 `generate_report` 工具。客戶端呼叫該工具，立刻拿到一個 task id，在工作者更新進度的同時輪詢 `tasks/status`，完成後再取回 `tasks/result`。取消是可用的；崩潰復原則以殺掉工作者執行緒再重新載入狀態的方式模擬。

要看的地方有：

- Task 狀態 JSON 被持久化到 `/tmp/lesson-13-tasks/<id>.json`。
- 工作者執行緒更新 `progress` 欄位；輪詢時看得到它在前進。
- 從客戶端發起的取消會設下一個事件；工作者檢查到就提早退出。
- 「崩潰」後重新載入狀態，會把進行中的那個 task 標記成 `failed` 並附上 `CRASH_RECOVERY`。

## 產出交付

這一課產出 `outputs/skill-task-store-designer.md`。給定一個長時間執行的工具（研究、建置、匯出），這項技能會設計出那個 task 儲存（狀態形狀、ttl、持久性）、挑出正確的 taskSupport 旗標，並勾勒出進度通知。

## 練習

1. 跑一次 `code/main.py`。發動一個 `generate_report` task，輪詢狀態，然後取回結果。

2. 在執行途中加上一次 `tasks/cancel` 呼叫。驗證工作者有理會它，且狀態變成 `cancelled`。

3. 模擬崩潰復原：殺掉工作者執行緒、重啟載入器，並觀察 `CRASH_RECOVERY` 這個失敗模式。

4. 把那個儲存擴充成 SQLite。持久性上的收穫是一樣的；但查詢選項打開了（列出工作階段 X 的所有 task）。

5. 讀 MCP 2026 年的路線圖文章。找出那個最可能在未來一年影響 SDK API 設計的 Tasks 相關未決問題。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| Task | 「長時間執行的工具呼叫」 | 帶 `_meta.task` 加值、以非同步方式執行的請求 |
| SEP-1686 | 「Tasks 規格」 | 在 2025-11-25 加上 Tasks 的 Spec Evolution Proposal |
| `_meta.task` | 「Task 封裝」 | 每個請求的中繼資料，內含 id、state、ttl |
| taskSupport | 「工具旗標」 | 每個工具各自的 `forbidden`／`optional`／`required` |
| `tasks/status` | 「輪詢方法」 | 取得當前狀態與選配的進度提示 |
| `tasks/result` | 「取回結果」 | 回傳已完成的酬載，或在尚未完成時回 404 |
| `tasks/cancel` | 「把它停掉」 | 冪等的取消請求 |
| ttl | 「保留預算」 | 伺服器承諾保留該 task 狀態的毫秒數 |
| `notifications/tasks/updated` | 「狀態推播」 | 由伺服器發起的狀態變更事件 |
| 持久化儲存 | 「耐得住崩潰的狀態」 | 檔案系統／SQLite／Redis 的持久化層 |

## 延伸閱讀

- [MCP — GitHub SEP-1686 issue](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1686) —— 最初的提案與完整討論
- [WorkOS — MCP async tasks for AI agent workflows](https://workos.com/blog/mcp-async-tasks-ai-agent-workflows) —— 附設計理由的逐步說明
- [DeepWiki — MCP task system and async operations](https://deepwiki.com/modelcontextprotocol/modelcontextprotocol/2.7-task-system-and-async-operations) —— 機制與狀態機
- [FastMCP — Tasks](https://gofastmcp.com/servers/tasks) —— SDK 層級的 task 實作模式
- [MCP blog — 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) —— 未決問題與 2026 年的優先事項，含子任務
