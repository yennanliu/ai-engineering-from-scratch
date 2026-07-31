# 代理框架的取捨 —— 圖、角色與行為者式協作

> 每個框架都在賣同一個示範（研究代理產出一份報告），也都藏著同一個 bug（狀態 schema 和協作層打架）。挑那個抽象最貼合你問題形狀的框架；其他一切都是你得寫兩遍的膠水程式碼。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 11 · 09（函數呼叫）、階段 11 · 16（LangGraph）
**時間：** 約 45 分鐘

## 問題所在

你有一個需要多次 LLM 呼叫的任務。可能是一條研究工作流程（規劃、搜尋、摘要、引註）。可能是一條程式碼審查管線（解析 diff、批評、修補、驗證）。可能是一個會訂機票、寫信、報帳的多輪助理。於是你挑了一個框架。

三天後，你發現框架的抽象在漏水。CrewAI 給了你角色，但當「researcher」要把一份結構化計畫交給「writer」時它就跟你打架。AutoGen 給了你代理之間的聊天，卻沒有一級狀態，所以你的檢查點只是一份對話日誌的 pickle。LangGraph 給了你狀態圖，卻要你在還不知道代理會做什麼之前就把每一個轉移都命名好。Agno 給了你單一代理的抽象，而你一想扇出到三個並行工作者它就尖叫。

解法不是「挑最好的框架」，而是讓框架的核心抽象對上你問題的形狀。這一課就是在畫那張地圖。

## 核心概念

![代理框架矩陣：核心抽象對問題形狀](../assets/framework-matrix.svg)

四個框架主導了 2026 年的地景。它們的核心抽象並不相同。

| 框架 | 核心抽象 | 最適合 | 最不適合 |
|-----------|------------------|----------|-----------|
| **LangGraph** | `StateGraph` —— 帶型別的狀態、節點、條件邊、checkpointer。 | 帶明確狀態與人類介入中斷的工作流程；需要時光回溯除錯的生產級代理。 | 拓撲未知、鬆散而由角色驅動的腦力激盪。 |
| **CrewAI** | `Crew` —— 角色（目標、背景故事）、任務、流程（循序或層級式）。 | 帶簡短線性／層級計畫的角色扮演或人格驅動工作流程。 | 任何超出 crew 輪次歷史的有狀態需求；複雜的分支。 |
| **AutoGen** | `ConversableAgent` 配對 —— 兩個以上的代理輪流說話，直到滿足結束條件。 | 多代理**對話**（師生、提案者－批評者、執行者－審核者），思考從聊天中浮現。 | 已知 DAG 的確定性工作流程；任何需要跨重啟持久狀態的東西。 |
| **Agno** | `Agent` —— 一個 LLM + 工具 + 記憶，可組成團隊。 | 快速做出單一代理與輕量團隊；多模態能力強、內建儲存驅動。 | 深層、明確分支、需要自訂 reducer 的圖。 |

### 「抽象」到底是什麼意思

一個框架的核心抽象，就是你在白板上推銷架構時畫的那個東西。

- **LangGraph** → 你畫一張圖。節點是步驟，邊是轉移，而每一點上的狀態物件都有型別。心智模型是狀態機。
- **CrewAI** → 你畫一張組織圖。每個角色有職務說明，由一位管理者分派任務。心智模型是一支專家小隊。
- **AutoGen** → 你畫一段 Slack 私訊。兩個代理互相傳訊息；需要主持人時第三個加入。心智模型是聊天。
- **Agno** → 你畫一個方框，工具掛在它上面。要組團隊就把方框並排。心智模型是「附電池的代理」。

### 狀態這個問題

狀態是多數框架選擇在生產環境崩解的地方。

- **LangGraph。** 帶型別的狀態（`TypedDict` 或 Pydantic 模型）、每欄位各自的 reducer、一級的 checkpointer（SQLite/Postgres/Redis）。恢復、中斷與時光回溯都是免費的。*（見階段 11 · 16。）*
- **CrewAI。** 狀態以字串透過 `context` 欄位在任務之間流動，或透過 `output_pydantic` 結構化。開箱沒有 per-crew 的持久儲存；若 crew 必須撐過重啟，就得自己接上。
- **AutoGen。** 狀態就是聊天歷史加上任何使用者自定的 `context`。對話逐字稿會持久化，任意的工作流程狀態則不會 —— 除非你自己寫轉接器。
- **Agno。** 內建儲存驅動（SQLite、Postgres、Mongo、Redis、DynamoDB），透過 `storage=` 掛到一個 `Agent` 上 —— 對話工作階段與使用者記憶會自動持久化。它不是完整的圖 checkpointer，而是一個 session 儲存。

