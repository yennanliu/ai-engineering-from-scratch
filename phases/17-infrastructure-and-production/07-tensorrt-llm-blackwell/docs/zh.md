# 硬體特化的推論編譯 —— Blackwell 上的 FP8 與 NVFP4

> 硬體特化的推論編譯，是拿可攜性換吞吐量，而 TensorRT-LLM —— 只支援 NVIDIA、為 Blackwell 調校 —— 就是那筆交易划算的最清楚例子。在配 Dynamo 編排的 GB200 NVL72 上，SemiAnalysis 的 InferenceX 在 2026 年第一到第二季，對一個 120B 模型量到每百萬詞元 0.012 美元，而 H100 + vLLM 是每百萬 0.09 美元 —— 7 倍的經濟落差。這個堆疊是三種浮點體制的複利：FP8 對 KV 快取與注意力核心仍然關鍵，因為它有那些地方需要的動態範圍；NVFP4（4 位元微縮放）負責權重與活化值；多詞元預測（MTP）與分離式預填／解碼再往上疊 2-3 倍。Day-0 的模型支援可直接載入 FP4 權重，不需要訓練後轉換。2026 年工程團隊的陷阱是：TRT-LLM 雖然開源，卻是 NVIDIA 專屬的 —— 對 CUDA 與 Blackwell 特化 —— 所以採用它就是拿可攜性換吞吐量。在下決定之前，先針對你自己的模型與硬體組合把帳算清楚。

**類型：** 學習
**程式語言：** Python (stdlib, toy FP8/NVFP4 memory and cost calculator)
**先修單元：** 階段 17 · 04（服務引擎內部）、階段 10 · 13（量化）
**時間：** 約 75 分鐘

## 學習目標

- 解釋為何就算權重已經是 NVFP4，FP8 對 KV 快取與注意力仍然關鍵。
- 算出一個前沿模型在 BF16、FP8 與 NVFP4 之下的 HBM 佔用，並推敲那些節省從哪裡來。
- 說出 TRT-LLM 所利用的 Blackwell 專屬特性（day-0 FP4、MTP、分離式服務、all-to-all 原語）。
- 判斷 TRT-LLM 的 NVIDIA 鎖定，何時值得換那個相對於 Hopper 上 vLLM 的 7 倍成本落差。

## 問題所在

2026 年推論經濟學的前沿是「一塊錢能買多少詞元」。答案取決於四層疊起來的選擇：硬體世代（Hopper H100/H200 對 Blackwell B200/GB200）、精度（BF16 → FP8 → NVFP4）、服務引擎（vLLM 對 SGLang 對 TRT-LLM），以及編排（純跑對分離式對 Dynamo）。

在 Hopper 上配 vLLM，一個 120B 的 MoE 跑起來約每百萬詞元 0.09 美元。在 Blackwell 上配 TRT-LLM + Dynamo，同一個模型約 0.012 美元 —— 便宜 7 倍。那個落差有一部分來自硬體（Blackwell 的單卡 LLM 吞吐量是 Hopper 的 11-15 倍）。有一部分來自堆疊：FP4 權重、MTP 草稿、分離式預填／解碼，以及供 MoE 專家通訊用的 NVLink 5 all-to-all。

你在 NVIDIA 的堆疊之外複製不了這件事。那就是那筆取捨 —— 拿可攜性換經濟性。理解哪一項堆疊選擇貢獻了落差中的哪一份，正是這一課的重點。

## 核心概念

### 為什麼 FP8 仍是 KV 快取的地板

2026 年一個常見的錯誤：以為 NVFP4 到處都適用。並不是。KV 快取需要 FP8（8 位元浮點），因為它存的是動態範圍很寬的注意力鍵與值。把 KV 量化到 FP4 會造成災難性的準確度損失 —— 分布的尾巴掉光，注意力分數就崩了。FP8 的指數位元給了 KV 快取所需的範圍。

