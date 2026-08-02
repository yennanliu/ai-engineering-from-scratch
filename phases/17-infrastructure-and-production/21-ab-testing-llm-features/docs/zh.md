# 對 LLM 功能做 A/B 測試 —— GrowthBook、Statsig 與那個「感覺」問題

> 傳統 A/B 測試不是為非決定性的 LLM 打造的。那個關鍵區別是：評測回答「這模型做得了這件事嗎？」；A/B 測試回答「使用者在乎嗎？」兩者都必要；靠感覺出貨的時代結束了。2026 年該測什麼：提示詞工程（措辭）、模型選擇（GPT-4 對 GPT-3.5 對開源；準確率對成本對延遲）、生成參數（temperature、top-p）。真實案例：某個聊天機器人的獎勵模型變體帶來 +70% 的對話長度與 +30% 的留存；Nextdoor 的 AI 主旨行實驗在調整獎勵函式後帶來 +1% 點擊率；可汗學院的 Khanmigo 在「延遲對數學正確率」這條軸上反覆迭代。平台分佈：**Statsig**（2025 年 9 月被 OpenAI 以 11 億美元收購）—— 序貫測試、CUPED、一站式。**GrowthBook** —— 開源、倉儲原生、貝氏 + 頻率論 + 序貫三種引擎、CUPED、SRM 檢查、Benjamini-Hochberg + Bonferroni 校正。你依「偏不偏好倉儲 SQL」以及「被 OpenAI 收購對你的組織要不要緊」來挑。

**類型：** 學習
**程式語言：** Python (stdlib, toy sequential test simulator)
**先修單元：** 階段 17 · 13（可觀測性）、階段 17 · 20（漸進式部署）
**時間：** 約 60 分鐘

## 學習目標

- 分辨評測（「這模型做得了這件事嗎」）與 A/B 測試（「使用者在乎嗎」）。
- 列舉三條可測試的軸（提示詞、模型、參數），並替每一條挑出指標。
- 解釋 CUPED、序貫測試，以及 Benjamini-Hochberg 的多重比較校正。
- 依倉儲 SQL 的姿態與對企業收購的立場，在 Statsig 與 GrowthBook 之間挑一個。

## 問題所在

你手動調了一段系統提示詞。感覺變好了。你出貨。轉換率的變化落在噪音裡。你怪那個指標。或者你上了一個新模型而轉換率沒動 —— 是模型退步了，還是那個變化太小偵測不到？你不知道，因為你沒做 A/B 就出貨了。

評測回答的是「模型在一份已標註集上做不做得了某項任務」。它們不回答使用者是否偏好那個輸出。只有受控的線上實驗才回答得了，而且前提是實驗有足夠檢定力、控制住了非決定性，並對多重比較做了校正。

## 核心概念

### 評測對上 A/B 測試

**評測** —— 離線、已標註集、裁判（評分準則、LLM-as-judge，或人類）。回答：「在這個固定分布上，輸出正確／有幫助／安全嗎？」

**A/B 測試** —— 線上、真實使用者、隨機化。回答：「新變體有沒有推動那個要緊的使用者層級指標？」

兩者都必要。評測在暴露前抓退化；A/B 在之後確認產品影響。

### 該測什麼

1. **提示詞工程** —— 措辭、系統提示詞結構、範例。指標：任務成功率、使用者留存、每請求成本。
2. **模型選擇** —— GPT-4 對 GPT-3.5-Turbo 對 Llama 開源版。指標：準確率（任務）+ 每請求成本 + 延遲 P99。多目標。
3. **生成參數** —— temperature、top-p、max_tokens。指標：因任務而異（輸出多樣性對決定性）。

### CUPED —— 變異數縮減

Controlled-experiments Using Pre-Experiment Data（用實驗前資料的受控實驗）。在比較實驗後期間之前，先把實驗前期間的變異數迴歸掉。典型變異數縮減：30-70%。有效樣本數免費上升。

實作：Statsig 與 GrowthBook 都有。

### 序貫測試

古典 A/B 假設樣本數固定。序貫測試（「邊看邊決定」）在反覆檢視之下控制住偽陽性率。永遠有效的序貫程序（mSPRT、Howard 的信賴序列）讓你在贏家明顯時提早停止。

### 多重比較校正

在 95% 信心水準下跑 20 次 A/B 測試，光靠機率就會出現一個偽陽性。Bonferroni 校正把每次測試的 α 收緊；Benjamini-Hochberg 控制偽發現率。GrowthBook 兩種都實作了。

### SRM —— 樣本比例失配

指派雜湊把使用者隨機分到各變體。若 50/50 的切分實際是 47/53，就有東西壞了 —— SRM 檢查會把它標出來。兩個平台都有實作。

