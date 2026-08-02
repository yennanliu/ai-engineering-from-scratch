# 分離式預填／解碼 —— NVIDIA Dynamo 與 llm-d

> 預填是運算受限的；解碼是記憶體受限的。把兩者跑在同一張 GPU 上，就會浪費掉其中一項資源。分離把它們拆到不同的池子上，並透過 NIXL（RDMA/InfiniBand，或退回 TCP）在兩者之間轉移 KV 快取。NVIDIA Dynamo（GTC 2025 發表、1.0 正式版）坐在 vLLM/SGLang/TRT-LLM 之上 —— 它的 Planner Profiler + SLA Planner 會自動把預填與解碼的比例調到匹配、以滿足 SLO。NVIDIA 公布的吞吐量增益大致在這個範圍 —— developer.nvidia.com（2025-06）顯示在中等延遲體制下，DeepSeek-R1 MoE 在 GB200 NVL72 + Dynamo 上約有 6 倍改善，而 Dynamo 的產品頁（developer.nvidia.com，未註明日期）宣傳 GB300 NVL72 + Dynamo 相對 Hopper 最高有 50 倍的 MoE 吞吐量。那個「30 倍」的數字，是社群對「完整 Blackwell + Dynamo + DeepSeek-R1」各種回報的彙總；我們找不到任何一份第一手來源精確地寫出 30 倍，所以請把它當成方向性的宣稱。llm-d（Red Hat + AWS）是 Kubernetes 原生的：預填／解碼／路由器各是獨立的 Service，各有逐角色的 HPA。llm-d 0.5 加上階層式 KV 卸載、知快取的 LoRA 路由、UCCL 網路、縮到零。經濟性：把多家客戶揭露的資料在內部彙整起來顯示，在 SLA 不變的前提下，從共置服務換到配 Dynamo 的分離式，可以在 200 萬美元等級的推論支出上省下 30–40%（也就是每年 60-80 萬美元）；那個「200 萬 → 60-80 萬」的具體數字是一份內部合成值，不是單一份已發表的案例研究 —— 把它當成數量級的錨點，不是可引用的參考。短提示詞（<512 詞元、短輸出）撐不起那筆轉移成本。

**類型：** 學習
**程式語言：** Python (stdlib, toy disaggregated-vs-colocated simulator)
**先修單元：** 階段 17 · 04（服務引擎內部）、階段 17 · 08（推論指標）
**時間：** 約 75 分鐘

## 學習目標

- 解釋為何預填與解碼有不同的最佳 GPU 配置，並把共置之下的浪費量化。
- 畫出分離式架構：預填池、解碼池、透過 NIXL 的 KV 轉移、路由器。
- 說出分離「划不來」的條件（短提示詞、短輸出）。
- 分辨 NVIDIA Dynamo（疊在堆疊之上）與 llm-d（Kubernetes 原生），並把每一個對到一種運維情境。

## 問題所在

你在 8 張 H100 上跑 Llama 3.3 70B。在混合工作負載下（長提示詞 + 短輸出），GPU 在解碼期間閒著，因為大多數運算都花在預填上。在另一種工作負載下（短提示詞 + 長輸出），情況相反。共置的預填 + 解碼，就代表兩邊你都過度配置。

預算影響：20-40% 的 GPU 時間浪費在錯的資源上。你買 H100 的運算力去跑記憶體受限的解碼，或買 H100 的 HBM 頻寬去跑運算受限的預填。兩種都是昂貴的浪費。

分離把預填與解碼拆到各自依其瓶頸調整大小的池子上。KV 快取透過高頻寬互連從預填池轉移到解碼池。

## 核心概念

### 為什麼瓶頸不同

**預填** —— 在一次前向裡對完整輸入提示詞跑過 transformer。矩陣乘法主導；運算受限。H100 FP8 提供約 2000 TFLOPS 的有效吞吐量。批次效率不錯 —— 一次前向處理很多詞元。

**解碼** —— 一次產生一個詞元，每次迭代都要讀完整權重。記憶體頻寬受限。HBM3 提供約 3 TB/s。只有在高併發時批次效率才好 —— 讀權重的成本會攤到整個批次上。

