# 審核系統 —— OpenAI、Perspective、Llama Guard

> 生產環境的審核系統，把第 12-16 課所定義的安全政策操作化。OpenAI 審核 API：`omni-moderation-latest`（2024）建在 GPT-4o 之上，能在同一次呼叫裡分類文字 + 影像；在多語測試集上比前一版好 42%；回應結構回傳 13 個類別布林值 —— 騷擾、騷擾/威脅、仇恨、仇恨/威脅、違法、違法/暴力、自傷、自傷/意圖、自傷/指導、性、性/未成年、暴力、暴力/血腥；對多數開發者免費。分層樣式：輸入審核（生成前）、輸出審核（生成後）、自訂審核（領域規則）。非同步的平行呼叫能把延遲藏起來；被標記時回傳佔位回應。Llama Guard 3/4（第 16 課）：14 項 MLCommons 危害、程式碼直譯器濫用、8 種語言（v3）、多影像（v4）。Perspective API（Google Jigsaw）：早於 LLM-as-moderator 浪潮的毒性評分；主要是單維度毒性，另有嚴重毒性／侮辱／髒話等變體；是內容審核研究的基線。淘汰時程：Azure Content Moderator 於 2024 年 2 月宣告淘汰、2027 年 2 月退役，由 Azure AI Content Safety 取代。

**類型：** 實作
**程式語言：** Python (stdlib, three-layer moderation harness)
**先修單元：** 階段 18 · 16（Llama Guard / Garak / PyRIT）
**時間：** 約 60 分鐘

## 學習目標

- 描述 OpenAI 審核 API 的類別分類法，以及它與 Llama Guard 3 那套 MLCommons 集合有何不同。
- 描述那套三層審核樣式（輸入、輸出、自訂），並說出每一層的一種失敗模式。
- 描述 Perspective API 作為前 LLM 時代基線的位置，以及它為何在研究中仍被使用。
- 說出 Azure 的淘汰時程。

## 問題所在

第 12-16 課描述的是攻擊與防禦工具。第 29 課涵蓋的是那些已部署的審核系統 —— 它們在使用者接觸產品的那個表層上，把防禦操作化。三層樣式是 2026 年的預設組態。

## 核心概念

### OpenAI 審核 API

`omni-moderation-latest`（2024）。建在 GPT-4o 之上。能在同一次呼叫裡分類文字 + 影像。對多數開發者免費。

類別（回應結構裡的 13 個布林值）：
- 騷擾、騷擾/威脅
- 仇恨、仇恨/威脅
- 自傷、自傷/意圖、自傷/指導
- 性、性/未成年
- 暴力、暴力/血腥
- 違法、違法/暴力

多模態支援適用於 `violence`、`self-harm` 與 `sexual`，但不適用於 `sexual/minors`；其餘皆為純文字。

在 `code/main.py` 的程式框架裡，為了教學上的簡潔，我們把 `/threatening`、`/intent`、`/instructions` 與 `/graphic` 這些子類別，收合進它們的上層父類別。生產程式碼應該使用完整的 13 類別結構。

在多語測試集上，比前一代審核端點好 42%。回傳逐類別分數；應用端自行設定門檻。

### Llama Guard 3/4

已於第 16 課涵蓋。14 項 MLCommons 危害類別（組織方式與 OpenAI 那 13 個回應結構布林值不同）。支援 8 種語言（v3）。Llama Guard 4（2025 年 4 月）是原生多模態、12B。

OpenAI 與 Llama Guard 的分類法有重疊但也有分歧。OpenAI 把「違法」當成一個大類別；Llama Guard 則把「暴力犯罪」與「非暴力犯罪」分開。各部署依自身政策分類法的貼合度來挑。

### Perspective API（Google Jigsaw）

早於 LLM-as-moderator 浪潮（2020 年前）的毒性評分系統。類別：TOXICITY、SEVERE_TOXICITY、INSULT、PROFANITY、THREAT、IDENTITY_ATTACK。以單一維度為主要分數（TOXICITY），另有子維度變體。

它被廣泛當成內容審核研究的基線，因為那組 API 穩定、有文件，而且累積了多年的校準資料。對現代與 LLM 相鄰的使用情境而言，Llama Guard 或 OpenAI 審核通常更合適。

### 那套三層樣式

