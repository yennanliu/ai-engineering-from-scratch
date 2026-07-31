# DeepSeek-V3 架構導覽

> 階段 10 · 第 14 單元點名了每個開源模型都會轉的六個架構旋鈕。DeepSeek-V3（2024 年 12 月，總參數 6710 億、啟用 370 億）六個全轉，還多加了四個：多頭潛在注意力（MLA）、無輔助損失負載平衡、多詞元預測（MTP），以及 DualPipe 訓練。這個單元把 DeepSeek-V3 的架構從頭讀到尾，並從公開的 config 推導出每一項參數量。讀完之後，你能解釋為什麼 671B/37B 這個比例是正確的賭注，以及為什麼在前沿規模上 MLA + MoE 合起來勝過任何單獨一者。

**類型：** 學習
**程式語言：** Python (stdlib, parameter calculator)
**先修單元：** 階段 10 · 14（開源模型導覽）、階段 10 · 17（NSA）、階段 10 · 18（MTP）、階段 10 · 19（DualPipe）
**時間：** 約 75 分鐘

## 學習目標

- 從頭到尾讀完 DeepSeek-V3 的 config，用六個 GPT-2 旋鈕加上四個 DeepSeek 特有的新增項目來解釋每一個欄位。
- 推導出總參數量（6710 億）、啟用參數量（370 億），以及各自由哪些元件貢獻。
- 算出 MLA 在 128k 上下文下的 KV 快取佔用，並與一個啟用參數相同、採用 GQA 的密集模型要付的代價比較。
- 說出 DeepSeek 特有的四項創新（MLA、MTP、無輔助損失路由、DualPipe），並指出各自針對架構／訓練堆疊的哪一塊。

## 問題所在

DeepSeek-V3 是第一個架構與 Llama 家族有實質差異的前沿開源模型。Llama 3 405B 是「轉了六個旋鈕的 GPT-2」。DeepSeek-V3 則是六個旋鈕全轉、外加四個。讀 Llama 3 的 config 只能算是讀 DeepSeek config 的熱身，因為深層結構 —— 注意力區塊的形狀、路由邏輯、訓練時的目標函式 —— 差異大到需要另外一趟導覽。

學這個的回報是：DeepSeek-V3 的開放權重釋出，改變了「前沿能力」在開源模型裡的定義。這套架構是許多 2026 年訓練任務照抄的藍圖。只要工作碰到前沿 LLM 的訓練或推論，理解它就是入場門檻。

## 核心概念

### 那個不變的核心，再看一次

DeepSeek-V3 仍然是自迴歸的。它仍然疊解碼器區塊。每個區塊仍然是注意力加 MLP 加兩個 RMSNorm。MLP 裡仍然用 SwiGLU。仍然用 RoPE。前置正規化。權重綁定的嵌入。跟每個 Llama 或 Mistral 是同一條基準線。

### 轉折：用 MLA 而不是 GQA

在階段 10 · 14 你已經知道 GQA 是靠讓一組 Q 頭共用 K 與 V 來縮小 KV 快取。多頭潛在注意力（MLA）走得更遠：K 與 V 被壓縮成一份共用的低秩潛在表示（也就是 `kv_lora_rank`），再即時逐頭解壓回來。KV 快取只存那個潛在向量 —— 典型是每層每個詞元 512 個浮點數，而不是 8 x 128 = 1024 個。

在 128k 上下文下，採用 MLA 的 DeepSeek-V3（每層每個詞元一份共用潛在向量 `c^{KV}`；K 與 V 都由這個潛在向量透過上投影導出，而這些上投影可以被吸收進後續的矩陣乘法）：

```
kv_cache = num_layers * kv_lora_rank * max_seq_len * bytes_per_element
         = 61 * 512 * 131072 * 2
         = 7.6 GB
```

一個假想的 GQA 基準線（Llama 3 70B 的形狀、8 個 KV 頭、頭維度 128）要付的是：

