# 給 AI 用的 SRE —— 多代理事故應變、Runbook、預測式偵測

> AI SRE 用透過 RAG 接地在基礎設施資料（日誌、runbook、服務拓撲）上的 LLM，來自動化調查、記錄與協調這幾個階段。2026 年的架構模式是多代理編排 —— 由一個監督者協調數個專職代理（日誌、指標、runbook）；AI 提出假設與查詢，人類核可需要判斷的決定。Datadog Bits AI 與 Azure SRE Agent 把這一套做成託管產品出貨。Runbook 正在演化：NeuBird Hawkeye 用對抗式評估（兩個模型分析同一起事故；一致代表有信心，不一致代表不確定）；運維記憶在團隊人員更迭之間持續留存。自動修復維持謹慎：AI 建議，人類核可。全自主的動作範圍很窄（重啟 Pod、回滾特定部署），並配上緊繃的護欄 —— 任何在賣「設好就不用管」的人都在誇大。正在浮現的前沿是事故前預測。MIT 的研究回報，一個用歷史日誌 + GPU 溫度 + API 錯誤樣式訓練的 LLM，提前 10-15 分鐘預測到了 89% 的中斷。推估：到 2026 年底，95% 的企業 LLM 會有自動故障轉移。

**類型：** 學習
**程式語言：** Python (stdlib, toy multi-agent incident triage simulator)
**先修單元：** 階段 17 · 13（可觀測性）、階段 17 · 24（混沌工程）
**時間：** 約 60 分鐘

## 學習目標

- 畫出多代理 AI SRE 架構：監督者 + 專職代理（日誌、指標、runbook）+ 人類核可閘門。
- 解釋為何自動修復是窄的（重啟 Pod、還原部署），而不是寬的（重新架構服務）。
- 說出那個對抗式評估模式（NeuBird Hawkeye）：兩個模型一致 = 有信心；不一致 = 升級。
- 引用 MIT 那個 89% 的早期偵測結果，以及那個運維上的限制：沒有致動的預測只是儀表板。

## 問題所在

一位待命工程師在凌晨三點被呼叫。「結帳流程錯誤率很高。」他們去看 Datadog、Loki、三份 runbook、部署日誌。30 分鐘後他們發現根因是 KV 快取暴衝造成的 vLLM OOM。他們重啟 Pod；錯誤消失。

在 2026 年，那場調查的前 20 分鐘是可以自動化的。把日誌依服務分組、關聯到近期的部署、比對 runbook —— 全都是 RAG + 工具使用。一個受監督的代理可以在人類打開 Datadog 之前，先做完第一輪檢傷並提出一個假設。

全自主的修復是另一個問題。重啟 Pod：安全。擴大 GPU 池：政策允許的話安全。重新架構服務：絕對不行。這門紀律就是把那條窄線畫出來。

## 核心概念

### 多代理架構

```
          Incident
             │
             ▼
        Supervisor
        /    |    \
       ▼     ▼     ▼
  Log agent  Metric agent  Runbook agent
       │     │     │
       └─────┴─────┘
             │
             ▼
        Hypothesis + evidence
             │
             ▼
        Human approval
             │
             ▼
        Action (narrow set)
```

監督者把事故拆成子查詢。專職代理有工具存取權（日誌搜尋、PromQL、文件檢索）。監督者做綜合，把假設 + 證據呈給人類。人類核可或重新導向。

### 自動修復的範圍

**安全（窄）**：重啟 Pod、還原特定部署、在預先核准的界線內擴縮池子、開啟預先核准的功能旗標。

**不安全（寬）**：改變服務拓撲、修改資源上限、部署新程式碼、改 IAM、動資料庫。

任何在賣「設好就不用管」的人都在誇大。隨著 AI SRE 成熟，那個安全集合會擴大，但那條邊界是真的。

### 對抗式評估（NeuBird Hawkeye）

兩個模型各自獨立分析同一起事故。若它們對根因意見一致，信心就高。若不一致，就把兩個假設都攤開來升級給人類。模式很簡單，但對付幻覺出來的根因是有效的過濾器。

### 運維記憶

