# 生產服務堆疊 —— KV 卸載與知快取的路由

> 一套生產服務堆疊，把路由器、引擎與可觀測性接進同一份 Kubernetes 部署 —— 並把 KV 快取當成一項可以離開 GPU 的資源。KV 卸載把 KV 快取從 GPU 記憶體抽出來，並跨查詢與跨引擎重用它（先 CPU DRAM，再磁碟／Ceph）。vLLM 的 production-stack 是那份參考部署；LMCache 是那層卸載。vLLM 0.11.0 的 KV Offloading Connector（2026 年 1 月）透過 Connector API（v0.9.0+）讓這件事變成非同步且可插拔。卸載路徑通常對請求路徑是隱形的，不過快取未命中與晉升仍可能增加端到端延遲。就算沒有共享前綴，LMCache 也有價值 —— 當一張 GPU 的 KV 槽位用盡時，被搶占的請求可以從 CPU 還原，而不必重新做預填。已發表的基準是在 4 台 a3-highgpu-4g 上的 16 張 H100（80GB HBM）：當 KV 快取超過 HBM 時，原生 CPU 卸載與 LMCache 都大幅改善吞吐量；在 KV 佔用很低時，各種設定都與基線相當，只有小小的開銷。

**類型：** 學習
**程式語言：** Python (stdlib, toy KV-spill simulator)
**先修單元：** 階段 17 · 04（服務引擎內部）、階段 17 · 06（SGLang/RadixAttention）
**時間：** 約 60 分鐘

## 學習目標

- 畫出 vLLM production-stack 的各層：路由器、引擎、KV 卸載、可觀測性。
- 解釋 KV Offloading Connector API（v0.9.0+），以及 0.11.0 的非同步路徑如何把卸載延遲藏起來。
- 量化 LMCache 的 CPU-DRAM 何時有幫助（KV > HBM）、何時只是增加開銷（KV 小到裝得進 HBM）。
- 在給定部署限制下，在 vLLM 原生 CPU 卸載與 LMCache connector 之間做選擇。

## 問題所在

你的 vLLM 服務顯示 GPU 的 HBM 都在 100%，而且併發一爬升就出現搶占事件。請求被逐出、重新排隊，然後你在一分鐘內把同一段 2K 詞元的提示詞重新預填四次。GPU 的運算花在冗餘的預填上；goodput 遠低於原始吞吐量。

加更多 GPU 是線性花錢。加更多 HBM 不可能。但 CPU DRAM 很便宜 —— 一顆插槽就有 512 GB 以上，延遲比 HBM 差好幾個數量級，但拿來放「暫時溫熱」的 KV 快取剛剛好。

LMCache 把 KV 快取抽到 CPU DRAM，好讓被搶占的請求快速恢復，並讓跨引擎重複出現的前綴共享快取，而不必每個引擎各自重新預填。

## 核心概念

### vLLM production-stack

`github.com/vllm-project/production-stack` 是那份參考 Kubernetes 部署：

- **路由器** —— 知快取的（階段 17 · 11）。消費 KV 事件。
- **引擎** —— vLLM 的 worker。每張 GPU 一個，或每個 TP/PP 群組一個。
- **KV 快取卸載** —— LMCache 部署或原生 connector。
- **可觀測性** —— Prometheus 抓取、Grafana 儀表板、OTel 軌跡。
- **控制平面** —— 服務發現、設定、滾動更新。

以 Helm chart + operator 的形式出貨。

### KV Offloading Connector API（v0.9.0+）

vLLM 0.9.0 引入了一組供可插拔 KV 快取後端使用的 Connector API。你的引擎把區塊卸載給 connector；connector 把它們存起來（RAM、磁碟、物件儲存、LMCache）。請求需要某個區塊時，connector 再把它載回來。

vLLM 0.11.0（2026 年 1 月）加上非同步的卸載路徑 —— 卸載可以在背景發生，所以在常見情況下引擎不必等它。端到端延遲與吞吐量仍取決於工作負載形狀、KV 快取命中率與系統壓力；vLLM 自己的說明也指出，在低命中率下自訂核心的卸載可能讓吞吐量退化，而非同步排程與推測解碼之間有已知的互動問題。

### 原生 CPU 卸載對上 LMCache

**vLLM 原生 CPU 卸載**：引擎本地。把 KV 區塊存在主機 RAM 裡。實作快、沒有網路跳躍。不跨引擎。

**LMCache connector**：叢集規模。把區塊存在一台共享的 LMCache 伺服器上（CPU DRAM + Ceph/S3 層）。任何引擎都存取得到那些區塊。已發表 16 張 H100 的基準。

