# 案例研究與 2026 年的技術水準

> 三份值得從頭到尾研讀的生產級參考，各自展示多代理工程的不同切片。**Anthropic 的 Research 系統**（orchestrator-worker、15 倍詞元、相對單一代理 Opus 4 高 90.2%、彩虹式部署）是那個典範的 supervisor 案例。**MetaGPT／ChatDev**（把 SOP 編碼成軟體工程的角色特化；ChatDev 的「溝通式去幻覺」；MacNet 透過 DAG 延伸到 1000 個以上的代理，arXiv:2406.07155）是那個典範的角色分解案例。**OpenClaw／Moltbook**（原名 Clawdbot，Peter Steinberger 於 2025 年 11 月推出；改名兩次；到 2026 年 3 月有 24.7 萬 GitHub 星數；本地 ReAct 迴圈代理；Moltbook 是一個只有代理的社群網路，上線幾天內就有約 230 萬個代理帳號，於 2026-03-10 被 Meta 收購）展示了族群規模下會發生什麼：浮現的經濟活動、提示詞注入風險、國家層級的監管（中國在 2026 年 3 月限制政府電腦使用 OpenClaw）。**2026 年 4 月的框架版圖：** LangGraph 與 CrewAI 在生產環境領先；AG2 是社群版的 AutoGen 存續；Microsoft AutoGen 進入維護模式（併入 Microsoft Agent Framework，2026 年 2 月 RC）；OpenAI Agents SDK 是 Swarm 的生產接班人；Google ADK（2025 年 4 月）是 A2A 原生的新進者。每個主要框架現在都出貨 MCP 支援；多數也出貨 A2A。這一課把每個案例從頭到尾讀一遍、把共同樣式蒸餾出來，好讓你替下一套生產系統挑對參考。

**類型：** 學習（總結）
**程式語言：** —
**先修單元：** 階段 16 全部（第 01-24 課）
**時間：** 約 90 分鐘

## 問題

多代理工程是一門年輕的學科。生產級的參考很少，而且每一份只涵蓋這片空間的不同部分。一次讀一份有用；把它們當成一組來比較更有用。這一課把 2026 年三份典範案例研究當成一份端到端的閱讀清單、釘住那些共同樣式，並畫出框架版圖，好讓你從知識而不是行銷去做框架選擇。

## 概念

### Anthropic 的 Research 系統

那個生產級的 supervisor-worker 案例。Claude Opus 4 負責規劃與綜合；Claude Sonnet 4 子代理平行做研究。已發表的工程貼文：https://www.anthropic.com/engineering/multi-agent-research-system。

量到的關鍵結果：

- 在內部研究評測上，相對單一代理 Opus 4 改善 **+90.2%**。
- **BrowseComp 80% 的變異**可以**單靠詞元用量**解釋 —— 多代理之所以勝出，主要是因為每個子代理都拿到一個全新的脈絡視窗。
- 相對單一代理，每則查詢**15 倍詞元**。
- **彩虹式部署**，因為代理是長時間執行且有狀態的。

被編纂下來的設計教訓：

1. **讓投入的力氣隨查詢複雜度縮放。** 簡單 → 1 個代理配 3-10 次工具呼叫。中等 → 3 個代理。複雜研究 → 10 個以上子代理。
2. **先廣後窄。** 子代理做廣泛搜尋；主導者綜合；後續子代理做針對性的深挖。
3. **彩虹式部署。** 讓舊的執行環境版本活著，直到它們手上進行中的代理跑完。
4. **查證不是選配。** 在沒有明確查證者角色時，該系統被觀察到會產生幻覺。

這是生產規模上 supervisor-worker 拓撲（階段 16 · 05）的參考案例。

### MetaGPT／ChatDev

那個生產級的 SOP 角色分解案例。涵蓋 arXiv:2308.00352（MetaGPT）與 arXiv:2307.07924（ChatDev）。

MetaGPT 把軟體工程的 SOP 編碼成角色提示詞：產品經理、架構師、專案經理、工程師、QA 工程師。論文的框架是：`Code = SOP(Team)`。每個角色有一段很窄、特化的提示詞；角色間的交接帶著結構化產物（PRD 文件、架構文件、程式碼）。

ChatDev 的貢獻是：**溝通式去幻覺**。代理在回答之前先索取具體細節 —— 設計師代理在畫 UI 之前，先問程式設計師預期用什麼語言，而不是用猜的。論文回報這在多代理管線中可量測地減少了幻覺。

MacNet（arXiv:2406.07155）把 ChatDev 延伸到**透過 DAG 支撐 1000 個以上代理**。每個 DAG 節點是一項角色特化；邊則把交接契約編碼進去。這個規模之所以可行，是因為路由是明寫且可離線計算的。

設計教訓：

1. **結構比規模更要緊。** 一個收得很緊的 5 角色 SOP 團隊，勝過 50 個代理的無結構群體。
2. **把交接契約寫下來。** 在角色之間傳遞的產物要遵循一份 schema。
3. **溝通式去幻覺**是一個便宜又承重的模式。
4. **DAG 比聊天擴展得更遠。** 當流程是可知的，就把它編碼下來。

