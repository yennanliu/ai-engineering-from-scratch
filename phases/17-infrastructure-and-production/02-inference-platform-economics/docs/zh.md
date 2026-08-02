# 推論平台的經濟學 —— Fireworks、Together、Baseten、Modal、Replicate、Anyscale

> 2026 年的推論市場已經不再只是租 GPU 時數。它分岔成自訂晶片（Groq、Cerebras、SambaNova）、GPU 平台（Baseten、Together、Fireworks、Modal），以及以 API 為先的市集（Replicate、DeepInfra）。Fireworks 自 2026 年 5 月 1 日起把每張 GPU 的價格調漲每小時 1 美元，而 40 億美元估值加上每天 10 兆以上詞元，告訴你這套靠量驅動的模式行得通。Baseten 在 2026 年 1 月完成 3 億美元 E 輪、估值 50 億美元。競爭定位的規則很簡單：Fireworks 最佳化延遲、Together 最佳化目錄廣度、Baseten 最佳化企業級的細緻度、Modal 最佳化 Python 原生的開發體驗、Replicate 最佳化多模態覆蓋、Anyscale 最佳化分散式 Python。這一課給你一張可以直接交給創辦人的矩陣。

**類型：** 學習
**程式語言：** Python (stdlib, toy per-call economics comparator)
**先修單元：** 階段 17 · 01（託管 LLM 平台）、階段 17 · 04（服務引擎內部）
**時間：** 約 60 分鐘

## 學習目標

- 說出那三個市場分段（自訂晶片、GPU 平台、API 為先），並把每家廠商對到一個分段。
- 解釋為何「按詞元計價」的 API 模式，會朝服務引擎的成本曲線壓縮，而不是朝硬體的成本曲線。
- 跨至少三家廠商算出每次請求的實效成本，並說明何時按分鐘（Baseten、Modal）會勝過按詞元。
- 指認出對某項給定工作負載（無伺服器突發、穩定高吞吐、微調變體、多模態），哪個平台才是對的預設。

## 問題所在

你評估過超大規模業者的託管平台。你決定需要一家更窄、更快的供應商 —— Fireworks 求延遲、Together 求廣度、Baseten 放一個微調過的自訂模型。現在你有六個實際選項，而它們的定價頁對不起來。Fireworks 標的是每百萬詞元多少錢；Baseten 標的是每分鐘；Modal 標的是每秒；Replicate 標的是每次預測。不把工作負載模型化，你就沒辦法把它們正面對比。

更糟的是，每張定價頁背後的商業模式都不一樣。Fireworks 在共享 GPU 上跑自家引擎（FireAttention）；那個按詞元的費率反映的是他們的使用率曲線。Baseten 給你 Truss + 專屬 GPU；按分鐘反映的是獨占性。Modal 是真正的 Python 無伺服器 —— 按秒計費、次秒級冷啟動。同樣的輸出（一則 LLM 回應），三種不同的成本函數。

這一課把這六家模型化，並告訴你各自何時勝出。

## 核心概念

### 三個分段

**自訂晶片** —— Groq（LPU）、Cerebras（WSE）、SambaNova（RDU）。在同一個模型上，解碼通常比 GPU 叢集快 5-10 倍。每詞元價格較高（2025 年底 Groq 在 Llama-70B 上約每百萬詞元 0.99 美元），但在對延遲敏感的使用情境上無可匹敵。Groq 是語音代理與即時翻譯的生產首選。

**GPU 平台** —— Baseten、Together、Fireworks、Modal、Anyscale。跑在 NVIDIA（2026 年是 H100、H200、B200）或有時 AMD 上。它們是介於「純 GPU 租賃」（RunPod、Lambda）與「超大規模託管服務」（Bedrock）之間的那層經濟。

**以 API 為先的市集** —— Replicate、DeepInfra、OpenRouter、Fal。目錄很廣、按預測或按秒付費，強調的是「多快能發出第一次呼叫」。

### Fireworks —— 為延遲最佳化的 GPU 平台

- FireAttention 引擎（自訂）；行銷上宣稱在等價設定下比 vLLM 低 4 倍延遲。
- 批次層級約為無伺服器費率的 50%，供非互動式工作負載使用。
- 微調過的模型與基礎模型同價 —— 相對那些替你的 LoRA 加價的供應商，這是實打實的差異化。
- 2026 年年中：自 2026 年 5 月 1 日起，隨需 GPU 租賃每小時調漲 1 美元。規模夠大時量價可談。
- 財務訊號：40 億美元估值、每天處理 10 兆以上詞元。

### Together —— 為廣度最佳化

- 200 種以上模型，包括在上游發布後幾天內就上架的開源版本。
- 在等價的 LLM 模型上比 Replicate 便宜 50-70% —— 那個「AI 原生雲」的定位講的就是量與目錄。
- 推論 + 微調 + 訓練都在同一組 API。

### Baseten —— 為企業級細緻度最佳化

- Truss 框架：把相依、密鑰、服務設定打包進同一份 manifest 的模型封裝。
- GPU 從 T4 到 B200。按分鐘計費，冷啟動緩解做得還不錯。
- SOC 2 Type II、HIPAA-ready。金融科技與醫療常見的選擇。
- 50 億美元估值，2026 年 1 月 E 輪（來自 CapitalG、IVP、NVIDIA 的 3 億美元）。

### Modal —— 為 Python 原生最佳化

- 用純 Python 寫的基礎設施即程式碼。在函數上加 `@modal.function(gpu="A100")` 裝飾器，一行指令就部署。
- 按秒計費。有預熱時冷啟動 2-4 秒；小模型 <1 秒。
- 8,700 萬美元 B 輪、估值 11 億美元（2025）。在獨立調查中開發者體驗分數最高。

