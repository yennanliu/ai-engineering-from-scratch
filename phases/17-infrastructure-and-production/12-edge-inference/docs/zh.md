# 邊緣推論 —— Apple Neural Engine、Qualcomm Hexagon、WebGPU/WebLLM、Jetson

> 邊緣的核心限制是記憶體頻寬，不是運算。行動裝置的 DRAM 落在 50-90 GB/s；資料中心的 HBM3 超過 2-3 TB/s —— 30-50 倍的落差。解碼是記憶體受限的，所以這個落差是決定性的。2026 年的版圖分成四路。Apple M4/A18 的 Neural Engine 峰值 38 TOPS，配統一記憶體（不用 CPU↔NPU 複製）。Qualcomm 的 Snapdragon X Elite／8 Gen 4 Hexagon 打到 45 TOPS。WebGPU + WebLLM 在 M3 Max 上跑 Llama 3.1 8B（Q4）約 41 tok/s（大約是原生的 70-80%）；1.76 萬 GitHub 星數、相容 OpenAI 的 API、約 70-75% 的行動覆蓋率。NVIDIA Jetson Orin Nano Super（8GB）裝得下 Llama 3.2 3B／Phi-3；AGX Orin 透過 vLLM 跑 gpt-oss-20b 約 40 tok/s；Jetson T4000（JetPack 7.1）是 AGX Orin 的 2 倍。TensorRT Edge-LLM 支援 EAGLE-3、NVFP4、分塊預填 —— 在 CES 2026 上由 Bosch、ThunderSoft、MediaTek 展示。

**類型：** 學習
**程式語言：** Python (stdlib, toy bandwidth-bound decode simulator)
**先修單元：** 階段 17 · 04（服務引擎內部）、階段 17 · 09（生產級量化）
**時間：** 約 60 分鐘

## 學習目標

- 解釋為何行動裝置上的 LLM 推論是記憶體頻寬受限的，而運算是次要的。
- 列舉那四個邊緣目標（Apple ANE、Qualcomm Hexagon、WebGPU/WebLLM、NVIDIA Jetson），並把每一個對到一種使用情境。
- 說出 2026 年 WebGPU 的覆蓋缺口（Firefox Android 正在追趕）與 Safari iOS 26 的落地。
- 替每個目標挑一種量化格式（ANE 用 Core ML 的 INT4 + FP16、Hexagon 用 QNN 的 INT8/INT4、瀏覽器用 WebGPU Q4、Jetson Thor 用 NVFP4）。

## 問題所在

一位客戶想要一個裝置端的聊天機器人：語音優先、預設私密、離線可用。在 MacBook Pro M3 Max 上，Llama 3.1 8B Q4 跑約 55 tok/s —— 沒問題。在 iPhone 16 Pro 上，同一個模型跑 3 tok/s —— 有問題。在配 Snapdragon 8 Gen 3 的中階 Android 上，7 tok/s。在 Chrome Android v121+ 透過 WebGPU 跑，依裝置 4-8 tok/s。

那個吞吐量的變異不是移植問題。它是「頻寬落差 × 量化格式 × NPU 是否從使用者空間存取得到」的乘積。2026 年的邊緣推論是四個不同的問題，配四種不同的解法。

## 核心概念

### 頻寬才是真正的天花板

解碼每產出一個詞元就要讀完整套權重。一個 Q4 的 7B 模型是 3.5 GB。以 50 GB/s 讀 3.5 GB 要 70 毫秒 —— 理論天花板約 14 tok/s。在 90 GB/s（高階行動 DRAM）下，天花板移到約 25 tok/s。低於這個數字時，再多運算也沒用。

資料中心的 HBM3 以 3 TB/s 讀同樣的 3.5 GB 只要 1.2 毫秒 —— 天花板是 830 tok/s。同一個模型、同樣的權重。不同的記憶體子系統。

### Apple Neural Engine（M4／A18）