把兩者共置：你買的是對兩者都好的 GPU。H100 兩者都行，但不管你跑哪個都一樣貴。在規模上，你會想要預填池用 H100／偏重運算；解碼池用 H200／偏重記憶體，或搭配激進的量化。

### 那個架構

```
            ┌──────────────┐
  Request → │    Router    │ ───────────────────────┐
            └──────┬───────┘                        │
                   │                                │
                   ▼ (prompt only)                  │
            ┌──────────────┐    KV cache    ┌───────▼──────┐
            │ Prefill pool │ ─── NIXL ────► │ Decode pool  │
            │  (compute)   │                │  (memory)    │
            └──────────────┘                └──────┬───────┘
                                                   │ tokens
                                                   ▼
                                                 Client
```

NIXL 是 NVIDIA 的跨節點傳輸。有 RDMA/InfiniBand 就用，沒有就退回 TCP。轉移延遲是真的 —— 對 70B FP8 上一個 4K 詞元提示詞的 KV 快取，通常是 20-80 毫秒。這就是為什麼短提示詞撐不起分離：那筆轉移稅超過了節省。

### Dynamo 對上 llm-d

**NVIDIA Dynamo**（GTC 2025 發表、1.0 正式版）：
- 以編排者的身分坐在 vLLM、SGLang、TRT-LLM 之上。
- Planner Profiler 量測工作負載，SLA Planner 自動設定預填與解碼的比例。
- Rust 核心、Python 可擴充。
- 吞吐量增益：NVIDIA 回報在中等延遲體制下，DeepSeek-R1 MoE 在 GB200 NVL72 + Dynamo 上有 6 倍（developer.nvidia.com，2025-06）；社群對完整 Blackwell + Dynamo + DeepSeek-R1 堆疊「最高 30 倍」的回報缺乏單一第一手來源，應視為方向性數字。
- GB300 NVL72 + Dynamo：依 Dynamo 產品頁（developer.nvidia.com，未註明日期），相對 Hopper 最高 50 倍的 MoE 吞吐量。

**llm-d**（Red Hat + AWS，Kubernetes 原生）：
- 預填／解碼／路由器各是獨立的 Kubernetes Service。
- 逐角色的 HPA，訊號用佇列深度（預填）／KV 使用率（解碼）。
- `topologyConstraint packDomain: rack` 把預填與解碼的小團打包到同一個機架上，以取得高頻寬的 KV 轉移。
- llm-d 0.5（2026）：階層式 KV 卸載、知快取的 LoRA 路由、UCCL 網路、縮到零。

若你想要一個託管的、疊在堆疊之上的編排者，就用 Dynamo。若你想要 Kubernetes 原生的原語、而且已押注 CNCF 生態系，就用 llm-d。

### 經濟性

內部合成值（不是單一份已發表的案例研究 —— 數量級的錨點）：

- 每年 200 萬美元的推論支出，跑在共置服務上。
- 換成配 Dynamo 的分離式。
- 同樣的請求量、同樣的 P99 延遲 SLA。
- 回報的節省：每年 60–80 萬美元（降低 30–40%）。
- 沒有買新硬體。

我們是從多家客戶的揭露資料綜合出這個數字，而不是來自單一份可引用的案例研究；最接近的已發表資料點是 Baseten 在 2025-10 的「用 Dynamo 的 KV 路由讓 TTFT 快 2 倍、吞吐量高 61%」（baseten.co），以及 VAST + CoreWeave 在 2025-12 預估「在 40–60% KV 命中率下每美元多 60–130% 詞元」（vastdata.com）。那些節省來自替每個池子調到合適的尺寸；預填吃重的工作負載（帶 8K 以上前綴的 RAG）獲益比平衡型的更多。

### 什麼時候「不要」分離

- 提示詞 < 512 詞元且輸出 < 200 詞元：轉移稅主導了收穫。
- 小叢集（< 4 張 GPU）：池子的多樣性不夠。
- 團隊沒辦法帶著逐角色擴縮去營運兩個 GPU 池：Dynamo 有幫助，但不是不費力。
- 沒有 RDMA 網路：TCP 的轉移稅更重。

### 那個路由器與階段 17 · 11 整合

分離式的路由器是知 KV 快取的（階段 17 · 11）。一個請求落到持有它前綴的解碼池上 —— 若沒有相符，就走預填 → 解碼。命中率與分離會相乘 —— 那個知快取的路由器決定了「到底需不需要一次新的預填」。