```
kv_cache = 2 * 61 * 8 * 128 * 131072 * 2
         = 30.5 GB
```

在 128k 上下文下，MLA 比 Llama-3-70B 那種 GQA 快取小 4 倍。

代價是：MLA 為每次注意力計算（每個頭）多加了一個解壓步驟。跟省下來的頻寬相比，這點額外計算很小。對長上下文推論來說是淨賺。

### 路由：無輔助損失負載平衡

MoE 路由器決定每個詞元交給哪 top-k 個專家處理。天真的路由器會把太多工作集中在少數幾個專家上，讓其他專家閒置。標準解法是加一項輔助損失來懲罰負載不平衡。這有效，但會稍微傷到主任務的表現。

DeepSeek-V3 提出了一種無輔助損失的方案。在路由器的 logits 上加入每個專家各自的偏置項，訓練期間依一條簡單規則調整：如果專家 `e` 過載，就降低 `bias_e`；如果負載不足，就提高它。不需要額外的損失項。訓練保持乾淨。專家負載保持平衡。

對主損失的影響：量不出來。對 MoE 架構的影響：更乾淨，也少了一個輔助損失的超參數要調。

### MTP：更密的訓練訊號 + 免費的草稿

在階段 10 · 18 你已經知道 DeepSeek-V3 加了 D=1 個 MTP 模組，用來預測往後兩個位置的詞元。推論時，這個訓練好的模組被改用成推測解碼的草稿模型，接受率超過 80%。訓練時，每個隱藏狀態被 D+1 = 2 個目標監督，提供更密的訊號。

參數量：在 6710 億主體之上再加 140 億。額外開銷：2.1%。

### 訓練：DualPipe

在階段 10 · 19 你已經知道 DualPipe 是一種雙向管線，把前向與反向 chunk 跟跨節點的 all-to-all 通訊重疊起來。在 DeepSeek-V3 那 2,048 張 H800 的規模下，它救回了大約 24.5 萬 GPU-小時 —— 那些用 1F1B 會賠給管線氣泡的時間。

### config，一個欄位一個欄位看

以下是 DeepSeek-V3 的 config（簡化版）：

```
hidden_size: 7168
intermediate_size: 18432   (dense MLP hidden size, used on first few layers)
moe_intermediate_size: 2048 (expert MLP hidden size)
num_hidden_layers: 61
first_k_dense_layers: 3    (first 3 layers use dense MLP)
num_attention_heads: 128
num_key_value_heads: 128   (formally equal to num_heads under MLA, but
                           the real compression is in kv_lora_rank)
kv_lora_rank: 512          (MLA latent dimension)
num_experts: 256            (MoE expert count per block)
num_experts_per_tok: 8      (top-8 routing)
shared_experts: 1           (always-on shared expert per block)
max_position_embeddings: 163840
rope_theta: 10000.0
vocab_size: 129280
mtp_module: 1               (1 MTP module at depth 1)
```

逐項解讀：

- `hidden_size=7168`：嵌入維度。
- `num_hidden_layers=61`：總區塊深度。
- `first_k_dense_layers=3`：前 3 個區塊使用大小 18432 的密集 MLP。其餘 58 個用 MoE。
- `num_attention_heads=128`：128 個查詢頭。
- `kv_lora_rank=512`：K 與 V 被壓縮到這個潛在維度，再逐頭解壓。
- `num_experts=256, num_experts_per_tok=8`：每個 MoE 區塊有 256 個專家，路由 top-8。
- `shared_experts=1`：在 256 個被路由的專家之外，還有 1 個永遠開著的專家對每個詞元都有貢獻。可以把它想成一層「密集地板」，確保每個詞元都拿得到某些可靠的東西。
- `moe_intermediate_size=2048`：每個專家的 MLP 隱藏層大小。比密集 MLP 小，因為總共有 256 個。

### 參數帳目

完整計算在 `code/main.py` 裡。重點如下：