### Replicate —— 多模態的廣度

- 按預測計費。影像、影片與音訊模型的預設平台。
- 整合生態系（Zapier、Vercel、CMS 外掛）。
- 在 LLM 的每詞元費率上競爭力較弱，但在多模態的多樣性上勝出。

### Anyscale —— Ray 原生

- 建構在 Ray 之上；RayTurbo 是 Anyscale 自有的推論引擎（與 vLLM 競爭）。
- 最適合那種「推論只是更大的圖裡一個節點」的分散式 Python 工作負載。
- 託管的 Ray 叢集；與 Ray AIR 及 Ray Serve 緊密整合。

### 按詞元對上按分鐘 —— 各自何時勝出

當工作負載對延遲不敏感且突發時，按詞元說得通 —— 你只為用掉的付錢。當使用率高且可預測時，按分鐘說得通 —— 一旦你把 GPU 餵飽，它就勝過按詞元。

粗略規則：對於專屬 GPU 上持續使用率超過約 30% 的工作負載，按分鐘（Baseten、Modal）開始勝過按詞元（Fireworks、Together）。低於這個數，按詞元勝出，因為你避開了替閒置付錢。

### 自訂引擎才是那道真正的護城河

vLLM 與 SGLang 之上的每個平台都宣稱有自訂引擎。FireAttention、RayTurbo、Baseten 的推論堆疊。自訂引擎的宣稱帶著行銷成分 —— 誠實的說法是：vLLM + SGLang 大約占了生產環境開源推論的 80%，而平台層的差異化在於開發體驗、歸屬與 SLA。

### 你該記住的數字

- Fireworks GPU 租賃：自 2026 年 5 月 1 日起每小時調漲 1 美元。
- Fireworks 的宣稱：在等價設定下比 vLLM 低 4 倍延遲。
- Together：在 LLM 上比 Replicate 便宜 50-70%。
- Baseten 估值：50 億美元（E 輪，2026 年 1 月，3 億美元）。
- Modal 估值：11 億美元（B 輪，2025）。
- 持續使用率超過約 30% 時，按分鐘勝過按詞元。

```figure
cost-per-token
```

## 框架應用

`code/main.py` 在一份合成工作負載上，跨不同計價模式比較這六家廠商。回報每日金額與實效的每百萬詞元金額。跑它，找出按詞元與按分鐘之間的損益平衡。

## 產出交付

這一課產出 `outputs/skill-inference-platform-picker.md`。給定工作負載輪廓、SLA 與預算，挑出主要的推論平台並點名亞軍。

## 練習

1. 跑 `code/main.py`。對一張 H100 上的 70B 模型，在什麼持續使用率下 Baseten（按分鐘）會勝過 Fireworks（按詞元）？自己推導那個交叉點，並跟拇指法則比較。
2. 你的產品同時提供影像生成、聊天與語音轉文字。替每種模態挑平台，並點名把它們統一起來的閘道模式。
3. Fireworks 把你主要模型的價格每小時調漲 1 美元。若有 40% 的流量移到批次層級（打五折），把混合後的成本影響模型化。
4. 一位受監管的客戶要求 SOC 2 Type II + HIPAA + 專屬 GPU。哪三個平台可行，而哪一個在 FinOps 上勝出？
5. 比較 Llama 3.1 70B 在 Fireworks 無伺服器、Together 隨需、Baseten 專屬與 Replicate API 上，每 1,000 次預測的成本。在每天 10 次預測時哪個最便宜？每天 10,000 次呢？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| 自訂晶片 | 「非 GPU 的晶片」 | Groq LPU、Cerebras WSE、SambaNova RDU —— 為解碼而最佳化 |
| FireAttention | 「Fireworks 的引擎」 | 自訂的注意力核心；行銷上宣稱比 vLLM 低 4 倍延遲 |
| Truss | 「Baseten 的格式」 | 模型封裝 manifest；相依 + 密鑰 + 服務設定 |
| 按詞元 | 「API 計價」 | 依消耗的詞元計費；不必替閒置付錢 |
| 按分鐘 | 「專屬計價」 | 依牆鐘 GPU 時間計費；高使用率時勝出 |
| 按預測 | 「Replicate 的計價」 | 依模型調用次數計費；影像／影片常用 |
| RayTurbo | 「Anyscale 的引擎」 | 建在 Ray 上的自有推論引擎；在 Ray 叢集上與 vLLM 競爭 |
| 批次層級 | 「打五折」 | 費率較低的非互動式佇列；Fireworks、OpenAI 常見 |
| 微調也算基礎價 | 「Fireworks 的 LoRA」 | 以基礎模型的費率計算 LoRA 服務的請求（差異化） |

## 延伸閱讀

- [Fireworks Pricing](https://fireworks.ai/pricing) —— 按詞元費率、批次層級、GPU 租賃。
- [Baseten Pricing](https://www.baseten.co/pricing/) —— 按分鐘費率、承諾容量、企業層級。
- [Modal Pricing](https://modal.com/pricing) —— 按秒的 GPU 費率與免費層級。
- [Together AI Pricing](https://www.together.ai/pricing) —— 模型目錄與按詞元費率。
- [Anyscale Pricing](https://www.anyscale.com/pricing) —— RayTurbo 與託管 Ray 的定價。
- [Northflank — Fireworks AI Alternatives](https://northflank.com/blog/7-best-fireworks-ai-alternatives-for-inference) —— 比較性的評估。
- [Infrabase — AI Inference API Providers 2026](https://infrabase.ai/blog/ai-inference-api-providers-compared) —— 廠商版圖。