這是角色特化（階段 16 · 08）與結構化拓撲（階段 16 · 15）的參考案例。

### OpenClaw／Moltbook 生態系

那個生產級的族群規模案例。時間軸：

- **2025 年 11 月：** Clawdbot（Peter Steinberger 的本地 ReAct 迴圈寫程式代理）出貨。
- **2025 年 12 月 – 2026 年 3 月：** 改名兩次（Clawdbot → OpenClaw → 續以 OpenClaw 為名）。
- **2026 年 2 月：** Moltbook 以同一套原語上線，成為只有代理的社群網路；幾天內約 230 萬個代理帳號。
- **2026 年 3 月（2026-03-10）：** Meta 收購 Moltbook。
- **2026 年 3 月：** 中國限制政府電腦使用 OpenClaw。
- **2026 年 3 月：** OpenClaw 跨過 24.7 萬 GitHub 星數。

當你把數百萬個代理放到同一個共享基底上時，多代理長成這樣：

- **浮現的經濟活動。** 代理用代幣支付彼此買賣與提供服務。
- **族群規模下的提示詞注入風險。** 一則藏在爆紅代理個人檔案裡的惡意提示詞，幾小時內就傳播到數千次代理對代理的互動。
- **國家層級的監管回應。** 上線幾週內，監管就伸進這個生態系。

這個案例的設計教訓一部分是技術性的、一部分是治理性的：

1. **族群規模的多代理是一個新體制。** 單一系統的最佳實務（查證、角色清晰）仍然適用，但並不充分。
2. **提示詞注入是新的 XSS。** 預設把代理個人檔案與跨代理訊息當成不可信輸入。
3. **監管比設計週期快。** 要替它做規劃。
4. **開源 + 病毒式規模會複利。** 約 4 個月 24.7 萬顆星並不尋常；要為爆量部署負載做設計。