NVFP4（2025-2026）適用於權重與活化值。微縮放：每一小塊權重有自己的縮放因子，所以小塊可以橫跨不同的動態範圍，而不必承受逐張量縮放的損失。對活化值來說，FP4 撐得住，因為活化值在一層之內的範圍很小。

典型的 Blackwell 設定：

- 權重：NVFP4（4 位元微縮放）。
- 活化值：NVFP4。
- KV 快取：FP8。
- 注意力累加器：FP32（softmax 穩定性）。

### TRT-LLM 使用的那些 Blackwell 專屬原語

- **Day-0 FP4 權重**：模型供應商直接出貨 FP4 權重；TRT-LLM 不需訓練後轉換就能載入。FP4 不必走 AWQ／GPTQ 那一步。
- **多詞元預測（MTP）**：跟 EAGLE（階段 17 · 05）同一個構想，但整合進 TRT-LLM 的建置裡。
- **分離式服務**：預填與解碼分別跑在不同的 GPU 池上，KV 快取透過 NVLink 或 InfiniBand 轉移。跟 Dynamo（階段 17 · 20）同一個構想。
- **All-to-all 通訊原語**：NVLink 5 把 MoE 的專家通訊延遲相對 Hopper 砍掉 3 倍。TRT-LLM 的 MoE 核心就是為此調校的。
- **NVFP4 + MXFP8 微縮放**：在 Blackwell 的 Tensor Core 上以硬體加速處理縮放因子。

### 你該背下來的數字

- HGX B200 在 GPT-OSS-120B 上透過 TRT-LLM 是每百萬詞元 0.02 美元。
- GB200 NVL72 透過 Dynamo（編排 TRT-LLM）是每百萬詞元 0.012 美元。
- H100 + vLLM 在可比工作負載上約每百萬詞元 0.09 美元。
- TRT-LLM 三個月的更新帶來 2.8 倍吞吐量增益（2026）。
- 單卡 LLM 吞吐量，Blackwell 對 Hopper 是 11-15 倍。
- MLPerf Inference v6.0（2026 年 4 月）：Blackwell 在每一項提交任務上都主導。

### FP4 在品質上實際付出什麼

NVFP4 很激進。在推理吃重的工作負載上（思維鏈、數學、長脈絡的程式碼生成），FP4 權重會有可見的退化。逐區塊校準能緩解，但消除不了。出貨推理型模型的團隊常用 FP8 權重 + FP4 活化值當折衷，或乾脆留在 H200 上全程用 FP8。

規則是：在決定採用 NVFP4 權重之前，永遠先在你自己的評測集上驗證任務品質。

### 為什麼這是一項 NVIDIA 鎖定的決策

TRT-LLM 是 C++ + CUDA + 閉源核心。模型必須為特定的 GPU SKU 編譯。沒有 AMD、沒有 Intel、沒有 ARM。若你的基礎設施策略是多廠商，那 TRT-LLM 對「由 TRT-LLM 服務的那一層」就是不可行的 —— 你仍然可以在混合硬體上用 vLLM 服務。若你是純 NVIDIA，那 7 倍落差就付得起那份鎖定。

### 2026 年的實務配方

對一份年度推論帳單超過 1 億美元的規模，跑在 Hopper + vLLM 上等於白白留下 7-10 倍在桌上。把成本主導的工作負載遷到 Blackwell + TRT-LLM + Dynamo。實驗層留在 H100 + vLLM，換取模型迭代速度。每一個轉成 NVFP4 的模型，在上生產前都要驗證品質。

### 分離帶來的紅利

TRT-LLM 的分離式服務（預填與解碼分池）在階段 17 · 20 有深入涵蓋。在 Blackwell 上，倍數會疊起來：FP4 權重 × MTP 加速 × 分離式放置 × 知快取的路由。那個 7 倍的數字假設的就是這一整套堆疊。

```figure
pipeline-parallel
```

## 框架應用

