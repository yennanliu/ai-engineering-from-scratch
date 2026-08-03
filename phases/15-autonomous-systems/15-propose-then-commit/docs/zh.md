# Human-in-the-Loop：先提議後提交

> 2026 年關於 HITL 的共識很具體。它不是「代理問一下，使用者按核准」。它是先提議後提交：被提議的行動連同一把冪等鍵持久化到儲存中；帶著意圖、資料來源脈絡、觸及的權限、爆炸半徑與回捲計畫呈現給審查者；只有在得到積極確認之後才提交；執行後再查證，確認那個副作用真的發生了。LangGraph 的 `interrupt()` 加 PostgreSQL 檢查點、Microsoft Agent Framework 的 `RequestInfoEvent`，以及 Cloudflare 的 `waitForApproval()`，實作的都是同一種形狀。典範化的失敗模式是橡皮圖章式核准：沒看就按下「核准？」。有記錄的緩解方式是帶明確檢查清單的挑戰—回應。

**類型：** 學習
**程式語言：** Python (stdlib, propose-then-commit state machine with idempotency)
**先修單元：** 階段 15 · 12（持久執行）、階段 15 · 14（絆線）
**時間：** 約 60 分鐘

## 問題所在

代理採取一項行動。使用者必須決定：核准或不核准。若這個決定是瞬間的，那大概不是審查。若這個決定是有結構的，那就慢但值得信任。工程上的問題是：怎麼讓「有結構的審查」成為阻力最小的那條路。

2023 年那套 HITL 模式是一個同步提示：「代理想寄信給 X，內文為 Y —— 核准嗎？」使用者按核准。大家都覺得系統很安全。實務上這個表面被大量橡皮圖章化：使用者按得很快、核准幾乎沒有預測力，而當代理出錯時，稽核軌跡顯示的是一長串使用者根本記不得的核准。

2026 年那套模式 —— 先提議後提交 —— 把 HITL 搬到一個持久基底上、附上結構化中繼資料，並要求積極提交。每一套託管代理 SDK 都出貨了一個版本：LangGraph 的 `interrupt()`、Microsoft Agent Framework 的 `RequestInfoEvent`、Cloudflare 的 `waitForApproval()`。API 名稱不同；形狀相同。

## 核心概念

### 先提議後提交的狀態機

1. **提議。** 代理產出一項被提議的行動。持久化到一個儲存（PostgreSQL、Redis、Durable Object）。包含：
   - 意圖（代理為什麼要做這件事）
   - 資料來源脈絡（是什麼來源導致了這項提議）
   - 觸及的權限（哪些範圍／檔案／端點）
   - 爆炸半徑（最壞情況是什麼）
   - 回捲計畫（若提交了，我們要怎麼把它復原）
   - 冪等鍵（每項提議唯一；重複送出會回到同一筆紀錄）
2. **呈現。** 審查者看到提議與所有中繼資料。審查者是一個人（不是代理在審查自己）。
3. **提交。** 積極確認。行動執行。
4. **查證。** 執行後，把那個副作用讀回來確認。若查證這一步失敗，系統就處在一個已知的壞狀態，警示啟動。

### 那把冪等鍵

沒有冪等鍵，一次暫時性失敗之後的重試就可能把已核准的行動執行兩次。具體例子：使用者核准「從 A 轉 100 美元給 B」。網路閃斷。工作流重試。使用者只核准過一次，轉帳卻執行了兩次。冪等鍵把那次核准綁到單一個唯一的副作用上；第二次執行就是 no-op。

這跟 Stripe 與 AWS API 用的是同一套冪等模式。把它重用在代理核准上，在 Microsoft Agent Framework 的文件裡是明寫的。

### 持久性：為什麼核准活得比行程久

那間核准候診室，是一塊代理並不擁有的狀態。工作流被暫停（第 12 課）。當核准抵達時，工作流就從那個確切的點續跑。這就是為什麼 LangGraph 把 `interrupt()` 跟 PostgreSQL 檢查點配在一起，而不只是記憶體內狀態 —— 兩天後才來的核准，仍然找得到完好的工作流。

### 橡皮圖章式核准與挑戰—回應的緩解

HITL 的預設 UI（「核准」／「拒絕」按鈕）產出的是沒有真正審查的快速核准。有記錄的緩解方式是：一份挑戰—回應檢查清單，要求先對特定問題給出肯定回答，「核准」按鈕才會啟用。具體形狀：

- 「你了解這會碰到什麼資源嗎？[ ]」
- 「你有沒有確認爆炸半徑是可接受的？[ ]」
- 「如果失敗，你有回捲計畫嗎？[ ]」