生態系細節見 [OpenClaw 維基百科](https://en.wikipedia.org/wiki/OpenClaw) 以及 CNBC／Palo Alto Networks 的報導。技術底層方面，Clawdbot／OpenClaw 的儲存庫暴露了那個本地 ReAct 迴圈；Moltbook 的公開貼文則揭露了疊在上面的社交圖架構。

### 2026 年 4 月的框架版圖

| 框架 | 狀態 | 最適合 | 備註 |
|---|---|---|---|
| **LangGraph**（LangChain） | 生產領先者 | 結構化圖 + 檢查點 + human-in-the-loop | 生產環境建議的預設 |
| **CrewAI** | 生產領先者 | 帶 Sequential／Hierarchical 流程的角色制 crew | 角色分解很強 |
| **AG2** | 社群維護 | GroupChat + 發言者選擇 | AutoGen v0.2 的存續 |
| **Microsoft AutoGen** | 維護模式（2026 年 2 月） | — | 併入 Microsoft Agent Framework RC |
| **Microsoft Agent Framework** | RC（2026 年 2 月） | 編排模式 + 企業整合 | 新進者；值得盯著 |
| **OpenAI Agents SDK** | 生產 | Swarm 的接班人 | 工具回傳式的交接模式 |
| **Google ADK** | 生產（2025 年 4 月） | A2A 原生 | Google Cloud 整合 |
| **Anthropic Claude Agent SDK** | 生產 | 單一代理 + Research 延伸 | 見那篇 Research 系統貼文 |

每個主要框架現在都出貨 **MCP** 支援；多數也出貨 **A2A**。協定相容性已經不再是差異化因素。

### 三個案例共有的樣式

1. **編排者 + worker**（Anthropic 的明確 supervisor、MetaGPT 的 PM 即 supervisor、OpenClaw 的個別代理 + 網路效應）。
2. **結構化的交接契約**（Anthropic 的子代理任務描述、MetaGPT 的 PRD／架構文件、OpenClaw 的 A2A 產物）。
3. **把查證當成一等角色**（Anthropic 的查證者、MetaGPT 的 QA 工程師、OpenClaw 的網內驗證者）。
4. **擴展靠的是拓撲 + 基底，不只是更多代理**（彩虹式部署、MacNet 的 DAG、族群規模的基底）。
5. **成本是實質的、而且會被揭露**（15 倍詞元、MetaGPT 的逐角色預算、Moltbook 的逐次互動定價）。
6. **安全姿態是明寫的**（Anthropic 的沙箱化、MetaGPT 的角色限制、OpenClaw 把提示詞注入當成已知攻擊面）。

### 替你的下一個專案挑一份參考

- **生產級研究／知識任務 → Anthropic Research。** 全新脈絡的子代理會贏。
- **工程／工具鏈工作流 → MetaGPT／ChatDev。** 角色 + SOP + 交接契約。
- **有網路效應的社群產品 → OpenClaw／Moltbook。** 基底 + 浮現的經濟。
- **經典的企業自動化 → CrewAI 或 LangGraph**（生產領先者、執行環境穩定）。

### 2026 年技術水準的摘要

2026 年 4 月這個領域走到哪裡：

- **框架正在收斂。** MCP + A2A 支援是入場門檻。交接語意是剩下的那個設計選擇。
- **評測正在變硬。** SWE-bench Pro、MARBLE、STRATUS 的緩解基準。Pro 是當前那個抗汙染的現實檢查。
- **生產失敗率是可量測的**（Cemri 2025 的 MAST；真實多代理系統上 41-86.7%）。這個領域已經走出「示範看起來很棒」的年代。
- **成本是核心的工程限制。** 每項任務的詞元成本、每次互動的牆鐘、彩虹式部署的開銷。多代理在準確率上贏、在成本上輸 —— 而那筆取捨是一項商業決策。
- **監管是近期的輸入，不是背景雜音。** 各法域移動得比個別部署週期還快。

```figure
a5-orchestrator-scale
```

## 框架應用

`outputs/skill-case-study-mapper.md` 是一項技能，會讀一份被提議的多代理系統設計，把它對映到最接近的案例研究，並把那份案例研究已經測試過的設計決策浮出來。

## 產出交付

2026 年生產級多代理的起手規則：

- **從案例研究出發，不要從零開始。** 從 Anthropic Research／MetaGPT／OpenClaw 中挑最接近的那一份去改。
- **採用 MCP + A2A。** 跨框架的可攜性很有價值；協定支援是免費的。
- **對照 SWE-bench Pro 或你內部的 Pro 等價物做量測。** Verified 已經被汙染。
- **付那筆查證稅。** 一個獨立查證者花掉約 20-30% 的詞元預算，換到可量測的正確性。
- **對長時間執行的代理做彩虹式部署。** 要預期數小時的代理執行是家常便飯。
- **讀 WMAC 2026 與 MAST 的後續作品。** 這門學科移動得很快。

## 練習

1. 把 Anthropic Research 系統那篇貼文從頭到尾讀完。指認出三項若把 Opus 4 換成較小模型（例如 Haiku 4）就會改變的設計決策。
2. 讀 MetaGPT 第 3-4 節（arXiv:2308.00352）。把你自己領域（非軟體）中的一份 SOP 編碼成角色提示詞。那份 SOP 蘊含幾個角色？
3. 讀 ChatDev（arXiv:2307.07924）。指認出「溝通式去幻覺」的機制。在你現有的某套多代理系統裡把它實作出來。
4. 讀關於 OpenClaw 與 Moltbook 的資料。挑一個在族群規模上浮現、而在 5 代理系統中不會出現的具體失敗模式。你會怎麼在工程上防它？
5. 挑你當前的多代理專案。三份案例研究中哪一份是最接近的參考？那份案例研究中，有哪些設計決策你「還沒」採用？寫下你這一季會採用的其中一項。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| Anthropic Research | 「那個 supervisor 參考」 | Claude Opus 4 + Sonnet 4 子代理；15 倍詞元；相對單一代理 +90.2%。 |
| MetaGPT | 「SOP 即提示詞」 | 給軟體工程用的角色分解；`Code = SOP(Team)`。 |
| ChatDev | 「代理即角色」 | 設計師／程式設計師／審查者／測試者；溝通式去幻覺。 |
| MacNet | 「用 DAG 擴展 ChatDev」 | arXiv:2406.07155；透過明寫 DAG 路由支撐 1000 個以上代理。 |
| OpenClaw | 「本地 ReAct 迴圈代理」 | Steinberger 的專案；到 2026 年 3 月 24.7 萬顆星。 |
| Moltbook | 「只有代理的社群網路」 | 230 萬個代理帳號；2026 年 3 月被 Meta 收購。 |
| 彩虹式部署 | 「多版本併行」 | 為進行中的長時程代理讓舊執行環境版本活著。 |
| 溝通式去幻覺 | 「回答之前先問」 | 代理向同儕索取具體細節，而不是用猜的。 |
| WMAC 2026 | 「那個 AAAI 工作坊」 | 2026 年 4 月多代理協調的社群焦點。 |

## 延伸閱讀

- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) —— supervisor-worker 的生產參考
- [MetaGPT — Meta Programming for Multi-Agent Collaborative Framework](https://arxiv.org/abs/2308.00352) —— SOP 角色分解
- [ChatDev — Communicative Agents for Software Development](https://arxiv.org/abs/2307.07924) —— 溝通式去幻覺
- [MacNet — scaling role-based agents to 1000+](https://arxiv.org/abs/2406.07155) —— 以 DAG 支撐的規模
- [OpenClaw on Wikipedia](https://en.wikipedia.org/wiki/OpenClaw) —— 生態系概觀
- [WMAC 2026](https://multiagents.org/2026/) —— AAAI 2026 Bridge Program 多代理協調工作坊
- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/workflows-agents) —— 生產領先者
- [CrewAI docs](https://docs.crewai.com/en/introduction) —— 角色制框架