當單一引擎有 HBM 壓力時挑原生。當多個引擎共享前綴時（帶共同系統提示詞的 RAG、共用樣板的多租戶）挑 LMCache。

### 基準行為

那份跨 4 台 a3-highgpu-4g、16 張 H100（80 GB HBM）的測試：

- KV 佔用低（短提示詞、低併發）：所有設定都與基線相當，LMCache 增加約 3-5% 開銷。
- 中等佔用：LMCache 開始在跨引擎的前綴重用上發揮作用。
- KV 超過 HBM：原生 CPU 卸載與 LMCache 都大幅改善吞吐量；LMCache 收穫更大，因為它能跨引擎共享。

### LMCache 決定性的時候

- 多租戶服務，且系統提示詞跨租戶共享。
- RAG，且文件片段在多個查詢間重複。
- 同一基礎模型上的微調變體（LoRA），讓基礎模型的 KV 重用砍掉冗餘工作。
- 搶占吃重的工作負載：從 CPU 還原比重新預填便宜。

### 什麼時候「不要」啟用

- HBM 壓力很小 —— 你付了開銷卻沒好處。
- 短脈絡（<1K 詞元）—— 轉移時間 > 重新預填。
- 單租戶、單一提示詞的工作負載 —— 沒有可捕捉的重用。

### 與分離式服務的整合

階段 17 · 17 的分離式服務加上 LMCache 會相乘：從預填池轉到解碼池的 KV，若沒被用到就落進 LMCache；後續查詢再從 LMCache 拉。階段 17 · 11 那個知快取的路由器，可以路由到「本地快取或 LMCache 共享快取」有相符的那個引擎。

### 你該記住的數字

- vLLM 0.9.0：Connector API 出貨。
- vLLM 0.11.0（2026 年 1 月）：非同步卸載路徑；端到端延遲的影響取決於工作負載、KV 命中率與系統壓力（不是絕對保證）。
- 16 張 H100 的基準：當 KV 佔用超過 HBM 時 LMCache 有幫助。
- HBM 壓力很小時：3-5% 開銷、沒有好處。

```figure
zero-sharding
```

## 框架應用

`code/main.py` 在有與沒有 LMCache 的情況下，模擬一份搶占吃重的工作負載。回報避免掉的重新預填次數、吞吐量增益，以及 HBM 使用率的損益平衡點。

## 產出交付

這一課產出 `outputs/skill-vllm-stack-decider.md`。給定工作負載形狀與 vLLM 部署，判斷要用原生、LMCache，還是兩者都不用。

## 練習

1. 跑 `code/main.py`。在什麼 HBM 使用率之下 LMCache 開始划算？
2. 某位租戶在每小時 200 次查詢間共享一段 6K 詞元的系統提示詞。算出每位租戶預期的 LMCache 節省。
3. LMCache 伺服器是一個單點失效。設計那套高可用策略（副本、退回原生）。
4. LMCache 存到跑在傳統硬碟上的 Ceph。對一份 70B FP8 上 4K 詞元的 KV（500 MB），讀取時間與重新預填相比如何？
5. 論證 vLLM 0.11.0 那條非同步路徑是不是「免費的」—— 那些開銷躲在哪裡？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| Production-stack | 「那份參考部署」 | vLLM 的 Kubernetes Helm chart + operator |
| Connector API | 「KV 後端介面」 | vLLM 0.9.0+ 可插拔的 KV 儲存介面 |
| 原生 CPU 卸載 | 「引擎本地的外溢」 | 把 KV 存在同一引擎的主機 RAM 裡 |
| LMCache | 「叢集級的 KV 快取」 | 跑在 CPU DRAM + 磁碟上、跨引擎的 KV 快取伺服器 |
| 0.11.0 非同步 | 「不阻塞的卸載」 | 卸載藏在引擎的串流之後 |
| 搶占 | 「逐出以騰空間」 | HBM 滿了時的 KV 快取洗牌 |
| 前綴重用 | 「同一段系統提示詞」 | 多個查詢共享開頭；快取命中 |
| Ceph 層 | 「磁碟層」 | 快取階層中位於 DRAM 之下的持久儲存 |

## 延伸閱讀

- [vLLM Blog — KV Offloading Connector (Jan 2026)](https://blog.vllm.ai/2026/01/08/kv-offloading-connector.html)
- [vLLM Production Stack GitHub](https://github.com/vllm-project/production-stack) —— Helm chart + operator。
- [LMCache for Enterprise-Scale LLM Inference (arXiv:2510.09665)](https://arxiv.org/html/2510.09665v2)
- [LMCache GitHub](https://github.com/LMCache/LMCache) —— Connector 的實作。
- [vLLM 0.11.0 release notes](https://github.com/vllm-project/vllm/releases) —— 非同步路徑的細節。
