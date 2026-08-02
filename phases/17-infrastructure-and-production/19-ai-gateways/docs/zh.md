# AI 閘道 —— LiteLLM、Portkey、Kong AI Gateway、Bifrost

> 一個閘道坐在你的應用與模型供應商之間。核心功能是供應商路由、退路、重試、速率限制、密鑰參照、可觀測性、守衛。2026 年的市場分佈：**LiteLLM** 是 MIT 授權的開源專案，支援 100+ 供應商、OpenAI 相容，但在約 2000 RPS 附近就撐不住（8 GB 記憶體，已發表的基準裡出現連鎖故障）；最適合 Python、<500 RPS、開發／原型。**Portkey** 定位在控制平面（守衛、PII 遮蔽、越獄偵測、稽核軌跡），2026 年 3 月開源為 Apache 2.0，延遲開銷 20-40 毫秒，生產層級每月 49 美元。**Kong AI Gateway** 建在 Kong Gateway 之上 —— Kong 自己在同樣 12 顆 CPU 上的基準：比 Portkey 快 228%、比 LiteLLM 快 859%；定價每個模型每月 100 美元（Plus 層級最多 5 個）；若你已經在用 Kong，就很適合企業採用。**Bifrost**（Maxim AI）—— 自動重試搭配可設定的退避，OpenAI 回 429 時退到 Anthropic。**Cloudflare / Vercel AI Gateway** —— 託管、零維運、基本重試。資料落地要求驅動了自架與否的決定；Portkey 與 Kong 位在中間，提供開源 + 可選的託管。

**類型：** 學習
**程式語言：** Python (stdlib, toy gateway-routing simulator)
**先修單元：** 階段 17 · 01（託管 LLM 平台）、階段 17 · 16（模型路由）
**時間：** 約 60 分鐘

## 學習目標

- 列舉那六項核心閘道功能（路由、退路、重試、速率限制、密鑰、可觀測性、守衛）。
- 把 2026 年的四套閘道（LiteLLM、Portkey、Kong AI、Bifrost）對到各自的規模天花板與使用情境。
- 引用 Kong 的基準（比 Portkey 快 228%、比 LiteLLM 快 859%），並解釋它為什麼在 >500 RPS 時要緊。
- 在給定資料落地要求與維運預算下，在自架與託管之間做選擇。

## 問題所在

你的產品會呼叫 OpenAI、Anthropic，以及一套自架的 Llama。每家供應商都有不同的 SDK、錯誤模型、速率限制與認證機制。你想要故障轉移（OpenAI 回 429 就試 Anthropic）、單一的憑證庫、統一的可觀測性，以及逐租戶的速率限制。

在應用層重新造這一套，會讓每個服務都跟每家供應商耦合。一層閘道把它整併成單一行程、單一 API（通常是 OpenAI 相容），再扇出到各家供應商。

## 核心概念

### 六項核心功能

1. **供應商路由** —— OpenAI、Anthropic、Gemini、自架等等，都在同一組 API 之後。
2. **退路** —— 遇到 429、5xx 或品質失敗時，改到別處重試。
3. **重試** —— 指數退避、有上限的嘗試次數。
4. **速率限制** —— 逐租戶、逐金鑰、逐模型。
5. **密鑰參照** —— 在執行期從保險庫拉憑證（永遠不放在應用裡）。
6. **可觀測性** —— OTel + GenAI 屬性（階段 17 · 13）+ 成本歸屬。
7. **守衛** —— PII 遮蔽、越獄偵測、允許主題過濾。

### LiteLLM —— MIT 開源、Python

- 100+ 供應商、OpenAI 相容、路由設定、退路、基本可觀測性。
- 在 Kong 的基準裡約 2000 RPS 就撐不住；8 GB 記憶體足跡，在持續負載下出現連鎖故障。
- 最適合：Python 應用、<500 RPS、開發／預備環境的閘道、實驗性路由。
- 成本：開源 0 元；也有雲端免費層級。

### Portkey —— 控制平面定位

- 自 2026 年 3 月起是 Apache 2.0 開源。守衛、PII 遮蔽、越獄偵測、稽核軌跡。
- 每請求 20-40 毫秒的延遲開銷。
- 生產層級每月 49 美元，含資料保留 + SLA。
- 最適合：需要把守衛與可觀測性綁在一起的受管制產業。

### Kong AI Gateway —— 主打規模

- 建在 Kong Gateway 之上（成熟的 API 閘道產品，lua + OpenResty）。
- Kong 自己在 12 顆 CPU 等價機器上的基準：比 Portkey 快 228%、比 LiteLLM 快 859%。
- 定價：每個模型每月 100 美元，Plus 層級最多 5 個。
- 最適合：已經在用 Kong；>1000 RPS；願意付授權費。

### Bifrost（Maxim AI）

- 自動重試搭配可設定的退避。
- 「OpenAI 回 429 就退到 Anthropic」是它的經典配方。
- 較新的參賽者；商業產品。

### Cloudflare AI Gateway / Vercel AI Gateway