### Statsig 對上 GrowthBook

**Statsig**：
- 被 OpenAI 以 11 億美元收購（2025 年 9 月）。託管、SaaS。
- 序貫測試、CUPED、保留族群。
- 一站式：功能旗標 + 實驗 + 可觀測性。
- 最適合：團隊本來就想要一套綁在一起的產品，也不在意 OpenAI 的所有權。

**GrowthBook**：
- 開源（MIT）；倉儲原生（直接讀 Snowflake/BigQuery/Redshift）。
- 多種引擎：貝氏、頻率論、序貫。
- CUPED、SRM、Bonferroni、BH 校正。
- 可自架，也有託管雲。
- 最適合：以倉儲 SQL 為主的團隊、資料團隊掌控指標層、想要開源。

### 非決定性讓檢定力變複雜

同一段提示詞會產出變動的輸出。傳統檢定力計算假設觀測是獨立同分布的。有了 LLM 的非決定性，有效樣本數比名目上低。把所需樣本數乘上約 1.3-1.5 倍當安全邊際。

### 真實案例的結果

- 聊天機器人的獎勵模型變體：+70% 對話長度、+30% 留存。
- Nextdoor 的主旨行：調整獎勵函式後 +1% 點擊率。
- 可汗學院 Khanmigo：在延遲與數學正確率之間反覆權衡。

### 那個反模式：靠感覺出貨

每位資深工程師都講得出某個因為「感覺比較好」而在沒有 A/B 之下出貨的功能。它們大多讓產品指標退步了，而團隊好幾個月都沒發現。A/B 就是那個強制機制。

### 你該記住的數字

- Statsig 被 OpenAI 收購：11 億美元，2025 年 9 月。
- GrowthBook：MIT 開源；貝氏 + 頻率論 + 序貫。
- CUPED 的變異數縮減：30-70%。
- LLM 的非決定性 → 樣本數要多留 30-50% 的緩衝。

## 框架應用

`code/main.py` 以固定邊界與序貫邊界模擬一次序貫 A/B 測試。展示序貫如何讓你提早停止。

## 產出交付

這一課產出 `outputs/skill-ab-plan.md`。給定功能變更、工作負載與基線，挑出平台、閘門與樣本數。

## 練習

1. 跑 `code/main.py`。在基線轉換率 3%、預期提升 5% 的情況下，要達到 80% 檢定力需要多少樣本數？
2. 替一位受醫療法規管制、要部署在自有機房的客戶，在 Statsig 與 GrowthBook 之間挑一個。
3. 設計一次在「每張已解決工單成本」上測試 GPT-4 對 GPT-3.5 的 A/B。主要指標、護欄指標、次要指標各是什麼？
4. 你的金絲雀通過了，但 A/B 顯示轉換率 -1.2%。你出貨嗎？把升級判準寫出來。
5. 對一段變異數為實驗後期間 60% 的實驗前期間套用 CUPED。算出有效樣本數的提升。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| 評測 | 「離線測試」 | 對模型能力所做的已標註集評估 |
| A/B 測試 | 「實驗」 | 對使用者做的線上隨機化比較 |
| CUPED | 「變異數縮減」 | 用實驗前期間的迴歸來降低變異數 |
| 序貫測試 | 「可以偷看的測試」 | 允許提早停止、永遠有效的程序 |
| 多重比較 | 「族系錯誤」 | 跑很多次測試會膨脹偽陽性 |
| Bonferroni | 「嚴格校正」 | 把 α 除以測試次數 |
| Benjamini-Hochberg | 「BH FDR」 | 偽發現率控制，比較不保守 |
| SRM | 「切分壞了」 | 樣本比例失配；指派的臭蟲 |
| Statsig | 「OpenAI 持有的」 | 商業一站式平台，2025 年被收購 |
| GrowthBook | 「那個開源的」 | MIT 授權、倉儲原生的平台 |
| mSPRT | 「序貫機率比檢定」 | 古典的序貫程序 |

## 延伸閱讀

- [GrowthBook — How to A/B Test AI](https://blog.growthbook.io/how-to-a-b-test-ai-a-practical-guide/)
- [Statsig — Beyond Prompts: Data-Driven LLM Optimization](https://www.statsig.com/blog/llm-optimization-online-experimentation)
- [Statsig vs GrowthBook comparison](https://www.statsig.com/perspectives/ab-testing-feature-flags-comparison-tools)
- [Deng et al. — CUPED](https://www.exp-platform.com/Documents/2013-02-CUPED-ImprovingSensitivityOfControlledExperiments.pdf)
- [Howard — Confidence Sequences](https://arxiv.org/abs/1810.08240)
