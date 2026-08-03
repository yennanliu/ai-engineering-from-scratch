# OpenAI 準備度框架與 DeepMind 前沿安全框架

> OpenAI Preparedness Framework v2（2025 年 4 月）引入研究類別（Research Categories）—— 長程自主性、Sandbagging、自主複製與適應、破壞防護措施 —— 與追蹤類別（Tracked Categories）有別。追蹤類別會觸發 Capabilities Report 加 Safeguards Report，並由安全顧問小組審視。DeepMind 的 FSF v3（2025 年 9 月，2026 年 4 月 17 日加入 Tracked Capability Levels）把自主性折進 ML 研發與資安兩個領域（ML 研發自主性等級 1 = 以相對「人類 + AI 工具」具競爭力的成本完全自動化 AI 研發管線）。FSF v3 明確透過對「工具性推理濫用」的自動化監控來處理欺瞞式對齊。誠實的註記：PF v2 中的研究類別（包含長程自主性）不會自動觸發緩解措施；政策的用語是「潛在的」。DeepMind 自己也說，若工具性推理變強，自動化監控「長期而言不會維持足夠」。

**類型：** 學習
**程式語言：** Python (stdlib, three-framework decision-table diff tool)
**先修單元：** 階段 15 · 19（Anthropic RSP）
**時間：** 約 45 分鐘

## 問題所在

第 19 課細讀了 Anthropic 的擴展政策。這一課讀 OpenAI 與 DeepMind 的，把圖景補齊。這三份文件是處理同一個問題的表親產物 —— 前沿實驗室何時該暫停或替一個模型設閘門 —— 它們在一小組類別上收斂，又在一些要緊的具體地方分歧。

收斂之處：三者都把長程自主性標記為值得追蹤的能力類別。三者都承認欺瞞行為（對齊偽裝、sandbagging）是一類特定風險。三者都有一個內部審視機構。分歧之處：OpenAI 把類別分成「追蹤」（強制緩解）與「研究」（不自動觸發）。DeepMind 把自主性折進兩個領域，而不是單獨命名。實驗室各自叫它追蹤對研究、關鍵對中度，或第一級對第二級；而一項能力落在哪個桶子裡，其運維後果在各實驗室之間是不同的。

把它們放在一起讀，才是有用的練習。同一項能力，在 Anthropic 可能是「強制緩解」、在 OpenAI 是「被監控但不觸發」、在 DeepMind 是「在某個特定領域內被追蹤」。政策姿態很要緊。

## 核心概念

### OpenAI Preparedness Framework v2（2025 年 4 月）

結構：

- **追蹤類別**：觸發 Capabilities Report（模型能做什麼）加 Safeguards Report（有哪些緩解措施就位）。部署前由安全顧問小組審視。
- **研究類別**：實驗室正在追蹤、但尚未承諾具體緩解措施的模型能力。包含長程自主性、Sandbagging、自主複製與適應、破壞防護措施。

v2 中的關鍵定位：研究類別不會自動觸發緩解措施。政策用語是「潛在的」緩解。這就是要盯的那個具體差異：一項類別落在追蹤還是研究，正是「被設閘門」與「只是被觀察」之間的樞紐。

### DeepMind Frontier Safety Framework v3（2025 年 9 月；2026 年 4 月 17 日加入 Tracked Capability Levels）

結構：

- **關鍵能力等級（CCL）**：橫跨五個領域的能力門檻：資安、生物、ML 研發、CBRN、自主性（折進 ML 研發與資安）。
- **Tracked Capability Levels**：2026 年 4 月加入的額外粒度。具體例子：ML 研發自主性等級 1 = 以相對「人類 + AI 工具」具競爭力的成本完全自動化 AI 研發管線。
- **欺瞞式對齊監控**：對「工具性推理濫用」做自動化監控的明確承諾。

它替自主性定位的方式與 OpenAI 不同。DeepMind 沒有把「自主性」留成一個頂層領域；它被折進那些「自主性會造成傷害」的領域裡（ML 研發與資安）。論點是：沒有領域的自主性是沒有風險的能力；反面論點是：跨領域的自主性是一種後設風險，框架應該替它命名。

### 三者共同收斂的地方

- 內部安全顧問小組（分別叫 Anthropic SAG、OpenAI SAG、DeepMind 內部委員會）。高能力模型在部署前要審視。
- 明確提及欺瞞式對齊／對齊偽裝是一類風險。
- 依宣告節奏發布的常設產物（Anthropic：Frontier Safety Roadmap、Risk Report；OpenAI：Capabilities 與 Safeguards Report；DeepMind：FSF 更新週期）。
- 承認只靠監控的防禦有天花板。DeepMind 講得很明白：「自動化監控長期而言不會維持足夠。」

### 它們分歧的地方

