# 長時間執行的背景代理：持久執行

> 生產級的長時程代理不是跑在 `while True` 裡。每一次 LLM 呼叫都變成一項帶檢查點、重試與重播的 activity。Temporal 與 OpenAI Agents SDK 的整合在 2026 年 3 月正式上線。Claude Code Routines（Anthropic）在沒有常駐本地行程的情況下執行排程好的 Claude Code 調用。工作階段在需要人類輸入時暫停、撐過部署，並從以 `thread_id` 為鍵的最新檢查點續跑。這些新的人體工學底下坐著一個老模式 —— 工作流編排 —— 只多了一項新輸入：LLM 呼叫作為非決定性的 activity，在復原時必須被決定性地重播。

**類型：** 學習
**程式語言：** Python (stdlib, minimal durable-execution state machine)
**先修單元：** 階段 15 · 10（權限模式）、階段 15 · 01（長時程代理）
**時間：** 約 60 分鐘

## 問題所在

想像一個跑四小時的代理。它呼叫三項工具、提示使用者兩次，並做了四十次 LLM 呼叫。跑到一半，它所在的主機重開機了。會發生什麼事？

- 在一個天真的 `while True` 迴圈裡：全部都沒了。這趟執行從零重來。那三次工具呼叫（帶著真實副作用）會再執行一次。使用者會被再問一次那些他們已經核准過的事。四十次 LLM 呼叫被重新計費。
- 有持久執行的話：這趟執行從最近的檢查點續跑。已完成的 activity 不會被重新執行；它們的結果從持久日誌中重播出來。使用者不必重新核准他們已經核准過的事。已經做過的 LLM 呼叫不會被重新計費。

這跟工作流引擎出貨了十年的模式一模一樣（Temporal、Cadence、Uber 的 Cherami）。新的地方在於：LLM 呼叫如今是一種 activity —— 非決定性、昂貴、帶副作用 —— 而它們乾淨地符合這個模式。

本課貫穿的主題是：長時程可靠度會衰減（METR 觀察到「35 分鐘退化」—— 成功率大致隨時程平方下降）。持久執行讓你跑得比可靠度輪廓所支撐的更久，若設計正確，這是一種安全失敗的新方式；若設計錯誤，就是不安全的那種。

## 核心概念

### Activity、workflow 與重播

- **Workflow**：決定性的編排程式碼。定義 activity 的順序、分支、等待。它必須是決定性的，才能從事件日誌重播而不會出現意外分歧。
- **Activity**：一個非決定性、可能失敗的工作單位。LLM 呼叫、工具呼叫、寫檔案、HTTP 請求。每項 activity 都會連同輸入（以及完成後的輸出）被記錄下來。
- **事件日誌**：那個持久的後端儲存。每次 activity 的開始、完成、失敗、重試，以及每一次工作流決策都被記錄。
- **重播**：復原時，工作流程式碼從頭再跑一次；每一項已經完成的 activity 都直接回傳它被記錄的結果，不重新執行。只有那些沒完成的 activity 才真的被執行。

這跟 React 對著虛擬 DOM 重新渲染，或 Git 從 commit 重建工作樹是同一種形狀。編排器的決定性，正是讓持久性變便宜的原因。

### 為什麼 LLM 呼叫符合這個模式

LLM 呼叫是：
- 非決定性的（temperature > 0；就算 temperature 0，也會跨模型版本漂移）。
- 昂貴的（金錢與延遲）。
- 可能失敗的（速率限制、逾時）。
- 帶副作用的（如果它們調用工具）。

這正是 activity 的輪廓。把每一次 LLM 呼叫包成一項 activity，就給了你帶指數退避的重試、跨重啟的檢查點，以及一條可重播、供除錯用的軌跡。

### 以 `thread_id` 為鍵的檢查點

LangGraph、Microsoft Agent Framework、Cloudflare Durable Objects 與 Claude Code Routines 全都收斂到同一種 API 形狀：一個 `thread_id`（或等價物）識別該工作階段；每次狀態轉移都持久化到一個後端（預設 PostgreSQL、開發用 SQLite、快取用 Redis）；續跑時讀最新的檢查點。

後端的選擇很要緊：

- **PostgreSQL**：持久、可查詢、撐得過部署。LangGraph 的預設。
- **SQLite**：僅供本地開發；跨主機會掉資料。
- **Redis**：很快，但除非設定 AOF／快照，否則是短暫的。
- **Cloudflare Durable Objects**：透明地分散式；以唯一鍵劃定範圍；可存活數小時到數週。

### 把「等待人類輸入」當成一等狀態