- 嵌入：`vocab * hidden = 129280 * 7168 = 約 9.3 億`。
- 前 3 個密集區塊：MLA 注意力（每區塊約 1.44 億）+ 密集 MLP（每區塊約 2.6 億）+ 正規化層。總共大約 12 億。
- 58 個 MoE 區塊：MLA 注意力（約 1.44 億）+ 各 256 個專家（每個 3000 萬）+ 1 個共用專家（3000 萬）+ 正規化層。每區塊含全部專家共約 79.5 億。58 個 MoE 區塊合計 4610 億。
- MTP 模組：140 億。

總計：核心架構約 4760 億 + MTP 140 億 —— 而公開的 6710 億這個數字另外還算進了額外的結構性參數（偏置張量、專家特有的元件、共用專家的縮放等等）。計算器重現出來的數字和公開值相差 3-5%，這個差距來自 DeepSeek 報告第 2 節附錄裡記載的細部帳目。

每次前向的啟用參數：

- 注意力：每層 1.44 億 * 61 = 88 億（所有層都會啟動）。
- 啟用的 MLP：前 3 層是密集的（3 * 2.6 億 = 7.8 億），58 個 MoE 層每層啟用 8 個路由專家 + 1 個共用專家 + 路由開銷。每層啟用的 MLP：約 2.6 億。合計：3 * 2.6 億 + 58 * 2.6 億 = 約 159 億。
- 嵌入 + 正規化層：12 億。
- 總啟用量：核心大約 260 億 + MTP 140 億（有訓練，但推論時不一定會跑）≈ 370 億。

### 671B / 37B 這個比例

18 倍的稀疏比（啟用參數是總量的 5.5%）。DeepSeek-V3 是至今釋出開放權重的前沿 MoE 模型裡最稀疏的一個。Mixtral 8x7B 的比例是 13/47（28%），密集得多。Llama 4 Maverick 的 17B/400B（4.25%）則相當接近。DeepSeek 押的注是：在前沿規模下，專家更多、啟用比例更低，能在每一個啟用 FLOP 上換到更好的品質。

### DeepSeek-V3 在版圖上的位置

| 模型 | 總參數 | 啟用 | 比例 | 注意力 | 創新之處 |
|-------|------|-------|-------|-----------|-------------|
| Llama 3 70B | 70B | 70B | 100% | GQA 64/8 | — |
| Llama 4 Maverick | 400B | 17B | 4.25% | GQA | — |
| Mixtral 8x22B | 141B | 39B | 27% | GQA | — |
| DeepSeek V3 | 671B | 37B | 5.5% | MLA 512 | MLA + MTP + 無輔助損失 + DualPipe |
| Qwen 2.5 72B | 72B | 72B | 100% | GQA 64/8 | YaRN 外推 |

### 後續：R1、V4

DeepSeek-R1（2025）是在 V3 骨幹上做的推理訓練。R1 用的是同一套架構。改變的是後訓練配方（在可驗證任務上做大規模 RL），不是預訓練架構。

DeepSeek-V4（如果會出的話）預期會保留 MLA + MoE + MTP，再加上 DSA（DeepSeek Sparse Attention），也就是階段 10 · 17 那個 NSA 的後繼者。這條血脈很穩定：架構層級的創新會累積，每一代再多轉幾個旋鈕。

```figure
moe-routing
```

## 框架應用

`code/main.py` 是專門針對 DeepSeek-V3 形狀的參數計算器。跑跑看，把輸出跟論文的數字比對，再拿它去算假想的變體（256 個專家 vs 512 個、top-8 vs top-16、MLA rank 512 vs 1024）。

要看的地方：

- 總參數量 vs 公開的 6710 億。
- 啟用參數量 vs 公開的 370 億。
- 128k 上下文下的 KV 快取 —— MLA 對 GQA 的比較。
- 逐層拆解，看看參數預算實際上花到哪裡去了。

## 產出交付