### 分支這個問題

任何非平凡的代理都會分支。誰來決定分支很重要。

- **LangGraph** —— 由你決定，透過條件邊。路由是一個帶具名分支的 Python 函數。分支在編譯後的圖裡是一級公民；checkpointer 會記下走了哪條分支。
- **CrewAI** —— 層級模式下由管理者決定；循序模式下由你在建構時決定。路由隱含在任務清單裡；除了管理者的提示詞之外，沒有一級的「if」。
- **AutoGen** —— 由代理透過聊天決定。分支從「下一個誰說話」中浮現。`GroupChatManager` 挑選下一位發言者；你可以手寫 `speaker_selection_method`，但預設是由 LLM 驅動。
- **Agno** —— 由代理透過「接下來呼叫哪個工具」決定。團隊有協調者／路由器／協作者模式；超出這些的分支就是開發者的責任。

### 可觀測性這個問題

- **LangGraph** —— 透過 LangSmith 或任何 OTel 匯出器走 OpenTelemetry。每一次節點轉移都是一個 trace span；檢查點同時也是可重播的軌跡。LangSmith 是第一方選項；Langfuse/Phoenix 也有轉接器。
- **CrewAI** —— 自 2025 年底起有一級的 OpenTelemetry；與 Langfuse、Phoenix、Opik、AgentOps 都有整合。
- **AutoGen** —— 透過 `autogen-core` 整合 OpenTelemetry；AgentOps 與 Opik 有連接器。追蹤粒度是每則代理訊息，而不是每個節點。
- **Agno** —— 內建 `monitoring=True` 旗標加上 OpenTelemetry 匯出器；與 Langfuse 在 session 軌跡上整合緊密。

### 成本與延遲

四個框架都會帶來每次呼叫的額外開銷（框架邏輯、驗證、序列化）。開銷由低到高大致是：Agno ≈ LangGraph < CrewAI ≈ AutoGen。差別主要由「框架自己多做了多少 LLM 路由」決定。CrewAI 的層級管理者要花詞元決定下一個誰上；AutoGen 的 `GroupChatManager` 也一樣。LangGraph 只在你寫 `llm.invoke` 的地方花詞元。Agno 的單一代理路徑很薄。

當每次執行的成本很重要時，優先選明確路由（LangGraph 的邊、AutoGen 的 `speaker_selection_method`），而不是由 LLM 挑選的路由。

### 互通性

- **LangGraph** ↔ **LangChain** 的工具、檢索器、LLM。一級的 MCP 轉接器（工具以 MCP 伺服器形式匯入）。
- **CrewAI** ↔ 工具繼承自 `BaseTool`；LangChain 工具、LlamaIndex 工具與 MCP 工具都能接進來。透過 `allow_delegation=True` 做 crew 對 crew 的委派。
- **AutoGen** → `FunctionTool` 能包住任何 Python callable；有 MCP 轉接器。在代理對代理的模式上與 AG2 生態系耦合緊密。
- **Agno** → `@tool` 裝飾器或 BaseTool 子類別；有 MCP 轉接器；工具能跨代理與跨團隊共用。

## 這項技能

> 你能用一句話說出，為什麼某個框架適合某個代理問題。

動手前的檢查清單：

1. **畫出形狀。** 這是一張圖（帶型別狀態、具名轉移）嗎？一場角色扮演（專家之間交接工作）？一段聊天（代理談到結束）？還是一個帶工具的單一代理？
2. **決定誰來分支。** 開發者決定分支 → LangGraph。管理者代理決定 → CrewAI 層級模式。從聊天中浮現 → AutoGen。由工具呼叫決定 → Agno。
3. **檢查狀態預算。** 你需要從檢查點恢復嗎？時光回溯？執行中途的人類中斷？如果要，LangGraph 是預設選擇；Agno 的 session 涵蓋對話範圍內的狀態。
4. **檢查成本預算。** 由 LLM 挑選的路由每一輪都多花詞元。如果代理一天要跑幾千次，優先選明確路由。
5. **把框架開銷算進預算。** 每個框架都是又一個依賴。如果任務只是兩次 LLM 呼叫加一個工具，就寫 30 行純 Python；沒有框架比「不用框架」更便宜。

在你能畫出那張圖、那張組織圖、那段聊天或那個代理方框之前，別急著抓框架。也別挑一個會讓你為了真正需要的東西去跟它的狀態模型打架的框架。

## 決策矩陣