先提議後提交（第 15 課）需要一個持久的「等待人類」狀態。工作流暫停、外部佇列扣著那個待處理請求，而一次核准就從那個確切的點續跑。沒有持久性，這只能盡力而為；有了它，一次隔夜的核准抵達之後，工作流在早上就接下去。

### 那個 35 分鐘退化

METR 觀察到，所有被量測的代理類別，在連續運作約 35 分鐘之後都出現可靠度衰減。任務時長翻倍，失敗率大約變四倍。持久執行修不好這件事；它讓你跑得比可靠度輪廓所支撐的更久。安全的模式是把持久性，跟「重新進入時要求新的 HITL 的檢查點」以及「無論牆鐘時間多久都替總運算量設上限的預算斷路開關」（第 13 課）結合起來。

### 什麼時候持久執行是錯的答案

- 短於幾分鐘、且沒有人類輸入的執行。開銷大於好處。
- 嚴格唯讀的資訊檢索。
- 那些正確性要求「端到端都在同一個脈絡視窗內」的任務（某些推理任務；某些一次性生成）。

```figure
memory-consolidation
```

## 框架應用

`code/main.py` 用 stdlib Python 實作一個最小的持久執行引擎。它支援：

- 一個 `@activity` 裝飾器，把輸入與輸出記錄到一份 JSON 事件日誌。
- 一個把 activity 排成序列的 workflow 函數。
- 一個 `run_or_replay(workflow, event_log)` 函數，重播已完成的 activity 而不重新執行它們。

驅動程式模擬一條三項 activity 的工作流、在中途崩潰，並顯示 (a) 天真的重試會把每件事都重跑一遍，對照 (b) 重播只跑那項缺掉的 activity。

## 產出交付

`outputs/skill-durable-execution-review.md` 審查一次被提議的長時間執行代理部署，檢視其持久執行形狀是否正確：activity、決定性、檢查點後端、人類輸入狀態，以及續跑時的 HITL 政策。

## 練習

1. 跑 `code/main.py`。觀察天真重試與重播之間，activity 執行次數的差別。改變崩潰的位置，展示重播次數也跟著改變。

2. 把這個玩具引擎改成明確使用 `thread_id`。模擬兩個共用該引擎的併發工作階段，並確認它們的事件日誌不會相撞。

3. 挑這個玩具引擎裡的一項 activity。引入一項非決定性（在工作流決策裡放一個牆鐘時間戳）。示範重播時的分歧。解釋真實引擎怎麼處理這件事（副作用註冊、`Workflow.now()` API）。

4. 讀 LangChain 那篇〈Runtime behind production deep agents〉。列出那個執行環境持久化的每一項狀態，並說出每一項各涵蓋哪種失敗模式。

5. 替一項 6 小時的自主寫程式任務設計一套檢查點政策。你在哪裡設檢查點？崩潰後續跑長什麼樣子？什麼需要新的 HITL？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|---|---|---|
| Workflow | 「代理的腳本」 | 決定性的編排程式碼；可從事件日誌重播 |
| Activity | 「一個步驟」 | 非決定性的單位（LLM 呼叫、工具呼叫）；前後都被記錄 |
| 事件日誌 | 「那個後端儲存」 | 每次狀態轉移的持久紀錄 |
| 重播 | 「續跑」 | 重跑工作流；已完成的 activity 回傳被記錄的結果，不重新執行 |
| 檢查點 | 「存檔點」 | 以 thread_id 為鍵持久化的狀態；續跑時取最新 |
| thread_id | 「工作階段鍵」 | 替持久狀態劃定範圍的識別碼 |
| 35 分鐘退化 | 「可靠度衰減」 | METR：成功率大致隨時程平方下降 |
| 非決定性 | 「重播時的漂移」 | 牆鐘、隨機、LLM 輸出；必須註冊成副作用 |

## 延伸閱讀

- [Anthropic — Claude Code Agent SDK: agent loop](https://code.claude.com/docs/en/agent-sdk/agent-loop) —— 預算、輪次與續跑語意。
- [Microsoft — Agent Framework: human-in-the-loop and checkpointing](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop) —— RequestInfoEvent 的形狀。
- [LangChain — The Runtime Behind Production Deep Agents](https://www.langchain.com/conceptual-guides/runtime-behind-production-deep-agents) —— 具體的執行環境需求。
- [OpenAI Agents SDK + Temporal integration (Trigger.dev announcement)](https://trigger.dev) —— LLM 呼叫的 activity 形狀。
- [Anthropic — Measuring agent autonomy in practice](https://www.anthropic.com/research/measuring-agent-autonomy) —— 那個 35 分鐘退化的出處。