### Blackwell 上的 MoE 才是真正數字所在

GB300 NVL72 + Dynamo 顯示相對 Hopper 基線有 50 倍的 MoE 吞吐量。MoE 的專家路由在預填時偏重運算、在解碼時偏重記憶體（專家快取），所以分離是雙重斬獲。2026 年前沿模型的服務是 MoE 主導的（DeepSeek-V3、未來的 GPT-5 變體）。

### 你該記住的數字

基準數字會漂移 —— NVIDIA 與整個推論堆疊每季都會發布更新結果。引用前先重新確認。

- DeepSeek-R1 在 GB200 NVL72 + Dynamo 上：在中等延遲體制下相對基線約 6 倍吞吐量（developer.nvidia.com，2025-06）；社群對完整 Blackwell + Dynamo 堆疊「最高 30 倍」的宣稱是沒有單一第一手來源的方向性彙總。
- GB300 NVL72 + Dynamo：相對 Hopper 最高 50 倍的 MoE 吞吐量（developer.nvidia.com，未註明日期）。
- 節省的錨點（內部合成值，不是單一案例研究）：在 SLA 不變下，從 200 萬美元的年度支出省下 60-80 萬美元。
- 分離的門檻：提示詞 >512 詞元 + 輸出 >200 詞元。
- 透過 NIXL 的 KV 轉移：70B FP8 上 4K 提示詞的 KV 要 20-80 毫秒。

## 框架應用

`code/main.py` 模擬共置與分離式服務。回報吞吐量、每請求成本，以及提示詞長度的交叉點。

## 產出交付

這一課產出 `outputs/skill-disaggregation-decider.md`。給定工作負載與叢集，判斷要不要分離。

## 練習

1. 跑 `code/main.py`。提示詞要多長，分離才會勝過共置？
2. 替一個 P99 前綴長度 8K、輸出 300 的 RAG 服務，設計預填池與解碼池。
3. Dynamo 對上 llm-d：替一家純 Kubernetes、對 Python 執行環境沒有偏好的公司挑一個。
4. 算 KV 轉移成本：70B FP8 上 4K 的預填約 500 MB KV。在 RDMA 100 GB/s 下轉移要 5 毫秒。在 TCP 10 GB/s 下要 50 毫秒。哪一個對你的 SLA 要緊？
5. MoE 的專家路由會改變 KV 的存取樣式。當 MoE 對每個詞元啟動不同專家時，分離的行為會怎樣？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| 分離式服務 | 「預填／解碼分開」 | 每個階段各有獨立的 GPU 池 |
| NIXL | 「NVIDIA 的傳輸」 | Dynamo 的跨節點 KV 轉移（RDMA/TCP） |
| NVIDIA Dynamo | 「那個編排者」 | 疊在 vLLM/SGLang/TRT-LLM 之上的協調者 |
| llm-d | 「Kubernetes 原生」 | Red Hat + AWS 的 K8s 分離式堆疊 |
| Planner Profiler | 「Dynamo 的自動設定」 | 量測工作負載、設定池子比例 |
| SLA Planner | 「Dynamo 的政策」 | 自動把預填與解碼的比例調到匹配以滿足 SLO |
| `packDomain: rack` | 「llm-d 的拓撲」 | 把預填與解碼打包在同一機架上以取得快速 KV |
| UCCL | 「統一的集合通訊」 | llm-d 0.5 供縮到零使用的網路層 |
| MoE 專家路由 | 「逐詞元選專家」 | DeepSeek-V3 的模式；分離對它有幫助 |

## 延伸閱讀

- [NVIDIA — Introducing Dynamo](https://developer.nvidia.com/blog/introducing-nvidia-dynamo-a-low-latency-distributed-inference-framework-for-scaling-reasoning-ai-models/)
- [NVIDIA — Disaggregated LLM Inference on Kubernetes](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/)
- [TensorRT-LLM Disaggregated Serving blog](https://nvidia.github.io/TensorRT-LLM/blogs/tech_blog/blog5_Disaggregated_Serving_in_TensorRT-LLM.html)
- [llm-d GitHub](https://github.com/llm-d/llm-d)
- [llm-d 0.5 release notes](https://github.com/llm-d/llm-d/releases)
