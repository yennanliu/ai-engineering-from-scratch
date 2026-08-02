# Kubernetes 上的 GPU 自動擴縮 —— Karpenter、KAI Scheduler、群組排程

> 是三層，不是一層。Karpenter 動態配置節點（一分鐘以內，比 Cluster Autoscaler 快 40%）。KAI Scheduler 處理群組排程、拓撲感知與階層式佇列 —— 它防止那個「八取七」的部分配置陷阱：七個節點乾等著、燒著錢，就為了缺一張 GPU。應用層級的自動擴縮器（NVIDIA Dynamo Planner、llm-d 的 Workload Variant Autoscaler）依推論專屬的訊號擴縮 —— 佇列深度、KV 快取使用率 —— 而不是 CPU／DCGM 的工作週期。經典的 HPA 陷阱是：`DCGM_FI_DEV_GPU_UTIL` 是一個工作週期量測值：100% 可能是 10 個請求，也可能是 100 個。vLLM 會預先配置 KV 快取記憶體，所以記憶體永遠不會觸發縮減。這一課教你怎麼把這三層組起來，並避開 Karpenter 那個會在推論途中終止執行中 GPU 工作的預設 `WhenEmptyOrUnderutilized` 政策。

**類型：** 學習
**程式語言：** Python (stdlib, toy queue-depth autoscaler simulator)
**先修單元：** 階段 17 · 02（推論平台的經濟學）、階段 17 · 04（服務引擎內部）
**時間：** 約 75 分鐘

## 學習目標

- 畫出那三層自動擴縮（節點配置、群組排程、應用層級），並說出每一層用的工具。
- 解釋為何 `DCGM_FI_DEV_GPU_UTIL` 對 vLLM 是錯的 HPA 訊號，並說出兩個替代品（佇列深度、KV 快取使用率）。
- 描述群組排程，以及 KAI Scheduler 所防止的那個部分配置失敗模式（八張 GPU 有七張閒著）。
- 說出那個會終止執行中 GPU 工作的 Karpenter 整併政策（`WhenEmptyOrUnderutilized`），並指出 2026 年安全的替代方案。

## 問題所在

你的團隊在 Kubernetes 上出貨一個 LLM 服務。你用 `DCGM_FI_DEV_GPU_UTIL` 當訊號設好了 HPA。這個服務在上班時段釘在 100% 使用率。HPA 從不擴增 —— 它已經認為你滿載了。你手動加一個副本；TTFT 下降。HPA 還是不擴。這個訊號在騙你。

另外，你用 Cluster Autoscaler 管節點。凌晨兩點來了一個 100 萬詞元的提示詞；叢集花 3 分鐘配置節點，而那個請求逾時了。

再另外，你部署一個需要跨 2 個節點、8 張 GPU 的 70B 模型。叢集有 7 張 GPU 空著，剩 1 張散在 3 個節點上。Cluster Autoscaler 為了那缺的 1 張 GPU 配置一個節點。七個節點等了 4 分鐘、燒著錢，就為了 Kubernetes 把最後一張 GPU 生出來。

三層，三種不同的失敗模式。2026 年懂 GPU 的自動擴縮不是「把 HPA 打開」。它是把節點配置、群組排程與應用訊號自動擴縮組起來。

## 核心概念

### 第 1 層 —— 節點配置（Karpenter）

Karpenter 盯著待處理的 pod，並在約 45-60 秒內配置節點（Cluster Autoscaler 對 GPU 節點通常要 90-120 秒）。它依 `NodePool` 的限制動態挑選實例型別 —— 若你的 pod 需要 8 張 H100，而叢集沒有相符的節點，Karpenter 會直接配置一個，而不是去擴大某個既有群組。

**那個整併陷阱**：Karpenter 預設的 `consolidationPolicy: WhenEmptyOrUnderutilized` 對 GPU 池很危險。它會終止一個執行中的 GPU 節點，把 pod 遷到一個更便宜、尺寸更合適的實例上。對推論工作負載來說，那意味著驅逐執行中的請求，並在新節點上重新載入一個 70B 模型。損失是好幾分鐘的容量加上請求失敗。