- 最高 38 TOPS。統一記憶體（CPU 與 ANE 共用同一個池）—— 沒有複製開銷。
- 透過 Core ML 與編譯過的 `.mlmodel` 存取，或透過 PyTorch 用 Metal Performance Shaders（MPS）。
- Llama.cpp 的 Metal 後端用的是 MPS，不是直接用 ANE；原生 ANE 需要轉成 Core ML。
- 2026 年 iOS 應用最實際的路徑：Core ML 配 INT4 權重 + FP16 活化值。

### Qualcomm Hexagon（Snapdragon X Elite／8 Gen 4）

- 最高 45 TOPS。在 SoC 中與 CPU 及 GPU 整合，但記憶體域是分開的。
- QNN（Qualcomm Neural Network）SDK 與 AI Hub 提供從 PyTorch/ONNX 的轉換。
- 聊天樣板、Llama 3.2、Phi-3 都以一等產物的形式在 AI Hub 上出貨。

### Intel／AMD 的 NPU（Lunar Lake、Ryzen AI 300）

- 40-50 TOPS。軟體落後於 Apple／Qualcomm；OpenVINO 在進步，但仍屬小眾。
- 最適合 Windows ARM 的 copilot 應用；在 AMD／Intel 桌機上原生支援本地優先。

### WebGPU + WebLLM

- 透過 WebGPU 的計算著色器在瀏覽器裡跑模型；免安裝。
- Llama 3.1 8B Q4 在 M3 Max 上約 41 tok/s —— 透過同一後端大約是原生的 70-80%。
- WebLLM 有 1.76 萬 GitHub 星數；相容 OpenAI 的 JS API；Apache 2.0。
- 2026 年的覆蓋：Chrome Android v121+、Safari iOS 26 正式版、Firefox Android 仍在追趕。整體約 70-75% 的行動覆蓋率。

### NVIDIA Jetson 家族

- Orin Nano Super（8GB）：裝得下 Llama 3.2 3B、Phi-3，tok/s 不錯。
- AGX Orin：透過 vLLM 跑 gpt-oss-20b 約 40 tok/s。
- Thor／T4000（JetPack 7.1）：AGX Orin 的 2 倍效能，支援 EAGLE-3 與 NVFP4。
- TensorRT Edge-LLM（2026）支援 EAGLE-3 推測解碼、NVFP4 權重、分塊預填 —— 把資料中心的最佳化移植到邊緣。

### 逐目標的量化選擇

| 目標 | 格式 | 備註 |
|--------|--------|------|
| Apple ANE | INT4 權重 + FP16 活化值 | Core ML 的轉換路徑 |
| Qualcomm Hexagon | QNN INT8／INT4 | AI Hub 的轉換器 |
| WebGPU／WebLLM | Q4 MLC（q4f16_1） | 用 `mlc_llm convert_weight` + 編譯出的 `.wasm`；不支援 GGUF |
| Jetson Orin Nano | Q4 GGUF 或 TRT-LLM INT4 | 記憶體受限 |
| Jetson AGX／Thor | NVFP4 + FP8 KV | Edge-LLM 的路徑 |

### 邊緣上的長脈絡陷阱

Llama 3.1 的 128K 脈絡是一項資料中心的功能。在一支 8 GB RAM 的手機上，4 GB 模型 + 32K 詞元要用的 2 GB KV 快取 + 作業系統開銷 = 記憶體不足。邊緣部署會把脈絡壓在 4K-8K，除非能接受激進的 KV 量化（Q4 KV）。

### 語音才是那個殺手級應用

語音代理對延遲敏感（第一個詞元 < 500 毫秒）。本地推論完全消除網路延遲。把它跟語音轉文字（Whisper Turbo 的變體在邊緣跑得動）結合，邊緣推論就成了一條生產品質的語音迴圈。

### 你該記住的數字

- Apple M4／A18 的 ANE：38 TOPS。
- Qualcomm Hexagon SD X Elite：45 TOPS。
- WebLLM 在 M3 Max 上：Llama 3.1 8B Q4 約 41 tok/s。
- AGX Orin：透過 vLLM 跑 gpt-oss-20b 約 40 tok/s。
- 資料中心與邊緣的頻寬落差：30-50 倍。
- WebGPU 的行動覆蓋率：約 70-75%（Firefox Android 落後）。