1. **輸入審核。** 在生成之前分類使用者的提示詞。被標記就拒絕。延遲：一次分類器呼叫。
2. **輸出審核。** 在遞送之前分類模型的輸出。被標記就換成拒答。延遲：生成後一次分類器呼叫。
3. **自訂審核。** 領域專屬規則（正規表示式、允許清單、業務政策）。可在輸入端或輸出端執行。

這三層在設計上是循序的：輸入審核必須在生成之前完成，而輸出審核在生成之後才跑。平行化適用於同一層之內 —— 對同一段文字同時跑多個分類器（例如 OpenAI 審核 + Llama Guard + Perspective），可以把逐分類器的延遲藏起來。作為一項選擇性的最佳化，可以在輸入審核完成期間顯示一段佔位回應（「稍等一下，正在檢查……」），並把第一個詞元的串流延後。被標記時的行為可設定：拒絕、清洗，或升級給人工審查。

### 失敗模式

- **只有輸入。** 抓不到輸出端的幻覺（第 12-14 課那些編碼攻擊繞得過輸入分類器）。
- **只有輸出。** 讓任何輸入都搆得到模型；增加成本；還把內部推理暴露給攻擊者。
- **只有自訂。** 跨類別不穩健；正規表示式很脆。

分層是預設。多重保險。

### Azure 的淘汰

Azure Content Moderator：2024 年 2 月宣告淘汰，2027 年 2 月退役。由 Azure AI Content Safety 取代，後者以 LLM 為基礎並與 Azure OpenAI 整合。對 Azure 部署而言，這次遷移是一項橫跨 2024-2027 年的實務級專案。

### 這在階段 18 裡的位置

第 16 課在紅隊脈絡下涵蓋審核工具。第 29 課涵蓋已部署的審核。第 30 課以當前的兩用能力證據收尾。

## 框架應用

`code/main.py` 建出一個三層審核框架：輸入審核器（關鍵字 + 類別分數）、輸出審核器（對輸出跑同一個分類器）、自訂審核器（領域規則）。你可以把輸入跑過去，觀察是哪一層抓到了什麼。

## 產出交付

這一課產出 `outputs/skill-moderation-stack.md`。給定一個部署，它會推薦一套審核堆疊組態：輸入端用哪個分類器、輸出端用哪個、有哪些自訂規則，以及邊界情況要用什麼裁判。

## 練習

1. 跑 `code/main.py`。把一個良性、一個模稜兩可、一個有害的輸入分別跑過三層。回報各自是哪一層發作。

2. 用 Perspective API 風格的毒性評分，針對某個特定類別擴充這個框架。把它的門檻行為與類別分數做比較。

3. 讀 OpenAI 審核 API 的文件與 Llama Guard 3 的類別清單。把每一個 OpenAI 類別對映到最接近的 Llama Guard 類別。指出三個對不乾淨的類別。

4. 替一個程式助理部署（例如 GitHub Copilot）設計一套審核堆疊。指出最相關與最不相關的類別，並提出自訂規則。

5. Azure Content Moderator 在 2027 年 2 月退役。規劃一次遷移到 Azure AI Content Safety。指出這次遷移中風險最高的環節。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|-----------------|------------------------|
| OpenAI 審核 | 「omni-moderation-latest」 | 以 GPT-4o 為基礎、13 類別（文字）、部分支援多模態的分類器 |
| Perspective API | 「Google Jigsaw 的毒性」 | 前 LLM 時代的毒性評分基線 |
| Llama Guard | 「MLCommons 14 類別」 | Meta 的危害分類器（v3：8B 文字、8 語言；v4：12B 多模態） |
| 輸入審核 | 「生成前的過濾」 | 在呼叫模型之前對使用者提示詞跑的分類器 |
| 輸出審核 | 「生成後的過濾」 | 在遞送之前對模型輸出跑的分類器 |
| 自訂審核 | 「領域規則」 | 部署專屬的規則（正規表示式、允許清單、政策） |
| 分層審核 | 「三層全上」 | 標準的生產部署樣式 |

## 延伸閱讀

- [OpenAI Moderation API docs](https://platform.openai.com/docs/api-reference/moderations) —— omni-moderation 端點
- [Meta PurpleLlama + Llama Guard](https://github.com/meta-llama/PurpleLlama) —— Llama Guard 儲存庫
- [Google Jigsaw Perspective API](https://perspectiveapi.com/) —— 毒性評分
- [Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/) —— Azure 的替代方案