這不是為了官僚而官僚 —— 它是一個逼迫機制。勾不下去的審查者，要嘛去要求澄清（升級），要嘛拒絕（安全預設）。Anthropic 的代理安全研究明白引用「以檢查清單驅動的 HITL」作為橡皮圖章核准模式的緩解方式。

### 什麼算是有後果的

不是每個行動都需要先提議後提交。2026 年的指引：

- **有後果的行動**（一律 HITL）：不可逆的寫入、金融交易、對外通訊、生產資料庫變更、破壞性的檔案系統操作。
- **可逆的行動**（有時 HITL）：對本地檔案的編輯、測試環境的變更、有清楚回捲的可逆寫入。
- **讀取與檢視**（永不 HITL）：讀檔案、列出資源、呼叫唯讀 API。

### 事後查證

「提交跑了」跟「副作用發生了」不是同一件事。網路分區與競態條件可能讓工作流以為自己成功了，而後端其實沒有持久化。查證那一步會在提交之後重新讀取目標資源以確認。這跟資料庫交易的 `RETURNING` 子句，或 AWS 在 `PutObject` 之後做 `GetObject` 是同一種模式。

### 歐盟 AI 法案第 14 條

第 14 條要求歐盟境內的高風險 AI 系統要有有效的人類監督。「有效」不是裝飾用的。法規語言明確排除橡皮圖章式的模式。在 Microsoft Agent Governance Toolkit 的法遵文件中，帶挑戰—回應的先提議後提交，就是那個撐得過第 14 條檢視的形狀。

```figure
mx-propose-then-commit
```

## 框架應用

`code/main.py` 用 stdlib Python 實作一台先提議後提交的狀態機。持久儲存是一個 JSON 檔。冪等鍵是 (thread_id, action_signature) 的雜湊。驅動程式模擬三種案例：一次乾淨的核准流程、一次暫時性失敗後的重試（絕不能重複執行），以及橡皮圖章的預設對照帶挑戰—回應的流程。

## 產出交付

`outputs/skill-hitl-design.md` 審查一條被提議的 HITL 工作流是否具備先提議後提交的形狀，並標出缺少的中繼資料、冪等性、查證或挑戰—回應層。

## 練習

1. 跑 `code/main.py`。確認對一項已核准提議的重試會使用那筆持久紀錄，而不會重新執行。接著把冪等鍵改成包含時間戳，並展示重試會重複執行。

2. 替提議紀錄擴充一個 `rollback` 欄位。模擬一次查證步驟失敗的執行。展示回捲自動觸發。

3. 讀 Microsoft Agent Framework 的 `RequestInfoEvent` 文件。找出一個該 API 有、而這個玩具引擎缺少的中繼資料欄位。把它加上去，並解釋它防的是什麼。

4. 替一項特定行動（例如「發文到一個公開的 Twitter 帳號」）設計一份挑戰—回應檢查清單。審查者必須回答哪三個問題？為什麼是那三個？

5. 挑一個「同步的『核准？』提示就夠了（不需要持久儲存）」的案例。解釋為什麼，並說出你正在接受的那類風險。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|---|---|---|
| 先提議後提交 | 「兩階段核准」 | 持久化的提議 + 積極提交 + 查證 |
| 冪等鍵 | 「重試安全的權杖」 | 每項提議唯一；第二次執行是 no-op |
| 資料來源脈絡 | 「它從哪來」 | 導致這項提議的那份具體來源內容 |
| 爆炸半徑 | 「最壞情況」 | 若這項行動出錯，影響的範圍 |
| 橡皮圖章 | 「快速核准」 | 沒有真正審查就按下「核准」 |
| 挑戰—回應 | 「逼迫用的檢查清單」 | 審查者必須對特定問題給出肯定確認 |
| RequestInfoEvent | 「MS Agent Framework 的原語」 | 帶結構化中繼資料的持久 HITL 請求 |
| `interrupt()`／`waitForApproval()` | 「框架的原語」 | LangGraph／Cloudflare 中同一形狀的對應物 |

## 延伸閱讀

- [Microsoft Agent Framework — Human in the loop](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop) —— `RequestInfoEvent`、持久核准。
- [Cloudflare Agents — Human in the loop](https://developers.cloudflare.com/agents/concepts/human-in-the-loop/) —— `waitForApproval()` 與 Durable Objects。
- [Anthropic — Measuring agent autonomy in practice](https://www.anthropic.com/research/measuring-agent-autonomy) —— 把 HITL 當成長時程風險的緩解。
- [EU AI Act — Article 14: Human oversight](https://artificialintelligenceact.eu/article/14/) —— 高風險系統的法規底線。
- [Anthropic — Claude's Constitution (January 2026)](https://www.anthropic.com/news/claudes-constitution) —— 圍繞監督的憲章式框架。