`code/main.py` 替一個模型計算 HBM 佔用、解碼吞吐量（記憶體受限體制），以及跨三種堆疊的每百萬詞元金額：H100 + BF16 + vLLM、H100 + FP8 + vLLM、B200 + NVFP4/FP8 + TRT-LLM。跑它，看那個複利效應，以及每一項改變各貢獻了落差中的多少。

## 產出交付

這一課產出 `outputs/skill-trtllm-blackwell-advisor.md`。給定工作負載、模型大小與年度詞元量，它會判斷 Blackwell + TRT-LLM 這套堆疊值不值得那份 NVIDIA 鎖定。

## 練習

1. 跑 `code/main.py`。對一個 30% 參數活躍的 120B MoE，算出在 H100 BF16、H100 FP8 與 B200 NVFP4/FP8 上受記憶體頻寬限制的解碼吞吐量。最大的躍升來自哪裡？
2. 一位客戶每年在 H100 + vLLM 上花 200 萬美元。給定那 7 倍的經濟落差，他們要買幾張 Blackwell GPU，才能在 12 個月內攤平遷到 TRT-LLM 的成本？
3. 你看到在 NVFP4 權重轉換後，MATH 的準確率掉了 3 分。說出兩條救援路徑：一條品質優先（維持 FP8 權重）、一條成本優先（用領域內資料做校準）。
4. 讀 MLPerf v6.0 的推論結果。哪一項任務上 Blackwell 相對 Hopper 的落差最小，為什麼？
5. 算出一個 405B 模型在 NVFP4 權重 + FP8 KV 快取、128k 脈絡下所需的 HBM。它裝得進單一個 GB200 NVL72 節點嗎？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| FP8 | 「八位元浮點」 | 8 位元浮點；因動態範圍需求而用於 KV 快取與注意力 |
| NVFP4 | 「四位元微縮放」 | NVIDIA 的 4 位元微縮放 FP 格式；Blackwell 上的權重與活化值 |
| MXFP8 | 「MX 八位元」 | 微縮放的 FP8 變體；在 Blackwell Tensor Core 上有硬體加速 |
| Day-0 FP4 | 「直接出貨 FP4 權重」 | 模型供應商釋出時權重就已是 FP4；不需訓練後轉換那一步 |
| MTP | 「多詞元預測」 | TRT-LLM 內建整合的推測解碼草稿（階段 17 · 05） |
| 分離式服務 | 「預填／解碼分開」 | 預填與解碼分在不同 GPU 池；KV 透過 NVLink/IB 轉移 |
| All-to-all | 「MoE 的專家通訊」 | 把詞元路由到專家 GPU 的通訊樣式；NVLink 5 砍掉 3 倍 |
| InferenceX | 「SemiAnalysis 的推論基準」 | 2026 年被業界接受的每詞元成本基準 |

## 延伸閱讀

- [NVIDIA — Blackwell Ultra MLPerf Inference v6.0](https://developer.nvidia.com/blog/nvidia-blackwell-ultra-sets-new-inference-records-in-mlperf-debut/) —— 2026 年 4 月的 MLPerf 結果。
- [NVIDIA — MoE Inference on Blackwell](https://developer.nvidia.com/blog/delivering-massive-performance-leaps-for-mixture-of-experts-inference-on-nvidia-blackwell/) —— NVLink 5 的 all-to-all 與 MoE 核心。
- [TensorRT-LLM Overview](https://nvidia.github.io/TensorRT-LLM/overview.html) —— 官方引擎文件。
- [NVIDIA — Introducing Dynamo](https://developer.nvidia.com/blog/introducing-nvidia-dynamo-a-low-latency-distributed-inference-framework-for-scaling-reasoning-ai-models/) —— TRT-LLM 之上的分離式編排。
- [MLPerf Inference](https://mlcommons.org/benchmarks/inference-datacenter/) —— 發表 Blackwell 數字的那套基準。