GPU 池的安全設定：

```yaml
disruption:
  consolidationPolicy: WhenEmpty
  consolidateAfter: 1h
```

讓 Karpenter 在一小時後整併真正空著的節點，但永遠不驅逐執行中的工作。

### 第 2 層 —— 群組排程（KAI Scheduler）

KAI Scheduler（專案原名「Karp」後改名）處理預設 kube-scheduler 做不到的事：

**群組排程** —— 全有或全無地排程。一個需要 8 張 GPU 的分散式推論 pod，要嘛 8 個一起啟動，要嘛一個都不啟動。沒有這個，你就會撞上部分配置陷阱：8 個裡有 7 個啟動了、無限期地等著、燒著錢。

**拓撲感知** —— 知道哪些 GPU 共用 NVLink、哪些坐在同一個機架上、哪些之間有 InfiniBand。據此放置 pod。一個 DeepSeek-V3 67B 的張量平行工作負載必須待在同一個 NVLink 域裡；KAI Scheduler 會尊重這件事。

**階層式佇列** —— 多個團隊帶著優先度與配額，競爭同一個 GPU 池。只有在優先度規則允許時，B 團隊的訓練工作才會搶占 A 團隊的生產緊急需求。

KAI 以次要排程器的身分與 kube-scheduler 並存部署；你在工作負載上加註解來使用它。Ray 與 vLLM production-stack 都有整合。

### 第 3 層 —— 應用層級的訊號

**那個 HPA 陷阱**：`DCGM_FI_DEV_GPU_UTIL` 是一個工作週期指標 —— 它量的是每個取樣區間裡 GPU 有沒有在做事。100% 使用率可能代表 10 個併發請求，也可能是 100 個；反正 GPU 都很忙。依工作週期擴縮，就是在盲目擴縮。

更糟的是，vLLM 這類引擎會預先配置 KV 快取記憶體（到 `--gpu-memory-utilization` 為止）。就算只有一個請求，記憶體用量也維持在約 90%。基於記憶體的 HPA 永遠不會縮減。

**2026 年的替代訊號**：

- 佇列深度（等待預填的請求數）。
- KV 快取使用率（有多少比例的區塊被配置給活躍序列）。
- 逐副本的 P99 TTFT（你的 SLA 訊號）。
- Goodput（每秒滿足所有 SLO 的請求數）。

NVIDIA Dynamo Planner 與 llm-d 的 Workload Variant Autoscaler 消費這些訊號並擴縮副本。對 LLM 服務而言，它們完全取代 HPA。

### 什麼時候用什麼

| 擴縮決策 | 工具 |
|----------------|------|
| 增減節點 | Karpenter |
| 排程多 GPU 工作 | KAI Scheduler |
| 增減副本 | Dynamo Planner／llm-d WVA（或依佇列深度自訂的 HPA） |
| 選 GPU 型別 | Karpenter NodePool |
| 搶占低優先度 | KAI Scheduler 的佇列 |

### 分離式預填／解碼讓一切更複雜

若你跑分離式的預填／解碼（階段 17 · 17），你就有兩類 pod、各有不同的擴縮觸發：預填 pod 依佇列深度擴縮、解碼 pod 依 KV 快取壓力擴縮。llm-d 把它們暴露成獨立的 `Service`，各有逐角色的 HPA。不要試著在兩者前面擺同一個 HPA。

### 冷啟動在這裡也很要緊

冷啟動緩解（階段 17 · 10）正是節點配置時間變成使用者可見的地方。Karpenter 的 45-60 秒暖機，加上載入 20GB 模型，再加上引擎初始化，代表一個從零開始的請求要花 2-5 分鐘。替 SLO 關鍵路徑保留一個暖池（`min_workers=1`），或在應用層使用 Modal 式的檢查點。

### 你該記住的數字

- Karpenter 配置節點：約 45-60 秒，對比 Cluster Autoscaler 約 90-120 秒（GPU 節點）。
- KAI Scheduler 防止部分配置的浪費 —— 那個八取七陷阱。
- 拿 `DCGM_FI_DEV_GPU_UTIL` 當 HPA 訊號：壞的；改用佇列深度或 KV 使用率。
- Karpenter 的 `WhenEmptyOrUnderutilized`：會終止執行中的 GPU 工作。推論請用 `WhenEmpty + consolidateAfter: 1h`。

