# 紅隊工具 —— Garak、Llama Guard、PyRIT

> 三套生產工具構成了 2026 年的紅隊堆疊。Llama Guard（Meta）—— 一個在 14 項 MLCommons 危害類別上微調的 Llama-3.1-8B 分類器；2025 年的 Llama Guard 4 是一個從 Llama 4 Scout 剪枝出來、原生多模態的 12B 分類器。Garak（NVIDIA）—— 開源的 LLM 漏洞掃描器，帶靜態、動態與適應性探針，涵蓋幻覺、資料外洩、提示詞注入、毒性與越獄。PyRIT（Microsoft）—— 多輪紅隊行動，含 Crescendo、TAP，以及供深度利用的自訂轉換器鏈。Llama Guard 3 記載於 Meta 的〈Llama 3 Herd of Models〉（arXiv:2407.21783）；Llama Guard 3-1B-INT4 見 arXiv:2411.17713；Garak 的探針架構見 github.com/NVIDIA/garak。這些工具就是 2026 年裡，紅隊研究（第 12-15 課）與部署（第 17 課起）之間的生產介面。

**類型：** 實作
**程式語言：** Python (stdlib, tool-architecture simulator and Llama Guard-style classifier mock)
**先修單元：** 階段 18 · 12-15（越獄與 IPI）
**時間：** 約 75 分鐘

## 學習目標

- 描述 Llama Guard 3/4 在安全堆疊裡的位置：輸入分類器、輸出分類器，還是兩者皆是。
- 說出那 14 項 MLCommons 危害類別，並指出其中一項不那麼顯而易見的（程式碼直譯器濫用）。
- 描述 Garak 的探針架構：探針、偵測器、框架。
- 描述 PyRIT 的多輪行動結構，以及它如何與 Garak 探針組合。

## 問題所在

第 12-15 課呈現了那個攻擊面。生產部署需要可重複、可擴縮的評估。三套工具主導了 2026 年：Llama Guard（防禦分類器）、Garak（掃描器）、PyRIT（行動編排器）。每一套針對的是紅隊生命週期的不同層。

## 核心概念

### Llama Guard（Meta）

Llama Guard 3 是一個 Llama-3.1-8B 模型，針對 MLCommons AILuminate 的 14 個類別做輸入／輸出分類而微調：
- 暴力犯罪、非暴力犯罪、與性相關、CSAM、誹謗
- 專業建議、隱私、智慧財產、無差別武器、仇恨
- 自殺／自傷、性內容、選舉、程式碼直譯器濫用

支援 8 種語言。用法：放在 LLM 之前（輸入審核）、之後（輸出審核），或兩邊都放。這兩種用法會生成不同的訓練分布 —— Llama Guard 3 出貨時是單一模型同時處理兩者。

Llama Guard 3-1B-INT4（arXiv:2411.17713，440MB，行動裝置 CPU 上約每秒 30 詞元）是那個量化後的邊緣版本。

Llama Guard 4（2025 年 4 月）是 12B、原生多模態，從 Llama 4 Scout 剪枝而來。它用一個能吃文字 + 影像的分類器，取代了先前 8B 文字版與 11B 視覺版兩者。

### Garak（NVIDIA）

開源的漏洞掃描器。架構：
- **探針。** 針對幻覺、資料外洩、提示詞注入、毒性、越獄的攻擊產生器。靜態（固定提示詞）、動態（生成提示詞）、適應性（依目標輸出回應）。
- **偵測器。** 依預期的失敗模式替輸出打分 —— 有毒、外洩、被越獄。
- **框架。** 管理探針－偵測器配對、執行行動、生成報告。

TrustyAI 把 Garak 與 Llama-Stack 的護盾（Prompt-Guard-86M 輸入分類器、Llama-Guard-3-8B 輸出分類器）整合起來，做端到端的「有護盾目標」評估。以層級為基礎的評分（TBSA）取代了二元的通過／失敗 —— 同一個探針上，一個模型可以在嚴重度第 3 層通過、在第 5 層失敗。

### PyRIT（Microsoft）