| 問題形狀 | 首選框架 | 為什麼 |
|---------------|---------------------|-----|
| 帶型別狀態、人類核准、長時間執行的工作流程 DAG | LangGraph | 一級狀態、checkpointer、中斷、時光回溯。 |
| 角色分明的研究／寫作管線 | CrewAI（循序）或 LangGraph 子圖 | 在 CrewAI 裡「一任務一角色」很好表達；分支變複雜時再用 LangGraph 往上擴。 |
| 提案者－批評者或師生對話 | AutoGen | 雙代理聊天就是它的原生形狀。 |
| 帶工具、工作階段與記憶的單一代理 | Agno | 設定最薄，內建儲存與記憶。 |
| 帶 reducer 的數千次並行扇出 | LangGraph + `Send` | 唯一有一級並行派送 API 的。 |
| 快速原型，不想綁框架 | 純 Python + 供應商 SDK | 沒有框架就是最快的框架。 |

## 練習

1. **簡單。** 拿同一個任務 ——「研究 Anthropic 的總部、寫一份 200 字摘要、附上出處」—— 分別用 LangGraph（四個節點：plan、search、write、cite）和 CrewAI（三個角色：researcher、writer、editor）實作。報告每次執行的詞元成本與程式碼行數。
2. **中等。** 用 AutoGen（researcher ↔ writer 聊天，editor 透過 `GroupChat` 加入）和 Agno（一個帶 `search_tools` 與 `write_tools` 的單一代理，加上一個 session 儲存）做同樣的任務。就 (a) 每次執行成本、(b) 崩潰後恢復的能力、(c) 在 write 步驟前插入人類核准的能力，把四種實作排名。
3. **困難。** 寫一個決策樹腳本 `pick_framework.py`，接受一段簡短的問題描述（JSON：`{has_typed_state, has_roles, has_dialogue, has_parallel_fanout, needs_resume}`），回傳一個建議並附一句話理由。用你自己設計的六個案例驗證它。

## 關鍵術語

| 術語 | 大家怎麼說 | 它實際上是什麼 |
|------|-----------------|-----------------------|
| 協作（Orchestration） | 「代理之間怎麼協調」 | 決定下一個要跑哪個節點／角色／代理的那一層。 |
| 持久狀態（Durable state） | 「重啟後能接著跑」 | 能撐過行程死亡的狀態，掛在檢查點或 session 儲存上。 |
| LLM 挑選的路由（LLM-selected routing） | 「讓模型決定」 | 由一個規劃者 LLM 每輪挑下一步；靈活，但每個決策都要付詞元。 |
| 明確路由（Explicit routing） | 「開發者決定」 | 由一個 Python 函數或靜態邊挑下一步；便宜且可稽核。 |
| Crew | 「一支 CrewAI 團隊」 | 角色 + 任務 + 流程（循序或層級式）綁成單一個可執行物件。 |
| GroupChat | 「AutoGen 的多代理聊天」 | N 個代理之間受管理的對話，配一個發言者挑選器。 |
| Team（Agno） | 「多代理版的 Agno」 | 對一組代理套用路由／協調／協作模式。 |
| StateGraph | 「LangGraph 的那張圖」 | 帶型別狀態、節點、條件邊與 checkpointer 的抽象。 |

## 延伸閱讀

- [LangGraph documentation](https://langchain-ai.github.io/langgraph/) —— StateGraph、checkpointer、中斷、時光回溯。
- [CrewAI documentation](https://docs.crewai.com/) —— Crews、Flows、Agents、Tasks、Processes。
- [AutoGen documentation](https://microsoft.github.io/autogen/) —— ConversableAgent、GroupChat、團隊、工具。
- [Agno documentation](https://docs.agno.com/) —— Agent、Team、Workflow、儲存、記憶。
- [Anthropic — Building effective agents (Dec 2024)](https://www.anthropic.com/research/building-effective-agents) —— 與框架無關的模式庫（提示詞串接、路由、並行化、協調者－工作者、評估者－最佳化者）。
- [Yao et al., "ReAct: Synergizing Reasoning and Acting" (ICLR 2023)](https://arxiv.org/abs/2210.03629) —— 每個框架都在包裝的那個迴圈。
- [Wu et al., "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation" (2023)](https://arxiv.org/abs/2308.08155) —— AutoGen 的設計論文。
- [Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (UIST 2023)](https://arxiv.org/abs/2304.03442) —— CrewAI 這類人格堆疊所建立在其上的角色扮演基礎。
- 階段 11 · 16（LangGraph）—— 本課用來當基準的那個框架。
- 階段 11 · 19（Reflexion）—— 一個能乾淨對應到 LangGraph、但對應到 CrewAI 就很彆扭的模式。
- 階段 11 · 22（生產環境可觀測性）—— 不管你挑哪個框架，都要怎麼為它加上儀表。
