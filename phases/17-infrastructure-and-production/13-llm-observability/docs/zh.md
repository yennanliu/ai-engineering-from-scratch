# LLM 可觀測性堆疊的選擇

> 2026 年的可觀測性市場分成兩類。開發平台（LangSmith、Langfuse、Comet Opik）把監控與評測、提示詞管理、工作階段重播綁在一起。閘道／儀器化工具（Helicone、SigNoz、OpenLLMetry、Phoenix）則聚焦在遙測上。Langfuse 核心採 MIT 授權，開源與商業的平衡拿捏得好（雲端免費層每月 5 萬事件）。Phoenix 以 OpenTelemetry 為原生、採 Elastic License 2.0 —— 對漂移／RAG 視覺化非常好，但不是一個持久的生產後端。Arize AX 用零複製的 Iceberg／Parquet 整合，宣稱比單體式可觀測性便宜 100 倍。LangSmith 在 LangChain/LangGraph 上領先，每人每月 39 美元，只有企業版才能自架。Helicone 走代理式、15-30 分鐘就設定好、每月 10 萬請求免費，但在代理軌跡上深度較淺。常見的生產模式：閘道（Helicone／Portkey）+ 評測平台（Phoenix／TruLens），由 OpenTelemetry 黏起來。

**類型：** 學習
**程式語言：** Python (stdlib, toy trace-sampling simulator)
**先修單元：** 階段 17 · 08（推論指標）、階段 14（代理工程）
**時間：** 約 60 分鐘

## 學習目標

- 分辨開發平台（綁在一起：評測 + 提示詞 + 工作階段）與閘道／遙測工具（只有軌跡 + 指標）。
- 把六個主要工具（Langfuse、LangSmith、Phoenix、Arize AX、Helicone、Opik）對映到各自的授權、定價與甜蜜點使用情境。
- 解釋那個「以 OpenTelemetry 當膠水」的模式，它讓你能把閘道工具與另一套評測平台結合起來。
- 說出 2026 年的成本差異化（Arize AX 的零複製做法 vs 單體式吞入），並指出那個約 100 倍的倍數。

## 問題所在

你出貨了一項 LLM 功能。它能用。你對提示詞失敗、工具迴圈、延遲回歸、成本尖峰或提示詞快取命中率毫無可見度。你 Google「LLM observability」，得到八個工具，全都宣稱在三種不同價位解決同一個問題。

它們解的不是同一個問題。LangSmith 回答「這趟 LangGraph 執行為什麼失敗？」Phoenix 回答「我的 RAG 管線在漂移嗎？」Helicone 回答「哪個應用在燒詞元？」Langfuse 回答「我能不能把整套自架起來？」不同的工具、不同的受眾。

挑選牽涉四條軸：技術堆疊（LangChain？原生 SDK？多廠商？）、授權容忍度（只要 MIT？Elastic 可以嗎？商業也行？）、預算（免費層？每月 100 美元？1000 美元？），以及自架（必須？有更好？絕不？）。

## 核心概念

### 兩類

**開發平台**把可觀測性跟評測、提示詞管理、資料集版本控管、工作階段重播綁在一起。你跑實驗、看哪段提示詞有效、拿新提示詞對舊贏家做資料集回歸。LangSmith、Langfuse、Comet Opik。

**閘道／遙測工具**替推論呼叫做儀器化 —— 提示詞、回應、詞元、延遲、模型、成本。Helicone、SigNoz、OpenLLMetry、Phoenix。極簡。可以透過 OpenTelemetry 與另一套評測工具結合。

### Langfuse —— 開源的平衡點

- 核心採 Apache／MIT 授權；用 Docker 自架。
- 雲端免費層：每月 5 萬事件。付費：團隊版每月 29 美元。
- 評測、提示詞管理、軌跡、資料集。四項開發平台功能都涵蓋得算合理。
- 甜蜜點：你想要 LangSmith 等級的功能，但必須自架或維持在開源授權上。

### Phoenix（Arize）—— 遙測優先、OpenTelemetry 原生

- Elastic License 2.0；自架很容易。
- 在 RAG 與漂移視覺化上非常強。嵌入空間的散佈圖是一等功能。
- 不是被設計成持久的生產後端 —— 主要是開發期的可觀測性。
- 甜蜜點：RAG 管線開發、漂移除錯，並在生產環境搭配另一個閘道。

### Arize AX —— 那個規模玩法

- 商業產品。透過 Iceberg／Parquet 做零複製的資料湖整合。
- 宣稱在規模上比單體式可觀測性（Datadog 等級）便宜約 100 倍。算法是：你把軌跡存在自己 S3 上的 Parquet 裡；Arize 直接讀。
- 甜蜜點：每天超過 1000 萬條軌跡、已有資料湖、想要 LLM 專屬儀表板但不想付 Datadog 的價。

### LangSmith —— LangChain/LangGraph 優先

- 商業產品，每人每月 39 美元。只有企業版才能自架。
- 對 LangChain 與 LangGraph 堆疊是同級最佳。若你兩者都不用，它的吸引力就低得多。
- 甜蜜點：團隊已押注 LangChain，而且願意付錢。

### Helicone —— 代理式的最小可行方案