- 託管、零維運。基本的重試與可觀測性。
- 最適合：跑在 Cloudflare/Vercel 上、做邊緣服務的 JavaScript 應用。
- 在守衛與速率限制上，跟 Kong/Portkey 相比功能有限。

### 自架對上託管

資料落地是那個強制因素。醫療與金融預設自架（LiteLLM、Portkey 開源版，或 Kong）。消費性產品預設託管（Cloudflare AI Gateway）或中間層（Portkey 託管版）。混合式：受管制的租戶自架，其他人用託管。

### 延遲預算

- LiteLLM：典型 5-15 毫秒開銷。
- Portkey：20-40 毫秒開銷。
- Kong：3-8 毫秒開銷。
- Cloudflare/Vercel：1-3 毫秒開銷（邊緣優勢）。

閘道延遲直接加到 TTFT 上。若 SLA 是 TTFT P99 < 100 毫秒，選 Kong 或 Cloudflare。若是 P99 < 500 毫秒，隨便哪個都行。

### 速率限制的語意很要緊

單純的權杖桶在中等規模以下沒問題。多租戶需要滑動窗口 + 突發額度 + 逐租戶分層。LiteLLM 出貨的是權杖桶；Kong 出貨的是滑動窗口；Portkey 出貨的是分層式。

### 閘道 + 可觀測性 + 路由是可組合的

階段 17 · 13（可觀測性）、16（模型路由）、19（閘道）在生產上是同一層。挑一個工具涵蓋這三者，或小心地把它們接起來：2026 年多數部署會把 Helicone（可觀測性）或 Portkey（守衛）與 Kong（規模）組合起來，分工承擔不同角色。

### 你該記住的數字

- LiteLLM：約 2000 RPS 就崩，8 GB 記憶體。
- Portkey：20-40 毫秒開銷；自 2026 年 3 月起是 Apache 2.0。
- Kong：比 Portkey 快 228%、比 LiteLLM 快 859%。
- Kong 定價：每個模型每月 100 美元，Plus 層級最多 5 個。
- Cloudflare/Vercel：邊緣上 1-3 毫秒開銷。

## 框架應用

`code/main.py` 在注入 429/5xx 的情況下，模擬跨 3 家供應商、帶退路的閘道路由。回報延遲、重試率與退路命中率。

## 產出交付

這一課產出 `outputs/skill-gateway-picker.md`。給定規模、維運姿態、法遵與延遲預算，挑出一套閘道。

## 練習

1. 跑 `code/main.py`。把退路設定成 OpenAI→Anthropic→自架。在供應商錯誤率 5% 時，預期命中率是多少？
2. 你的 SLA 是在 300 毫秒基線上做到 TTFT P99 < 200 毫秒。哪些閘道還在預算內？
3. 一位醫療客戶要求自架 + PII 遮蔽 + 稽核。在 Portkey 開源版與 Kong 之間挑一個。
4. 比較 LiteLLM 與 Kong：團隊該在什麼 RPS 天花板上遷移？
5. 替一套多租戶 SaaS 設計速率限制政策：免費層、試用層、付費層。要用權杖桶還是滑動窗口？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| 閘道 | 「API 仲介」 | 坐在應用與供應商之間的行程 |
| LiteLLM | 「那個 MIT 的」 | Python 開源，100+ 供應商，2K RPS 就崩 |
| Portkey | 「守衛型閘道」 | 控制平面 + 可觀測性，Apache 2.0 |
| Kong AI Gateway | 「主打規模的那個」 | 建在 Kong Gateway 上，基準領先者 |
| Bifrost | 「Maxim 的閘道」 | 重試 + 退到 Anthropic 的配方 |
| Cloudflare AI Gateway | 「邊緣託管」 | 部署在邊緣的託管閘道，零維運 |
| PII 遮蔽 | 「資料清洗」 | 送給模型前先用正規表示式 + NER 遮罩 |
| 越獄偵測 | 「提示詞注入防護」 | 對使用者輸入跑分類器 |
| 稽核軌跡 | 「受管制的日誌」 | 每一次 LLM 呼叫的不可竄改紀錄 |
| 權杖桶 | 「簡單的速率限制」 | 以補充為基礎的限流器 |
| 滑動窗口 | 「精確的速率限制」 | 以時間窗口計算的限流器；公平性更好 |

## 延伸閱讀

- [Kong AI Gateway Benchmark](https://konghq.com/blog/engineering/ai-gateway-benchmark-kong-ai-gateway-portkey-litellm)
- [TrueFoundry — AI Gateways 2026 Comparison](https://www.truefoundry.com/blog/a-definitive-guide-to-ai-gateways-in-2026-competitive-landscape-comparison)
- [Techsy — Top LLM Gateway Tools 2026](https://techsy.io/en/blog/best-llm-gateway-tools)
- [LiteLLM GitHub](https://github.com/BerriAI/litellm)
- [Portkey GitHub](https://github.com/Portkey-AI/gateway)
- [Kong AI Gateway docs](https://docs.konghq.com/gateway/latest/ai-gateway/)
