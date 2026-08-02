# 託管 LLM 平台 —— Bedrock、Vertex AI、Azure OpenAI

> 三家超大規模雲端業者，三種截然不同的策略。AWS Bedrock 是一個模型市集 —— Claude、Llama、Titan、Stability、Cohere 全在同一組 API 之後。Azure OpenAI 是與 OpenAI 的獨家合作，加上供專屬容量用的預配吞吐量單位（PTU）。Vertex AI 則以 Gemini 為先，長脈絡與多模態的故事講得最好。2026 年 Artificial Analysis 量到，在 Llama 3.1 405B 等級的部署上，Azure OpenAI 中位數約 50 毫秒、Bedrock 約 75 毫秒 —— PTU 解釋了這個落差，因為專屬容量勝過共享的隨需容量。判準不是「哪個最快」，而是「哪個模型目錄與 FinOps 表面跟我的產品相符」。這一課教你在把取捨寫下來的前提下做選擇，而不是靠感覺。

**類型：** 學習
**程式語言：** Python (stdlib, toy cost-and-latency comparator)
**先修單元：** 階段 11（LLM 工程）、階段 13（工具與協定）
**時間：** 約 60 分鐘

## 學習目標

- 說出那三種平台策略（市集、獨家、Gemini 為先），並把每一種對到一種產品使用情境。
- 解釋 Azure OpenAI 的預配吞吐量單位（PTU）替你買到了什麼，以及為何在 405B 規模上，隨需的 Bedrock 通常會慢上約 25 毫秒。
- 畫出每個平台的 FinOps 歸屬表面（Bedrock 的 Application Inference Profile、Vertex 的每團隊一專案、Azure 的範圍 + PTU 保留）。
- 寫下一份「最少兩家供應商」的政策，並解釋為何單一廠商鎖定是 2026 年那個昂貴的錯誤。

## 問題所在

你替產品挑了 Claude 3.7 Sonnet。現在你得把它服務出去。你可以直接呼叫 Anthropic API、也可以透過 AWS Bedrock 呼叫它，或者走一個閘道。直接 API 最簡單；Bedrock 加上了 BAA、VPC 端點、IAM 與 CloudWatch 歸屬。閘道則加上故障轉移、統一計費，以及跨供應商的速率限制。

更深的問題是目錄。如果你在同一個產品裡需要 Claude、Llama 與 Gemini，你就沒辦法從同一個地方全買到 —— 除非那個「地方」是 Bedrock 加 Vertex 加 Azure OpenAI 同時使用。這些超大規模業者並不可互換 —— 他們各自對「誰擁有模型層」下了不同的賭注。

這一課畫出那三種賭注、那個延遲落差、那個 FinOps 落差，以及鎖定風險。

## 核心概念

### 三種策略

**AWS Bedrock** —— 那個市集。Claude（Anthropic）、Llama（Meta）、Titan（AWS 第一方）、Stability（影像）、Cohere（嵌入）、Mistral，外加影像與嵌入的子目錄。一組 API、一個 IAM 表面、一份 CloudWatch 匯出。Bedrock 的賭注是：客戶想要的可選性大於單一模型。

**Azure OpenAI** —— 那個獨家合作。你拿到 GPT-4／4o／5／o 系列、DALL·E、Whisper，以及在 Azure 資料中心對 OpenAI 模型做微調。「Azure OpenAI Service」目錄裡沒有非 OpenAI 的模型 —— 那些歸 Azure AI Foundry（獨立產品）。Azure 的賭注是：OpenAI 仍會是前沿，而客戶想要在那段特定關係上有企業級的控制。

**Vertex AI** —— Gemini 為先，其他其次。Gemini 1.5／2.0／2.5 的 Flash 與 Pro，外加 Model Garden（第三方）。Vertex 的賭注是多模態長脈絡 —— 100 萬詞元的 Gemini 脈絡就是那個差異化。

### 規模上的延遲落差