- 把你的 `OPENAI_API_BASE` 換成 Helicone 的代理，15-30 分鐘就設定好。
- MIT 授權；每月 10 萬請求免費，付費從每月 20 美元起。
- 含故障轉移、快取、速率限制 —— 它同時也是一個閘道。
- 在代理／多步驟軌跡上的深度較淺。
- 甜蜜點：快速上手、單一堆疊的應用、需要閘道與可觀測性合而為一。

### Opik（Comet）—— 開源的開發平台

- Apache 2.0，完全開源。
- 功能集與 Langfuse 相近，帶著 Comet 的血統。
- 甜蜜點：已經在用 Comet 的 ML 團隊，想在同一塊面板上看 LLM 的可觀測性。

### SigNoz —— OpenTelemetry 優先的完整 APM

- Apache 2.0。處理一般 APM，並透過 OpenTelemetry 兼顧 LLM。
- 甜蜜點：跨服務與 LLM 呼叫的統一可觀測性。

### 那層膠水：OpenTelemetry + GenAI 語意慣例

OpenTelemetry 在 2025 年底發布了 GenAI 語意慣例（`gen_ai.system`、`gen_ai.request.model`、`gen_ai.usage.input_tokens`）。吃 OTel 的工具就能互通。正在成形的生產模式是：

1. 從每一次 LLM 呼叫發出帶 GenAI 慣例的 OTel。
2. 日常送往閘道（Helicone／Portkey）。
3. 同時分送到評測平台（Phoenix／Langfuse）以偵測回歸。
4. 歸檔到資料湖（Iceberg），供 Arize AX 或 DuckDB 做長期分析。

### 那個陷阱：在錯的層做儀器化

在你的代理框架內部做儀器化（例如加上 LangSmith 的軌跡）會把你綁在那個框架上。在 HTTP／OpenAI-SDK 那一層做儀器化（透過 OpenLLMetry 或你的閘道）才是可攜的。

### 取樣 —— 你留不住所有東西

在每天超過 100 萬個請求時，保留完整軌跡的成本會超過那些 LLM 呼叫本身。依規則取樣：錯誤 100%、高成本 100%、成功 5%。彙總值永遠留著；長尾才留原始資料。

### 你該記住的數字

- Langfuse 雲端免費層：每月 5 萬事件。
- LangSmith：每人每月 39 美元。
- Helicone 免費層：每月 10 萬請求。
- Arize AX 的宣稱：在規模上比單體式便宜約 100 倍。
- OpenTelemetry 的 GenAI 慣例：2025 年出貨，2026 年被廣泛採用。

## 框架應用

`code/main.py` 在幾種保留策略（100% 吞入、取樣、取樣 + 錯誤）之下，模擬每天 100 萬條軌跡的情境。回報儲存成本，以及每一種策略下失去了什麼。

## 產出交付

這一課產出 `outputs/skill-observability-stack.md`。給定技術堆疊、規模、預算與授權立場，挑出工具。

## 練習

1. 你在 LangChain 上的團隊想要開源、自架的可觀測性。在 Langfuse 與 Opik 之間挑一個並論證。
2. 在每天 500 萬條軌跡、Datadog 報價每月 15 萬美元的前提下，算出 Arize AX 的損益平衡。
3. 設計一組 OpenTelemetry 的 GenAI 屬性集，作為你組織的規範，要求每一次 LLM 呼叫都要帶上。
4. 論證只用 Phoenix 是否足以支撐生產環境。它在什麼時候不夠？
5. Helicone 有 20 毫秒的代理開銷。在 P99 TTFT 300 毫秒時可以接受嗎？若 SLA 是 100 毫秒呢？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| OpenLLMetry | 「給 LLM 用的 OTel」 | 給 LLM 用的開源 OpenTelemetry 儀器化 |
| GenAI 慣例 | 「OTel 屬性」 | 給 LLM 呼叫用的標準 OTel 屬性名稱 |
| LangSmith | 「LangChain 的可觀測性」 | 與 LangChain 生態系綁在一起的商業平台 |
| Langfuse | 「開源版 LangSmith」 | 功能集相近的 MIT 開源產品 |
| Phoenix | 「Arize 的開發工具」 | 以 OpenTelemetry 為原生的開發／評測平台 |
| Arize AX | 「規模化的可觀測性」 | 商業的零複製 Iceberg／Parquet 可觀測性 |
| Helicone | 「代理式的可觀測性」 | 收集 LLM 遙測、兼具閘道功能的 HTTP 代理 |
| Opik | 「Comet 的 LLM 產品」 | Comet 出品、Apache 2.0 的開源開發平台 |
| 工作階段重播 | 「軌跡重跑」 | 連同工具呼叫重播一整段代理工作階段 |
| 評測 | 「離線測試」 | 在有標註的資料集上跑候選模型／提示詞 |

## 延伸閱讀

- [SigNoz — Top LLM Observability Tools 2026](https://signoz.io/comparisons/llm-observability-tools/)
- [Langfuse — Arize AX Alternative analysis](https://langfuse.com/faq/all/best-phoenix-arize-alternatives)
- [PremAI — Setting Up Langfuse, LangSmith, Helicone, Phoenix](https://blog.premai.io/llm-observability-setting-up-langfuse-langsmith-helicone-phoenix/)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [Arize Phoenix docs](https://docs.arize.com/phoenix)
- [Helicone docs](https://docs.helicone.ai/)