```figure
autoscaling
```

## 框架應用

`code/main.py` 在一份突發式 GPU 工作負載上模擬一套三層自動擴縮器。比較天真 HPA（工作週期）、佇列深度 HPA，以及 KAI 群組排程式的擴縮。回報未被滿足的請求數、GPU 閒置分鐘數，以及一個綜合分數。

## 產出交付

這一課產出 `outputs/skill-gpu-autoscaler-plan.md`。給定叢集拓撲、工作負載形狀與 SLO，它會設計一份三層的自動擴縮計畫。

## 練習

1. 跑 `code/main.py`。在突發式工作負載下，天真的工作週期 HPA 丟掉了多少佇列深度 HPA 接得住的請求？那個差異從哪裡來？
2. 替一個在 H100 SXM5 上服務 Llama 3.3 70B FP8 的叢集設計一份 Karpenter NodePool。指定 `capacity-type`、`disruption.consolidationPolicy`、`consolidateAfter`，以及一個能把非 GPU 工作負載擋在這些節點外的 taint。
3. 你的團隊回報部署卡在 Pending，因為「GPU 明明有空、pod 就是排不上」。診斷 —— 這是 Karpenter、kube-scheduler，還是 KAI Scheduler 的問題？哪些指標可以確認？
4. 替分離式的預填 pod 挑一個擴縮訊號，再替解碼 pod 挑另一個不同的訊號。兩個都要論證。
5. 對一個全天候的生產服務（平均每天 60 次在 P99 TTFT > 10 秒時丟請求的事件），算出 `WhenEmptyOrUnderutilized` 整併陷阱的成本。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| Karpenter | 「那個節點配置器」 | Kubernetes 的節點自動擴縮器；次分鐘級配置 |
| Cluster Autoscaler | 「那個舊的擴縮器」 | Kubernetes 節點自動擴縮的前輩；較慢、以群組為單位 |
| KAI Scheduler | 「那個 GPU 排程器」 | 處理群組 + 拓撲 + 佇列的次要排程器 |
| 群組排程 | 「全有或全無」 | 原子性地排 N 個 pod，否則全部延後 |
| 拓撲感知 | 「知道機架」 | 依 NVLink／IB／機架位置來放置 pod |
| `DCGM_FI_DEV_GPU_UTIL` | 「GPU 使用率」 | 工作週期指標；對 LLM 來說「不是」擴縮訊號 |
| 佇列深度 | 「等待中的請求」 | 預填受限式擴縮的正確 HPA 訊號 |
| KV 快取使用率 | 「記憶體壓力」 | 解碼受限式擴縮的正確 HPA 訊號 |
| 整併 | 「Karpenter 的整併」 | 為換到更便宜實例型別而終止節點 |
| `WhenEmpty + 1h` | 「安全的整併」 | 不會驅逐執行中 GPU 工作的政策 |

## 延伸閱讀

- [KAI Scheduler GitHub](https://github.com/kai-scheduler/KAI-Scheduler) —— 設計文件與設定範例。
- [Karpenter Disruption Controls](https://karpenter.sh/docs/concepts/disruption/) —— 整併政策的語意與 GPU 安全的預設值。
- [NVIDIA — Disaggregated LLM Inference on Kubernetes](https://developer.nvidia.com/blog/deploying-disaggregated-llm-inference-workloads-on-kubernetes/) —— Dynamo Planner 的擴縮訊號。
- [Ray docs — KAI Scheduler for RayClusters](https://docs.ray.io/en/latest/cluster/kubernetes/k8s-ecosystem/kai-scheduler.html) —— Ray 的整合模式。
- [AWS EKS Compute and Autoscaling Best Practices](https://docs.aws.amazon.com/eks/latest/best-practices/aiml-compute.html) —— 託管 Kubernetes 專屬的指引。
- [llm-d GitHub](https://github.com/llm-d/llm-d) —— Workload Variant Autoscaler 的設計。