Artificial Analysis 持續跑基準。在等價的 Llama 3.1 405B 部署上（共享隨需），Azure OpenAI 的首個詞元延遲中位數約 50 毫秒；Bedrock 約 75 毫秒。這個落差不是 AWS 的失誤 —— 它是容量模型的差異。Azure 賣 PTU（預配吞吐量單位），替你的租戶保留 GPU 容量。Bedrock 的對應物（Provisioned Throughput）也存在，但每單位起跳約每小時 21 美元，而多數客戶留在共享隨需上。

隨需的共享容量要跟其他所有客戶的流量競爭。專屬容量不用。若你的產品 SLA 是 P99 的 TTFT < 100 毫秒，你要嘛在 Azure 買 PTU、要嘛買 Bedrock 的 Provisioned Throughput，要嘛接受預設的變異。

### 預配吞吐量的經濟學

Azure PTU：一塊被保留的推論運算。對可預測的工作負載，相對隨需最多省約 70%。成本按小時固定，不管有沒有流量 —— 閒置時你也在付那份保留。損益平衡通常落在 40-60% 的持續使用率。

Bedrock Provisioned Throughput：依模型與區域每小時 21-50 美元。數學類似 —— 損益平衡大約在尖峰使用率的一半。需要月度承諾。

Vertex 的預配容量依 Gemini SKU 出售；價格隨模型與區域而異，而且公開廣告得比較少。

### FinOps 表面 —— 真正的差異化

**Bedrock 的 Application Inference Profile** 是這個市集裡最乾淨的歸屬機制。替一個 profile 標上 `team`、`product`、`feature`；讓所有模型調用都經過它；CloudWatch 就會逐 profile 拆出成本，不需要後處理。2025 年新增，仍是超大規模業者原生機制中最細緻的。

**Vertex** 的歸屬是「每團隊一專案」加「到處貼標籤」。你把每個團隊模型化成一個 GCP 專案、在每個資源上貼標籤，再用 BigQuery Billing Export + DataStudio 做彙總。工比較多，但 BigQuery 讓你能對成本資料下任意 SQL。

**Azure** 依賴訂閱／資源群組的範圍加標籤，並把 PTU 保留當成一等的成本物件。標籤是從資源群組繼承的，不是從請求來的，所以逐請求的歸屬需要 Application Insights 的自訂指標，或一個會蓋上標頭的閘道。

樣式是：Bedrock 的原生機制最乾淨、Vertex 透過 BigQuery 最有彈性、Azure 除非你自己儀器化否則最不透明。

### 鎖定是 2026 年的風險

在單一模型獨大的年代，押注單一超大規模業者沒問題。2026 年前沿每個月都在移動 —— 這一季是 Claude 3.7、下一季是 Gemini 2.5、再下一季是 GPT-5。鎖在一個平台上，就等於把自己鎖在三分之二的前沿之外。

有在運作的團隊採用的模式是：任何產品關鍵的 LLM 呼叫，最少兩家供應商。Bedrock 加 Azure OpenAI 是常見的組合 —— Claude 從一邊來、GPT 從另一邊來、彼此故障轉移、同一個閘道。因為閘道會做最佳路由，成本上升幅度可忽略；而在停擺期間（像 2025 年 1 月的 Azure OpenAI 事故、AWS us-east-1 的停擺）可用性的提升是決定性的。

### 資料落地、BAA 與受監管產業

Bedrock：多數區域提供 BAA；VPC 端點；護欄。金融科技常見的預設。
Azure OpenAI：HIPAA、SOC 2、ISO 27001；歐盟資料落地；受監管企業的預設。
Vertex：HIPAA、GDPR、依區域的資料落地；Google Cloud 的法遵堆疊。

三者都通過基本的勾選項。差異在於資料保留政策、日誌怎麼被處理，以及濫用監控會不會讀你的流量（多數預設加入；企業版可退出）。

### 你該記住的數字

- Azure OpenAI 在 Llama 3.1 405B 等級上的 TTFT 中位數：約 50 毫秒（有 PTU）。
- Bedrock 隨需的 TTFT 中位數：約 75 毫秒。
- Bedrock Provisioned Throughput：每單位每小時 21-50 美元。
- Azure PTU 的損益平衡：約 40-60% 的持續使用率。
- 高使用率下 PTU 相對隨需的節省：最多 70%。