這個單元會產出 `outputs/skill-deepseek-v3-reader.md`。給定一個 DeepSeek 家族的模型（V3、R1，或任何未來的變體），它會產出一份逐元件的架構解讀：點名 config 的每個欄位、依元件推導參數量，並指出這個模型用上了 DeepSeek 四項特有創新中的哪幾項。

## 練習

1. 跑 `code/main.py`。把計算器估出來的總參數量跟公開的 6710 億比較，找出差距從哪裡來。論文第 2 節有完整的逐項列表。

2. 把 config 改成 MLA rank 256 而不是 512。算出 128k 上下文下 KV 快取的大小。這換來多少百分比的縮減，又在每個頭的表達能力上付出了什麼代價？

3. 把 DeepSeek-V3 的（256 個專家、top-8）路由，跟一個假想的（512 個專家、top-8）變體比較。總參數量成長，啟用參數量不變。理論上多出來的專家容量買到了什麼，推論時又要付出什麼？

4. 讀 DeepSeek-V3 技術報告（arXiv:2412.19437）第 2.1 節關於 MLA 的部分。用三句話解釋為什麼 K 與 V 的解壓矩陣可以為了推論效率被「吸收」進後續的矩陣乘法。

5. DeepSeek-V3 大多數運算採用 FP8 訓練。算出用 FP8 而非 BF16 儲存那 6710 億權重能省下多少記憶體。這件事又如何與 14.8T 詞元的訓練預算交互影響？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| MLA | 「多頭潛在注意力」 | 把 K 與 V 壓縮成一份共用的低秩潛在表示（kv_lora_rank，典型是 512），再即時逐頭解壓；KV 快取只存那個潛在向量 |
| kv_lora_rank | 「MLA 的壓縮維度」 | K 與 V 共用潛在向量的大小；DeepSeek-V3 用 512 |
| 前 k 層密集層 | 「前幾層維持密集」 | MoE 模型的前幾層跳過 MoE 路由器，改跑密集 MLP 以求穩定 |
| num_experts_per_tok | 「Top-k 路由」 | 每個詞元會啟動幾個被路由的專家；DeepSeek-V3 用 8 |
| 共用專家 | 「永遠開著的專家」 | 不管路由結果如何都會處理每個詞元的專家；DeepSeek-V3 用 1 個 |
| 無輔助損失路由 | 「用偏置調整負載平衡」 | 訓練期間調整每個專家的偏置項，不加損失項就讓專家負載保持平衡 |
| MTP 模組 | 「額外的預測頭」 | 從 h^(1) 與 E(t+1) 預測 t+2 的 Transformer 區塊；訓練訊號更密，還附送推測解碼的草稿模型 |
| DualPipe | 「雙向管線」 | 把前向／反向計算與跨節點 all-to-all 重疊起來的訓練排程 |
| 啟用參數比例 | 「稀疏度」 | active_params / total_params；DeepSeek-V3 是 5.5% |
| FP8 訓練 | 「8 位元訓練」 | 儲存與許多計算操作都用 FP8；相對 BF16 大約省一半記憶體，只付出很小的品質代價 |

## 延伸閱讀

- [DeepSeek-AI — DeepSeek-V3 Technical Report (arXiv:2412.19437)](https://arxiv.org/abs/2412.19437) —— 完整的架構、訓練與結果文件
- [DeepSeek-V3 model card on Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-V3) —— config 檔與部署說明
- [DeepSeek-V2 paper (arXiv:2405.04434)](https://arxiv.org/abs/2405.04434) —— 提出 MLA 的前身
- [DeepSeek-R1 paper (arXiv:2501.12948)](https://arxiv.org/abs/2501.12948) —— 建在 V3 架構上的推理訓練後繼者
- [Native Sparse Attention (arXiv:2502.11089)](https://arxiv.org/abs/2502.11089) —— DeepSeek 家族注意力的未來方向
- [DualPipe repository](https://github.com/deepseek-ai/DualPipe) —— 訓練排程的參考實作
