# 對 LLM API 做負載測試 —— 為什麼 k6 與 Locust 會說謊

> 傳統負載測試工具不是為串流回應、可變輸出長度、詞元層級指標，或 GPU 飽和而設計的。有兩個陷阱咬到大多數團隊。GIL 陷阱：Locust 的詞元層級量測是在 Python GIL 之下跑分詞的，在高併發時會跟請求產生互相競爭；分詞積壓接著就灌大了回報出來的詞元間延遲 —— 瓶頸是你的客戶端，不是伺服器。提示詞一致性陷阱：迴圈裡送一樣的提示詞，只測到詞元分布上的一個點；真實流量有可變長度與多樣的前綴相符。LLMPerf 用 `--mean-input-tokens` + `--stddev-input-tokens` 解決這件事。2026 年的工具對照：詞元層級準確的 LLM 專用工具（GenAI-Perf、LLMPerf、LLM-Locust、guidellm）；**k6 v2026.1.0** + **k6 Operator 1.0 GA（2025 年 9 月）** —— 感知串流、透過 TestRun/PrivateLoadZone CRD 做 Kubernetes 原生的分散式測試，最適合 CI/CD 閘門；Vegeta 用於 Go 的定速飽和測試；Locust 2.43.3 只有配上 LLM-Locust 擴充才適合串流。負載樣式：穩態、爬坡、尖峰（測自動擴縮）、浸泡（測記憶體洩漏）。

**類型：** 實作
**程式語言：** Python (stdlib, toy realistic-prompt generator + latency collector)
**先修單元：** 階段 17 · 08（推論指標）、階段 17 · 03（GPU 自動擴縮）
**時間：** 約 75 分鐘

## 學習目標

- 解釋讓通用負載測試工具在 LLM API 上說謊的那兩個反模式（GIL 陷阱、提示詞一致性陷阱）。
- 依用途挑工具：LLMPerf（基準跑測）、k6 + 串流擴充（CI 閘門）、guidellm（大規模合成）、GenAI-Perf（NVIDIA 參考實作）。
- 設計四種負載樣式（穩態、爬坡、尖峰、浸泡），並說出各自抓得到的失敗模式。
- 用輸入詞元的平均值 + 標準差，而不是固定長度，建出一份真實的提示詞分布。

## 問題所在

你用 k6 在 500 個併發使用者下測了你的 LLM 端點。它撐住了。你出貨。到了生產環境，200 個真實使用者就把服務打趴 —— P99 TTFT 爆炸，GPU 滿載。

發生了兩件事。第一，k6 送的是 500 個一模一樣的提示詞 —— 你的請求合併與前綴快取，讓它看起來像是你在處理 500 個併發解碼，其實你只處理了一個。第二，k6 不會用眼睛所感受到的方式，去追蹤串流回應上的詞元間延遲；它看到的是一條 HTTP 連線，不是 500 個以不同間隔抵達的詞元。

對 LLM 做負載測試自成一門學問。

## 核心概念

### GIL 陷阱（Locust）

Locust 用 Python，而且在 GIL 之下於客戶端跑分詞。在高併發下，分詞器會排在請求產生的後面。回報出來的詞元間延遲，包含了客戶端的分詞積壓。你以為伺服器慢；其實是測試框架。

修法：LLM-Locust 擴充把分詞搬到獨立行程，或改用編譯語言寫的框架（k6、用 tokenizers.rs 的 LLMPerf）。

### 提示詞一致性陷阱

所有已知的負載測試工具都讓你設定「一個」提示詞。在 10,000 次迭代的迴圈測試裡，每次送的都是同一段提示詞。伺服器每次看到同樣的前綴 —— 前綴快取命中率逼近 100%，吞吐量看起來棒極了。

修法：從一份提示詞分布中取樣。LLMPerf 用 `--mean-input-tokens 500 --stddev-input-tokens 150` —— 長度多樣、內容多樣。

### 四種負載樣式

1. **穩態** —— 固定 RPS 跑 30-60 分鐘。抓得到：基線效能退化。
2. **爬坡** —— 在 15 分鐘內把 RPS 從 0 線性拉到目標。抓得到：容量斷點、暖機異常。
3. **尖峰** —— 突然拉到 3-10 倍 RPS 撐 2 分鐘再回來。抓得到：自動擴縮的延遲、佇列飽和、冷啟動衝擊。
4. **浸泡** —— 穩態跑 4-8 小時。抓得到：記憶體洩漏、連線池漂移、可觀測性溢位。

### 2026 年的工具對照

**LLMPerf**（Anyscale）—— Python，但分詞由 Rust 撐。平均／標準差提示詞。感知串流。做效能跑測時最好的預設。

**NVIDIA GenAI-Perf** —— NVIDIA 的參考實作。用 Triton 客戶端；指標涵蓋完整。注意它的 ITL 不含 TTFT；LLMPerf 的則含。同一台伺服器，兩套工具會給出不同的 TPOT。