## 框架應用

`code/main.py` 在一份合成工作負載上比較這三個平台 —— 它模型化隨需與 PTU 的經濟性、TTFT 變異，以及成本歸屬的保真度。跑它，看 PTU 在哪裡划算，以及市集的模型廣度在哪裡勝過一個 TTFT 落差。

## 產出交付

這一課產出 `outputs/skill-managed-platform-picker.md`。給定一份工作負載輪廓（需要哪些模型、TTFT SLA、每日量、法遵需求），它會建議一個主平台、一個備援，以及一份 FinOps 儀器化計畫。

## 練習

1. 跑 `code/main.py`。對一個 70B 等級的模型，在什麼持續使用率下 Azure PTU 會勝過隨需？算出損益平衡點，並跟廣告上的 40-60% 區間比較。
2. 你的產品需要 Claude 3.7 Sonnet 與 GPT-4o。設計一份雙供應商部署 —— 哪個放哪家超大規模業者、前面擺什麼閘道、故障轉移政策是什麼？
3. 一位受監管的醫療客戶要求 BAA、美東資料落地，以及 P99 TTFT 低於 100 毫秒。挑一個平台，並用三項具體功能來論證。
4. 你發現這個月的 Bedrock 帳單漲了 4 倍，但流量沒變。在沒有 Application Inference Profile 的情況下，你要怎麼找出元凶？有 profile 的話要多久？
5. 讀 Azure OpenAI 與 Bedrock 的定價頁。對一份每月 1 億詞元的 Claude 工作負載，哪一個比較便宜 —— 直接用 Anthropic API、Bedrock 隨需，還是 Bedrock Provisioned Throughput？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| Bedrock | 「AWS 的 LLM 服務」 | 橫跨 Claude、Llama、Titan、Mistral、Cohere 的模型市集 |
| Azure OpenAI | 「Azure 的 ChatGPT」 | 在 Azure 資料中心、帶企業控制的獨家 OpenAI 模型 |
| Vertex AI | 「Google 的 LLM」 | 以 Gemini 為先、另有 Model Garden 放第三方模型的平台 |
| PTU | 「專屬容量」 | 預配吞吐量單位 —— 被保留的推論 GPU，按小時計價 |
| Application Inference Profile | 「Bedrock 的標籤機制」 | 帶標籤、CloudWatch 原生的逐產品成本／用量 profile |
| Model Garden | 「Vertex 的目錄」 | Vertex AI 的第三方模型區，與 Gemini 分開 |
| 最少兩家供應商 | 「LLM 冗餘」 | 每條關鍵 LLM 路徑都跨 ≥2 家超大規模業者的政策 |
| BAA | 「HIPAA 的文書」 | 商業夥伴協議；處理 PHI 時必要；三者都提供 |
| 濫用監控 | 「那個看日誌的」 | 供應商側對提示詞／輸出做的安全掃描；企業版可退出 |

## 延伸閱讀

- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) —— 權威的費率表與 Provisioned Throughput 定價。
- [Azure OpenAI Service Pricing](https://azure.microsoft.com/en-us/pricing/details/azure-openai/) —— PTU 經濟學與費率表。
- [Vertex AI Generative AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) —— Gemini 分層與 Model Garden 的加價。
- [Artificial Analysis LLM Leaderboard](https://artificialanalysis.ai/) —— 跨供應商的持續延遲與吞吐量基準。
- [The AI Journal — AWS Bedrock vs Azure OpenAI CTO Guide 2026](https://theaijournal.co/2026/03/aws-bedrock-vs-azure-openai/) —— 企業決策框架。
- [Finout — Bedrock vs Vertex vs Azure FinOps](https://www.finout.io/blog/bedrock-vs.-vertex-vs.-azure-cognitive-a-finops-comparison-for-ai-spend) —— 並排的歸屬機制。