- **Anthropic**：v3.0 移除了暫停承諾；AI R&D-4 門檻是被點名的下一道閘門。
- **OpenAI**：追蹤與研究的分割；研究類別（包含長程自主性）不會自動設閘門。
- **DeepMind**：自主性被折進其他領域；Tracked Capability Levels 在 2026 年 4 月加上粒度。

### Sandbagging：一項讓三者都變複雜的特定能力

Sandbagging（模型在評測上策略性地表現不佳）落在 OpenAI 的研究類別。Anthropic 的 RSP v3.0 透過評測脈絡落差（第 1 課）處理它。DeepMind 則透過 FSF v3 中的欺瞞式對齊監控處理它。

若一個模型在評測上放水，每一份框架的能力門檻就都被低估了。框架只有在量測有效時才有效。這正是為什麼除了實驗室自評之外，還需要外部量測（第 21 課，METR）與對抗性評測。

### 讀政策的技能

- 定位：每一項你在意的能力，都應該在政策裡找得到。找不到，就代表政策沒涵蓋它。
- 分類：它是追蹤（觸發緩解）還是研究（被追蹤但不觸發）？OpenAI 明確這樣命名；Anthropic 與 DeepMind 各有等價物。
- 節奏：這份政策是依宣告好的時程更新，還是只在特定事件後才更新？有宣告節奏的比較強。
- 獨立性：外部審視是強制的還是選配的？Anthropic 與 Apollo 及美國 AI 安全研究院合作；OpenAI 與 METR；DeepMind 則主要靠內部 SAG。

```figure
a5-tracked-vs-research
```

## 框架應用

`code/main.py` 實作一個小小的決策表 diff 工具。給定一項能力（自主性、欺瞞式對齊、研發自動化、資安提升等），它會輸出這三份政策各自如何分類該能力，以及會觸發什麼緩解。它是一份閱讀輔助，不是政策工具。

## 產出交付

`outputs/skill-cross-policy-diff.md` 針對某項特定能力產出一份跨政策比較，以這三份框架為參照。

## 練習

1. 跑 `code/main.py`。挑至少兩項你能對照原始文件驗證的能力，確認 diff 工具的輸出與政策相符。

2. 完整讀完 OpenAI Preparedness Framework v2。指認出每一個研究類別。對每一個各寫一句話，說明它為何落在研究而非追蹤。

3. 完整讀完 DeepMind FSF v3，加上 2026 年 4 月的 Tracked Capability Levels 更新。指認出 ML 研發自主性等級 1 的具體評測準則。你會怎麼從外部量它？

4. Sandbagging 落在 OpenAI 的研究類別。設計一項評測，能逼一個放水的模型露出它真實的能力。參照第 1 課關於評測脈絡操弄的討論。

5. 針對一項特定能力（你自己挑）比較這三份政策。說出你認為哪一份政策的分類最嚴謹、哪一份最不嚴謹。用原文佐證。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|---|---|---|
| 準備度框架 | 「OpenAI 的擴展政策」 | PF v2（2025 年 4 月）；追蹤對研究類別 |
| 追蹤類別 | 「強制緩解」 | 觸發 Capabilities + Safeguards Report；SAG 審視 |
| 研究類別 | 「只被監控」 | 被追蹤但沒有自動緩解；包含長程自主性 |
| 前沿安全框架 | 「DeepMind 的擴展政策」 | FSF v3（2025 年 9 月）+ Tracked Capability Levels（2026 年 4 月） |
| CCL | 「關鍵能力等級」 | DeepMind 逐領域的門檻（資安、生物、ML 研發、CBRN） |
| ML 研發自主性等級 1 | 「研發自動化」 | 以具競爭力的成本完全自動化 AI 研發管線 |
| Sandbagging | 「策略性表現不佳」 | 模型在評測上放水；落在 OpenAI 的研究類別 |
| 工具性推理 | 「手段—目的推理」 | 關於如何達成目標的推理；DeepMind 監控的對象 |

## 延伸閱讀

- [OpenAI — Updating our Preparedness Framework](https://openai.com/index/updating-our-preparedness-framework/) —— v2 的發布公告。
- [OpenAI — Preparedness Framework v2 PDF](https://cdn.openai.com/pdf/18a02b5d-6b67-4cec-ab64-68cdfbddebcd/preparedness-framework-v2.pdf) —— 完整文件。
- [DeepMind — Strengthening our Frontier Safety Framework](https://deepmind.google/blog/strengthening-our-frontier-safety-framework/) —— FSF v3 的發布公告。
- [DeepMind — Updating the Frontier Safety Framework (April 2026)](https://deepmind.google/blog/updating-the-frontier-safety-framework/) —— Tracked Capability Levels 的新增。
- [Gemini 3 Pro FSF Report](https://storage.googleapis.com/deepmind-media/gemini/gemini_3_pro_fsf_report.pdf) —— 一份 FSF 格式 Risk Report 的範例。
