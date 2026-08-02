# 對齊研究生態系 —— MATS、Redwood、Apollo、METR

> 有五個組織界定了 2026 年實驗室之外的那層對齊研究。MATS（ML Alignment & Theory Scholars）：自 2021 年底以來 527 位以上研究者、180 篇以上論文、1 萬次以上引用、h 指數 47；2024 年夏季梯次登記為 501(c)(3) 非營利組織，約 90 位學者與 40 位導師；2025 年之前的校友有 80% 從事安全／資安工作，其中 200 人以上任職於 Anthropic、DeepMind、OpenAI、英國 AISI、RAND、Redwood、METR、Apollo。Redwood Research：由 Buck Shlegeris 創立的應用對齊實驗室；提出了 AI 控制（第 10 課）；與英國 AISI 合作推動控制安全論證。Apollo Research：替前沿實驗室做部署前的謀劃評估；撰寫了〈脈絡內謀劃〉（第 8 課）與〈Towards Safety Cases for AI Scheming〉。METR（Model Evaluation and Threat Research）：以任務為基礎的能力評估、自主任務的時間跨度研究；〈Common Elements of Frontier AI Safety Policies〉比較了各實驗室的框架。Eleos AI Research：模型福祉的部署前評估（第 19 課）；執行了 Claude Opus 4 的福祉評估。

**類型：** 學習
**程式語言：** none
**先修單元：** 階段 18 · 01-27（階段 18 先前的課程）
**時間：** 約 45 分鐘

## 學習目標

- 指認出實驗室之外那個對齊研究生態系的五個組織，以及它們的核心產出。
- 描述 MATS 的規模（學者數、論文數、h 指數），以及它作為人才輸送管道的角色。
- 描述 Redwood 的 AI 控制議程，以及它與英國 AISI 的合作。
- 描述 METR 以任務為基礎的評估方法論。

## 問題所在

前沿實驗室（第 18 課）在內部產出安全評估，並發表選定的結果。實驗室之外的生態系，才是那些評估被查核的地方、新穎失敗模式最先被發現的地方，也是人才被培養出來的地方。理解這個生態系，有助於判讀哪些研究發現被誰所信任。

## 核心概念

### MATS（ML Alignment & Theory Scholars）

2021 年底開始。研究導師制計畫；學者花 10-12 週跟著一位資深研究者，處理一個特定的對齊問題。

規模（2026）：
- 自成立以來 527 位以上研究者。
- 發表 180 篇以上論文。
- 1 萬次以上引用。
- h 指數 47。
- 2024 年夏季：90 位學者 + 40 位導師；登記為 501(c)(3) 非營利組織。

職涯結果：2025 年之前的校友約 80% 從事安全／資安工作。200 人以上任職於 Anthropic、DeepMind、OpenAI、英國 AISI、RAND、Redwood、METR、Apollo。

### Redwood Research

應用對齊實驗室。由 Buck Shlegeris 創立。提出了 AI 控制議程（第 10 課）。與英國 AISI 合作推動控制安全論證。也替 DeepMind 與 Anthropic 的評估設計提供諮詢。

代表性論文：Greenblatt、Shlegeris 等人的〈AI Control〉（arXiv:2312.06942，ICML 2024）；〈對齊偽裝〉（Greenblatt、Denison、Wright 等人，arXiv:2412.14093，與 Anthropic 合作）。

風格：具體的威脅模型、最差情況的對手，以及禁得起壓力測試的具體協定。

### Apollo Research

替前沿實驗室做部署前的謀劃評估。撰寫了〈脈絡內謀劃〉（第 8 課，arXiv:2412.04984）。是 2025 年 OpenAI 反謀劃訓練合作案的夥伴。產出〈Towards Safety Cases for AI Scheming〉（2024）。

風格：在欺騙可能冒出來的代理型情境中做評估；三支柱分解（未對齊、目標導向、情境覺察）。

### METR（Model Evaluation and Threat Research）

以任務為基礎的能力評估。自主任務完成的時間跨度研究。〈Common Elements of Frontier AI Safety Policies〉（metr.org/common-elements，2025）比較了各實驗室的框架。

與 Apollo 共同撰寫 AI 謀劃的安全論證草案。