## 框架應用

`code/main.py` 用頻寬受限的數學，跨各邊緣目標算出理論上的解碼吞吐量天花板。拿它跟觀察到的基準比較，並標出哪些地方是頻寬、而不是運算，才是瓶頸。

## 產出交付

這一課產出 `outputs/skill-edge-target-picker.md`。給定平台（iOS／Android／瀏覽器／Jetson）、模型與延遲／記憶體預算，挑出一種量化格式與轉換管線。

## 練習

1. 跑 `code/main.py`。對一個 Q4 的 7B 模型跑在 Snapdragon 8 Gen 3（約 77 GB/s 頻寬）上，算出解碼天花板。拿它跟觀察到的 6-8 tok/s 比較 —— 這個執行環境有效率嗎？
2. Android 上的 WebGPU 需要 Chrome v121+。替較舊的瀏覽器設計一條退路 —— 透過同一組相容 OpenAI 的 API 走伺服器端。
3. 你的 iOS 應用需要 4K 脈絡的串流。哪一種模型／格式組合能讓你在 iPhone 16 上把活躍記憶體壓在 4 GB 以下？
4. Jetson AGX Orin 跑 gpt-oss-20b 有 40 tok/s。Jetson Nano 只裝得下 3B。若你的產品同時瞄準兩者，你要怎麼把推論堆疊統一起來？
5. 論證「WebLLM 在 2026 年是否已生產就緒」。引用覆蓋率、效能與 Firefox Android 那個缺口。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| ANE | 「Apple 的神經引擎」 | M 系列與 A 系列中的裝置端 NPU；統一記憶體 |
| Hexagon | 「Qualcomm 的 NPU」 | Snapdragon 的 NPU；用 QNN SDK 存取 |
| WebGPU | 「瀏覽器的 GPU」 | W3C 標準化的瀏覽器 GPU API；2026 年 Chrome/Safari 支援 |
| WebLLM | 「瀏覽器的 LLM 執行環境」 | MLC-LLM 專案；Apache 2.0；相容 OpenAI 的 JS |
| Jetson | 「NVIDIA 的邊緣」 | Orin Nano／AGX／Thor／T4000 家族 |
| TRT Edge-LLM | 「邊緣版 TensorRT」 | 2026 年 TensorRT-LLM 的邊緣移植版；EAGLE-3 + NVFP4 |
| 統一記憶體 | 「共享池」 | CPU 與 NPU 看到同一份 RAM；沒有複製開銷 |
| 頻寬受限 | 「記憶體受限」 | 解碼被「每秒讀取權重的位元組數」卡住 |
| Core ML | 「Apple 的轉換」 | Apple 用來做 ANE 原生模型的框架 |
| QNN | 「Qualcomm 的堆疊」 | Qualcomm Neural Network SDK |

## 延伸閱讀

- [On-Device LLMs State of the Union 2026](https://v-chandra.github.io/on-device-llms/) —— 版圖與基準。
- [NVIDIA Jetson Edge AI](https://developer.nvidia.com/blog/getting-started-with-edge-ai-on-nvidia-jetson-llms-vlms-and-foundation-models-for-robotics/) —— Orin／AGX／Thor。
- [NVIDIA TensorRT Edge-LLM](https://developer.nvidia.com/blog/accelerating-llm-and-vlm-inference-for-automotive-and-robotics-with-nvidia-tensorrt-edge-llm/) —— 2026 年邊緣移植版的發布。
- [WebLLM (arXiv:2412.15803)](https://arxiv.org/html/2412.15803v2) —— 設計與基準。
- [Apple Core ML](https://developer.apple.com/documentation/coreml) —— ANE 原生的轉換。
- [Qualcomm AI Hub](https://aihub.qualcomm.com/) —— 給 Hexagon 用的預轉換模型。