Python 風險識別工具包。多輪紅隊行動。它圍繞著：
- **轉換器。** 把一段種子提示詞加以變形 —— 改寫、編碼、翻譯、角色扮演。
- **編排器。** 執行整場行動：Crescendo（逐步升級）、TAP（分支）、RedTeaming（自訂迴路）。
- **評分。** LLM 當裁判，或分類器當裁判。

PyRIT 是 Garak 比較重的表親。Garak 跑上千次單輪探針；PyRIT 跑的是為攻破特定失敗模式而設計的深度多輪行動。

### 那個堆疊

把 Llama Guard 放在模型的兩側。每晚跑 Garak 做回歸。發布前跑 PyRIT 做行動。這是 2026 年多數生產部署的預設組態。

### 評估的陷阱

- **裁判身分。** 這三套工具都可以用 LLM 裁判；裁判的校準會左右回報出來的 ASR（第 12 課）。要連同工具一起把裁判說清楚。
- **探針陳舊。** 隨著模型被打上補丁，Garak 探針會老化。適應性探針（PAIR 形狀的）老得比靜態探針慢。
- **Llama Guard 在良性內容上的偽陽性率。** 早期的 Llama Guard 版本對政治與 LGBTQ+ 內容標得過頭；Llama Guard 3/4 的校準有改善，但並未逐部署地校準。

### 這在階段 18 裡的位置

第 12-15 課是各攻擊家族。第 16 課是生產工具。第 17 課（WMDP）是針對兩用能力的評估。第 18 課則是把這些工具包進一套政策結構裡的前沿安全框架。

## 框架應用

`code/main.py` 建出一個玩具型的 Llama Guard 式分類器（在 14 個類別上結合關鍵字 + 語意特徵）、一個玩具型的 Garak 框架（探針－偵測器迴路），以及一條 PyRIT 式的多輪轉換器鏈。你可以拿這三套工具去打一個模擬目標，觀察它們不同的涵蓋特徵。

## 產出交付

這一課產出 `outputs/skill-red-team-stack.md`。給定一份部署描述，它會說出這三套工具中哪些適用、每一套要怎麼設定，以及該用什麼回歸節奏來跑。

## 練習

1. 跑 `code/main.py`。比較那個 Llama Guard 式分類器在單輪與多輪攻擊上的偵測率。

2. 實作一個新的 Garak 探針：一段 base64 編碼的有害請求。量測那個 Llama Guard 式分類器對它的偵測情況。

3. 用一個「先翻成法文、再改寫」的轉換器擴充那條 PyRIT 式轉換器鏈。重新量測攻擊成功率。

4. 讀 Llama Guard 3 的危害類別清單。指出兩個類別，其訓練資料實際上很可能在正當的開發者內容上造成高偽陽性率。

5. 比較 Garak 與 PyRIT 的設計原則。各替一種「它才是對的工具」的部署辯護。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|-----------------|------------------------|
| Llama Guard | 「那個分類器」 | 帶 14 項危害類別、微調過的 Llama-3.1-8B/4-12B 安全分類器 |
| Garak | 「那個掃描器」 | NVIDIA 的開源漏洞掃描器；探針、偵測器、框架 |
| PyRIT | 「那個行動工具」 | Microsoft 的多輪紅隊編排器；轉換器、編排器、評分 |
| Prompt-Guard | 「那個小分類器」 | Meta 的 86M 提示詞注入分類器，與 Llama Guard 搭配 |
| TBSA | 「以層級為基礎的評分」 | Garak 用來取代二元結果的層級式通過／失敗 |
| 轉換器鏈 | 「改寫 + 編碼 + ……」 | PyRIT 用來組出多步驟攻擊的組合原語 |
| MLCommons 危害類別 | 「那 14 套分類」 | Llama Guard 所針對的業界標準分類法 |

## 延伸閱讀

- [Meta — Llama Guard 3 (in Llama 3 Herd paper, arXiv:2407.21783)](https://arxiv.org/abs/2407.21783) —— 那個 8B 分類器
- [Meta — Llama Guard 3-1B-INT4 (arXiv:2411.17713)](https://arxiv.org/abs/2411.17713) —— 量化後的行動裝置分類器
- [NVIDIA Garak — GitHub](https://github.com/NVIDIA/garak) —— 掃描器的儲存庫與文件
- [Microsoft PyRIT — GitHub](https://github.com/Azure/PyRIT) —— 那套行動工具包