**LLM-Locust**（TrueFoundry）—— 修掉 GIL 陷阱的 Locust 擴充。熟悉的 Locust DSL + 串流指標。

**guidellm** —— 大規模的合成基準測試。

**k6 v2026.1.0** + **k6 Operator 1.0 GA（2025 年 9 月）**：
- k6 本身（Go、編譯型、沒有 GIL）加上了感知串流的指標。
- k6 Operator 用 TestRun / PrivateLoadZone CRD 做 Kubernetes 原生的分散式測試。
- 最適合 CI/CD 閘門與 SLA 測試。

**Vegeta** —— Go，比 k6 更簡單。定速的 HTTP 飽和測試。不感知 LLM，但拿來測閘道／速率限制很好用。

**Locust 2.43.3 原版** —— 對 LLM 有 GIL 陷阱。只有搭配 LLM-Locust 擴充才行。

### CI 裡的 SLA 閘門

在 PR 上跑 k6，設定為：

- 在基線 RPS 下各跑 30-50 次迭代。
- 閘門：P50/P95 TTFT、5xx < 5%、TPOT 低於門檻。
- 違規就讓建置失敗。

### 真實的提示詞分布

從真實流量樣本建（如果你有的話），或從已發表的分布建（例如聊天用 ShareGPT 的提示詞、程式碼用 HumanEval）。把平均值 + 標準差餵給 LLMPerf。不計代價避開「一個提示詞跑迴圈」。

### 你該記住的數字

- k6 Operator 1.0 GA：2025 年 9 月。
- k6 v2026.1.0：感知串流的指標。
- 典型的 LLMPerf 跑測：在併發 X 下 100-1000 個請求。
- 典型的 CI 閘門：每個 PR 30-50 次迭代。
- 四種樣式：穩態、爬坡、尖峰、浸泡。

```figure
load-pattern-waves
```

## 框架應用

`code/main.py` 用真實的提示詞分布模擬一次負載測試，量測有效 TPOT，並示範那個一致提示詞的陷阱。

## 產出交付

這一課產出 `outputs/skill-load-test-plan.md`。給定工作負載與 SLA，挑出工具並設計那四種負載樣式。

## 練習

1. 跑 `code/main.py`。比較一致分布與真實分布 —— 差距在哪裡？
2. 替一道 CI 閘門寫出 k6 腳本：100 併發下 TTFT P95 < 800 毫秒，執行 5 分鐘。
3. 你的浸泡測試顯示記憶體每小時成長 50 MB。說出三個原因，以及用來在它們之間分辨的檢測手段。
4. 從 10 RPS 尖峰拉到 100 RPS。若已經有 Karpenter + vLLM production-stack（階段 17 · 03 + 18），預期的恢復時間是多少？
5. 同一台伺服器上 GenAI-Perf 回報 TPOT=6 毫秒；LLMPerf 回報 TPOT=11 毫秒。解釋一下。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| LLMPerf | 「那個 LLM 框架」 | Anyscale 的基準工具，感知串流 |
| GenAI-Perf | 「NVIDIA 的工具」 | NVIDIA 的參考框架 |
| LLM-Locust | 「給 LLM 用的 Locust」 | 修掉 GIL 陷阱的 Locust 擴充 |
| guidellm | 「合成基準」 | 大規模的合成工具 |
| k6 Operator | 「K8s 版 k6」 | 以 CRD 為基礎的分散式 k6 |
| GIL 陷阱 | 「Python 客戶端開銷」 | 分詞積壓灌大了回報的延遲 |
| 提示詞一致性陷阱 | 「單一提示詞的謊言」 | 同提示詞跑迴圈會命中快取、灌大吞吐量 |
| 穩態 | 「固定負載」 | 平坦的 RPS 跑 N 分鐘 |
| 爬坡 | 「線性往上」 | 在一段時間內從 0 拉到目標 |
| 尖峰 | 「突發測試」 | 突然乘上倍數再回復 |
| 浸泡 | 「長時間測試」 | 跑數小時以偵測洩漏 |

## 延伸閱讀

- [TianPan — Load Testing LLM Applications](https://tianpan.co/blog/2026-03-19-load-testing-llm-applications)
- [PremAI — Load Testing LLMs 2026](https://blog.premai.io/load-testing-llms-tools-metrics-realistic-traffic-simulation-2026/)
- [NVIDIA NIM — Introduction to LLM Inference Benchmarking](https://docs.nvidia.com/nim/large-language-models/1.0.0/benchmarking.html)
- [TrueFoundry — LLM-Locust](https://www.truefoundry.com/blog/llm-locust-a-tool-for-benchmarking-llm-performance)
- [LLMPerf](https://github.com/ray-project/llmperf)
- [k6 Operator](https://github.com/grafana/k6-operator)