人員流動是傳統 SRE 的無聲殺手 —— 部落知識跟著人走。AI SRE 把 runbook + 事後檢討存進向量資料庫；代理在每一起新事故上都去檢索。新工程師加入時，AI 手上有完整歷史。

### 事故前預測

MIT 2025 年的研究：一個用歷史日誌、GPU 溫度、API 錯誤樣式訓練的 LLM，在測試集上提前 10-15 分鐘預測到了 89% 的中斷。

現實檢查：沒有致動的預測就是儀表板。運維上的問題是「我們預測到之後要做什麼？」預先排空？呼叫待命？自動擴縮？答案因政策而異。

### 2026 年的產品

- **Datadog Bits AI** —— Datadog 裡的託管式 SRE 副手。
- **Azure SRE Agent** —— Azure 原生。
- **NeuBird Hawkeye** —— 對抗式評估 + 運維記憶。
- **PagerDuty AIOps** —— 檢傷 + 去重。
- **Incident.io Autopilot** —— 事故指揮官 + 協調。

### Runbook 即程式碼

Runbook 從 Confluence 頁面演化成帶結構化章節（症狀、假設、查證、行動）的版本化 markdown。結構化的 runbook 餵給 RAG 檢索的效果更好。任何 AI-SRE 的導入，都從把非結構化的 runbook 變成結構化的開始。

### 你該記住的數字

- MIT 的早期偵測：89% 的中斷，10-15 分鐘的前置時間。
- 多代理檢傷：監督者 + （日誌、指標、runbook）+ 人類。
- 安全的自動修復集合：重啟 Pod、還原部署、在界線內擴縮。
- 對抗式評估：兩個模型獨立分析；一致 = 有信心。

```figure
i4-incident-agents
```

## 框架應用

`code/main.py` 模擬一次多代理檢傷：日誌代理找到錯誤、指標代理找到 CPU 暴衝、runbook 代理比對到已知問題。監督者替假設排序。

## 產出交付

這一課產出 `outputs/skill-ai-sre-plan.md`。給定目前的待命制度、事故量與團隊成熟度，設計一次 AI SRE 導入。

## 練習

1. 跑 `code/main.py`。若日誌代理與指標代理意見不一致會怎樣？監督者怎麼裁決？
2. 替你的服務定義三項「安全」的自動修復動作。每一項都論證一次。
3. 寫出一份結構化的 runbook 樣板：章節、必填欄位、查證指令。
4. 預測式偵測在 12 分鐘前置時間觸發。你的政策是什麼 —— 呼叫待命、預先排空，還是兩者都做？
5. 論證一個 3 人團隊在 2026 年該採用 AI SRE 還是該再等等。考慮成熟度、量體與風險。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| AI SRE | 「待命用的代理」 | 由 LLM 支撐的事故調查 + 協調 |
| 監督者代理 | 「那個編排者」 | 把事故拆成子查詢的最上層代理 |
| 專職代理 | 「領域代理」 | 帶工具存取權的子代理（日誌、指標、runbook） |
| 自動修復 | 「AI 幫你修」 | 窄的、預先核准的動作；不是寬的重新架構 |
| 運維記憶 | 「向量化的 runbook」 | 放進向量資料庫供 RAG 用的事後檢討 + runbook |
| 對抗式評估 | 「雙模型檢查」 | 各自獨立的分析；一致 = 有信心 |
| NeuBird Hawkeye | 「那個對抗式的」 | 帶對抗式評估 + 記憶模式的產品 |
| Bits AI | 「Datadog 的 SRE 代理」 | Datadog 託管的 AI SRE |
| 事故前預測 | 「早期偵測」 | 對中斷預測有 10-15 分鐘前置時間 |

## 延伸閱讀

- [incident.io — AI SRE Complete Guide 2026](https://incident.io/blog/what-is-ai-sre-complete-guide-2026)
- [InfoQ — Human-Centred AI for SRE](https://www.infoq.com/news/2026/01/opsworker-ai-sre/)
- [DZone — AI in SRE 2026](https://dzone.com/articles/ai-in-sre-whats-actually-coming-in-2026)
- [Datadog Bits AI](https://www.datadoghq.com/product/bits-ai/)
- [NeuBird Hawkeye](https://www.neubird.ai/)
- [awesome-ai-sre](https://github.com/agamm/awesome-ai-sre)
