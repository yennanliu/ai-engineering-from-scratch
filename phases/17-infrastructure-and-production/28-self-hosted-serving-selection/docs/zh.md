# 自架服務的選型 —— 把引擎對到硬體與規模

> 引擎選型是硬體、規模與生態系的函數 —— 不是看排行榜。2026 年主宰自架推論的有四套引擎：llama.cpp、Ollama、vLLM、SGLang，而 TGI 落在維護模式裡跟在後頭。**llama.cpp** 在 CPU 上最快 —— 模型支援最廣，對量化與執行緒有完整掌控。**Ollama** 是開發筆電上一行指令就裝好的那個，比 llama.cpp 慢約 15-30%（Go + CGo + HTTP 序列化），在近似生產的負載下有 3 倍的吞吐量差距。**TGI 於 2025 年 12 月 11 日進入維護模式** —— 只修臭蟲，原始吞吐量比 vLLM 慢約 10%，但歷來在可觀測性與 HF 生態系整合上都名列前茅。那個維護狀態讓它成為長期上的高風險押注 —— 新專案的安全預設是 SGLang 或 vLLM。**vLLM** 是通用型的生產預設 —— v0.15.1（2026 年 2 月）加上 PyTorch 2.10、RTX Blackwell SM120、H200 最佳化。**SGLang** 是代理型多輪／前綴吃重的專家 —— 生產環境有 400,000+ 張 GPU（xAI、LinkedIn、Cursor、Oracle、GCP、Azure、AWS）。硬體限制：CPU 優先 → llama.cpp。AMD／非 NVIDIA → vLLM 是支援最強的路徑（TRT-LLM 綁死 NVIDIA）。2026 年的管線模式：開發用 Ollama，預備用 llama.cpp，生產用 vLLM 或 SGLang。這些引擎吃的權重格式不同 —— llama.cpp 家族吃 GGUF，GPU 引擎吃 HF safetensors —— 所以階段之間可能會夾一次格式轉換。

**類型：** 學習
**程式語言：** Python (stdlib, engine-decision tree walker)
**先修單元：** 階段 17 中所有涵蓋引擎的課程（04、06、07、09、18）
**時間：** 約 45 分鐘

## 學習目標

- 依硬體（CPU／AMD／NVIDIA Hopper／Blackwell）、規模（1 位使用者／100／10,000）與工作負載（一般聊天／代理／長脈絡）挑出一套引擎。
- 說出 2026 年 TGI 的維護模式狀態（2025 年 12 月 11 日），以及它為何讓新專案偏向 vLLM 或 SGLang。
- 描述開發／預備／生產的管線，包含 GGUF 轉 safetensors 的格式轉換夾在哪兩個階段之間。
- 解釋為何「CPU 優先」指向 llama.cpp，而「AMD」排除掉 TRT-LLM。

## 問題所在

你的團隊要開一個新的自架 LLM 專案。一位工程師說用 Ollama，另一位說用 vLLM，第三位說「TGI 不是開箱就能跑嗎？」在不同脈絡下三個人都對。沒有一個對所有情況都對。

在 2026 年，那棵決策樹要緊：硬體第一、規模第二、工作負載第三。而 2025 年有一件事 —— TGI 在 12 月 11 日進入維護模式 —— 改變了新專案的預設。

## 核心概念

### 那五套引擎

| 引擎 | 最適合 | 備註 |
|--------|----------|-------|
| **llama.cpp** | CPU／邊緣／最少相依／最廣的模型支援 | CPU 上最快，掌控完整 |
| **Ollama** | 開發筆電、單一使用者、一行指令安裝 | 比 llama.cpp 慢 15-30%；生產吞吐量差 3 倍 |
| **TGI** | HF 生態系、受管制產業 | **2025 年 12 月 11 日進入維護模式** |
| **vLLM** | 通用型生產、100+ 使用者 | 廣泛的生產預設；v0.15.1，2026 年 2 月 |
| **SGLang** | 代理型多輪、前綴吃重的工作負載 | 生產環境有 400,000+ 張 GPU |

### 硬體優先的決定

**CPU 優先** → llama.cpp。Ollama 也行但比較慢。在 CPU 上沒有別的引擎有競爭力。

**AMD GPU** → vLLM 是支援最強的路徑（AMD ROCm 支援）。SGLang 也行。TRT-LLM 綁死 NVIDIA，所以出局。

**NVIDIA Hopper（H100／H200）** → vLLM、SGLang 或 TRT-LLM。三者都是頂級。

**NVIDIA Blackwell（B200／GB200）** → TRT-LLM 是吞吐量領先者（階段 17 · 07）。vLLM 與 SGLang 緊追在後。

**Apple Silicon（M 系列）** → llama.cpp（Metal）。Ollama 是包在它外面的。

### 規模第二的決定

**1 位使用者／本地開發** → Ollama。一行指令，幾秒鐘出第一個詞元。

**10-100 位使用者／小團隊** → vLLM 單 GPU。

**100-10k 位使用者／生產** → vLLM production-stack（階段 17 · 18）或 SGLang。

**10k+ 位使用者／企業** → vLLM production-stack + 分離式（階段 17 · 17）+ LMCache（階段 17 · 18）。