風格：長跨度任務評估、實證能力量測、框架綜整。

### Eleos AI Research

模型福祉的部署前評估。執行了記載於系統卡 5.3 節的 Claude Opus 4 福祉評估。替第 19 課那些與福祉相關的宣稱提供外部的方法論查核。

### 那條流動

MATS 培養研究者。畢業生前往 Anthropic、DeepMind、OpenAI（實驗室的安全團隊），或前往 Redwood、Apollo、METR、Eleos（外部評估）。外部評估者與各實驗室、以及英國 AISI / CAISI 合作。發表出來的成果再把生態系餵回 MATS，供下一梯次使用。

### 這一層為什麼要緊

單一來源的評估並不可靠：實驗室評估自家模型，存在結構性的利益衝突。外部評估者能提出並查核那些實驗室可能少報的失敗模式。2024 年那篇臥底代理論文（第 7 課）是 Anthropic + Redwood；對齊偽裝是 Anthropic + Redwood；脈絡內謀劃是 Apollo；反謀劃是 Apollo + OpenAI。這種多組織的結構本身就是那道品質管控。

### 這在階段 18 裡的位置

第 7-11 課引用了 Redwood 與 Apollo 的工作；第 18 課引用了 METR 的框架比較；第 19 課引用了 Eleos。第 28 課就是把整個階段所倚賴的那個生態系，明確畫成一張組織地圖。

## 框架應用

沒有程式碼。去讀 METR 的〈Common Elements of Frontier AI Safety Policies〉，把它當成「外部綜整如何替實驗室內部的政策工作增添價值」的一個例子。

## 產出交付

這一課產出 `outputs/skill-ecosystem-map.md`。給定一項對齊宣稱或評估，它會指認出所屬組織、發表場域與方法論風格，並與已知的對應組織互相對照查核。

## 練習

1. 從第 7-15 課裡挑一篇論文，指認出參與的組織。把作者拿去與 MATS 校友名單及當前的生態系隸屬關係對照查核。

2. 讀 METR 的〈Common Elements of Frontier AI Safety Policies〉。指出他們強調的三項跨實驗室收斂，以及最大的兩項分歧。

3. MATS 的職涯結果約有 80% 走向安全／資安。論證這種選擇壓力究竟是適應性的（培養了這個領域），還是有偏的（把非主流立場過濾掉了）。

4. Redwood 與 Apollo 都在做控制／謀劃的工作，但風格不同。挑一種失敗模式，描述各自會怎麼調查它。

5. Eleos AI 是唯一一個純做模型福祉的組織。設計一個假想的第二個組織，聚焦在另一個與福祉相鄰的問題（認知自由、機器人具身等），並表述它的方法論。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|-----------------|------------------------|
| MATS | 「那個導師制計畫」 | ML Alignment & Theory Scholars；自 2021 年起 527 位以上研究者 |
| Redwood Research | 「那個控制實驗室」 | 應用對齊；AI 控制的作者群；英國 AISI 的合作夥伴 |
| Apollo Research | 「那些謀劃評估」 | 替前沿實驗室做部署前的謀劃評估 |
| METR | 「那些任務跨度評估」 | 以任務為基礎的能力評估；框架綜整 |
| Eleos AI | 「那個福祉實驗室」 | 模型福祉的部署前評估 |
| 人才輸送管道 | 「MATS -> 各實驗室」 | MATS 畢業生流向 Anthropic、DM、OpenAI、Redwood、Apollo、METR |
| 外部評估 | 「非實驗室的查核」 | 不是由模型生產者所做的評估；增添可信度 |

## 延伸閱讀

- [MATS (ML Alignment & Theory Scholars)](https://www.matsprogram.org/) —— 那個導師制計畫
- [Redwood Research](https://www.redwoodresearch.org/) —— AI 控制的論文
- [Apollo Research](https://www.apolloresearch.ai/) —— 謀劃評估
- [METR — Common Elements of Frontier AI Safety Policies](https://metr.org/blog/2025-03-26-common-elements-of-frontier-ai-safety-policies/) —— 框架比較
- [Eleos AI Research](https://www.eleosai.org/research) —— 模型福祉方法論