### 工作負載第三的決定

**一般聊天／問答** → vLLM 以廣泛預設勝出。

**代理型多輪（工具、規劃、記憶）** → SGLang 的 RadixAttention（階段 17 · 06）壓倒性領先。

**前綴重用吃重的 RAG** → SGLang。

**程式碼生成** → vLLM 沒問題；SGLang 在快取上稍好。

**長脈絡（128K+）** → vLLM + 分塊預填；SGLang + 分層 KV。

### TGI 的維護陷阱

Hugging Face 的 TGI 在 2025 年 12 月 11 日進入維護模式 —— 往後只修臭蟲。歷來：頂級的可觀測性、業界最佳的 HF 生態系整合（模型卡、安全工具），原始吞吐量稍落後 vLLM。

2026 年的新專案：預設避開 TGI。既有的 TGI 部署可以繼續跑，但終究該遷移。SGLang 與 vLLM 是比較安全的預設。

### 那個管線模式

開發（Ollama）→ 預備（llama.cpp）→ 生產（vLLM）。這些引擎吃的權重格式不同 —— llama.cpp 家族吃 GGUF，GPU 引擎吃 HF safetensors —— 所以階段之間可能會夾一次格式轉換。工程師在筆電上快速迭代；預備環境對齊生產的量化；生產才是服務的目標。

### Ollama 的但書

Ollama 拿來開發很棒。拿來做共享的生產環境就不太行：Go 的 HTTP 序列化增加開銷，併發管理比 vLLM 陽春，OpenTelemetry 支援落後。在它發光的地方用它 —— 一位使用者、一行指令 —— 要共享就換成 vLLM。

### 自架對上託管是另一個決定

階段 17 · 01（託管的超大規模雲）、· 02（推論平台）談的是託管。這一課假設你已經決定要自架了。自架的理由：資料落地、自訂微調、規模化下的總體擁有成本、託管上沒有的領域模型。

### 你該記住的數字

- TGI 維護模式：2025 年 12 月 11 日。
- vLLM v0.15.1：2026 年 2 月；PyTorch 2.10；支援 Blackwell SM120。
- SGLang 的生產足跡：400,000+ 張 GPU。
- Ollama 相對 llama.cpp 的吞吐量差距：慢 15-30%；生產負載下差 3 倍。

```figure
data-parallel
```

## 框架應用

`code/main.py` 是一支決策樹走訪器：給定硬體 + 規模 + 工作負載，挑出一套引擎並解釋原因。

## 產出交付

這一課產出 `outputs/skill-engine-picker.md`。給定限制條件，挑出一套引擎並寫出遷移計畫。

## 練習

1. 用你自己的硬體／規模／工作負載跑 `code/main.py`。輸出符合你的直覺嗎？
2. 你的基礎設施是 12 張 H100 與 8 張 AMD MI300X。要用什麼引擎？TRT-LLM 為什麼出局？
3. 有個團隊想在 2026 年用 TGI，因為「那是我們熟的東西」。把遷移的理由論證出來。
4. 從 Ollama 開發到 vLLM 生產：量化、組態與可觀測性上各有什麼改變？
5. 一個 P99 前綴長度 8K、且跨租戶重用度高的 RAG 產品。挑一套引擎，並把它跟階段 17 · 11 + 18 疊起來。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| llama.cpp | 「那個 CPU 的」 | 模型支援最廣，CPU 上最快 |
| Ollama | 「那個筆電的」 | 一行指令安裝，開發等級的吞吐量 |
| TGI | 「HF 的服務」 | 自 2025 年 12 月起維護模式 |
| vLLM | 「那個預設的」 | 2026 年廣泛的生產基準線 |
| SGLang | 「那個代理型的」 | 前綴吃重、RadixAttention |
| TRT-LLM | 「綁死 NVIDIA 的」 | Blackwell 吞吐量領先者，只支援 NVIDIA |
| GGUF | 「llama.cpp 的格式」 | 內含各種 K-quant 變體 |
| Production-stack | 「vLLM 的 K8s 版」 | 階段 17 · 18 的參考部署 |
| 管線模式 | 「開發→預備→生產」 | Ollama → llama.cpp → vLLM；各引擎的權重格式不同 |

## 延伸閱讀

- [AI Made Tools — vLLM vs Ollama vs llama.cpp vs TGI 2026](https://www.aimadetools.com/blog/vllm-vs-ollama-vs-llamacpp-vs-tgi/)
- [Morph — llama.cpp vs Ollama 2026](https://www.morphllm.com/comparisons/llama-cpp-vs-ollama)
- [n1n.ai — Comprehensive LLM Inference Engine Comparison](https://explore.n1n.ai/blog/llm-inference-engine-comparison-vllm-tgi-tensorrt-sglang-2026-03-13)
- [PremAI — 10 Best vLLM Alternatives 2026](https://blog.premai.io/10-best-vllm-alternatives-for-llm-inference-in-production-2026/)
- [TGI maintenance announcement](https://github.com/huggingface/text-generation-inference) —— 發行說明。
- [vLLM v0.15.1 release notes](https://github.com/vllm-project/vllm/releases)
