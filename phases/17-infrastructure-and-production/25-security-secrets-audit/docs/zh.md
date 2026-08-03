# 安全性 —— 密鑰、API 金鑰輪替、稽核日誌、守衛

> 用集中式保險庫（HashiCorp Vault、AWS Secrets Manager、Azure Key Vault）消除密鑰蔓延。永遠不要把憑證放在設定檔、進版控的 env 檔，或試算表裡。用 IAM 角色取代靜態金鑰；CI/CD 用 OIDC。AI 閘道模式是 2026 年的解法：應用 → 閘道 → 模型供應商，由閘道在執行期從保險庫拉憑證。在保險庫裡輪替，所有應用幾分鐘內就跟上 —— 不必重新部署，也不必在 Slack 上問「新金鑰在誰那裡」。輪替政策 ≤90 天；每次提交都用 TruffleHog / GitGuardian / Gitleaks 掃描。零信任：MFA、SSO、RBAC/ABAC、短生命週期權杖、裝置狀態。PII 清洗用實體辨識，在轉發之前把 PHI/PII 遮起來；一致化代碼化（Mesh 的做法）把敏感值對映到穩定的佔位符，好讓 LLM 保住程式碼／關係上的語意。網路出口：把 LLM 服務放在專用的 VPC/VNet 子網裡，只放行 `api.openai.com`、`api.anthropic.com` 等；擋掉所有其他對外連線。2026 年那起帶動風向的事故：Vercel 的供應鏈攻擊，透過被入侵的 CI/CD 憑證，把數千個客戶部署的環境變數外洩出去。

**類型：** 學習
**程式語言：** Python (stdlib, toy PII-scrubber + audit-log writer)
**先修單元：** 階段 17 · 19（AI 閘道）、階段 17 · 13（可觀測性）
**時間：** 約 60 分鐘

## 學習目標

- 列舉那四個密鑰管理反模式（進版控的設定檔、寫死的環境變數、試算表、靜態金鑰），並說出各自的替代方案。
- 解釋「AI 閘道從保險庫拉」這個模式，為何是 2026 年的生產標準。
- 實作一支帶一致化代碼化（同樣的值 → 同樣的佔位符）的 PII 清洗器，好讓語意存活下來。
- 說出 2026 年那起 Vercel 供應鏈事故，以及它教了我們什麼關於 CI/CD 憑證衛生的事。

## 問題所在

一位實習生把帶著 API 金鑰的 `.env` 提交上去。他們很快就把它刪掉了。金鑰早就進了 git 歷史 —— GitGuardian 掃描抓到它，而你的輪替流程是「在 Slack 上敲團隊、更新 40 個設定檔、重新部署所有服務」。8 小時後，你有一半的服務上線了，另一半還在等部署窗口。

另外，使用者的提示詞裡有「我的社會安全號碼是 123-45-6789」。提示詞送到 OpenAI。你有 BAA，但你們的內部政策是轉發前要遮蔽 PII。你沒有做。

再另外，你 EKS 叢集裡的 LLM Pod 連得到網際網路上的任何主機。有人透過 DNS 查詢把資料外洩到攻擊者控制的網域。沒有任何東西擋下它。

LLM 服務的安全性得處理這三個向量。保險庫支撐的憑證。PII 清洗。網路出口過濾。稽核日誌。

## 核心概念

### 集中式保險庫 + IAM 角色拉取

**保險庫**：HashiCorp Vault、AWS Secrets Manager、Azure Key Vault、GCP Secret Manager。單一真實來源。

**IAM 角色**：應用／閘道用它的 IAM 身分認證，而不是靜態金鑰。保險庫在權杖的生命週期內回傳那個密鑰。

**AI 閘道模式**：閘道在請求發生時從保險庫拉 `OPENAI_API_KEY`。在保險庫裡輪替；下一個請求就拿到新金鑰。不必重新部署。

### 輪替政策 ≤ 90 天

所有 API 金鑰、保險庫的 root 權杖、CI/CD 憑證。能自動輪替的就自動。手動輪替要記錄並追蹤。

### 密鑰掃描

- **TruffleHog** —— 對提交做正規表示式 + 熵值檢查。
- **GitGuardian** —— 商業產品，準確率高。
- **Gitleaks** —— 開源，跑在 CI 裡。

每次提交都跑。偵測到新密鑰就擋下 PR。

### 零信任姿態

- 所有帳號都必須 MFA。
- 透過 SAML/OIDC 做 SSO。
- 用 RBAC（角色式）或 ABAC（屬性式）做細緻的存取控制。
- 短生命週期權杖（以小時計，不是以天計）。
- 裝置狀態 —— 只允許有磁碟加密的公司裝置。

### PII / PHI 清洗

在提示詞離開你的基礎設施之前：

1. 實體辨識（spaCy NER、Presidio、商業方案）。
2. 把比對到的實體遮起來：`"My SSN is 123-45-6789"` → `"My SSN is [SSN_TOKEN_A3F]"`。
3. 一致化代碼化（Mesh 的做法）：同樣的值對映到同樣的佔位符，好讓 LLM 保住彼此的關係。
4. 對 LLM 回應做選配的反向對映。

靜態的正規表示式過濾器抓得到基本樣式；NER 抓得更多。兩個都用。

### 輸入與輸出守衛

輸入：擋掉已知的越獄手法、禁止的主題；逐使用者限流。

輸出：用正規表示式清洗外洩的密鑰（API 金鑰樣式、拒答脈絡裡的電子郵件樣式），用分類器抓政策違規。

### 網路出口白名單

把 LLM 服務放在專用子網裡：
- 白名單：`api.openai.com`、`api.anthropic.com`、向量資料庫端點、保險庫端點。
- 其他一律：丟棄。
- DNS 走只認允許清單的解析器（避免 DNS 通道式外洩）。

### 稽核日誌

每一次 LLM 呼叫的不可竄改日誌，含：
- 時間戳記。
- 使用者／租戶。
- 提示詞雜湊（為隱私不存原始提示詞）。
- 模型 + 版本。
- 詞元數。
- 成本。
- 回應雜湊。
- 任何觸發到的守衛。

依法規要求保存（SOC 2 一年、HIPAA 六年）。

### 2026 年的 Vercel 事故

供應鏈攻擊：被入侵的 CI/CD 憑證，把數千個客戶部署的環境變數外洩出去。教訓：CI/CD 憑證等同生產憑證。放進保險庫。權限收窄。積極輪替。

### 你該記住的數字

- 輪替政策：≤ 90 天。
- 每次提交都掃：TruffleHog / GitGuardian / Gitleaks。
- Vercel 2026：CI/CD 憑證被入侵 → 數千個客戶的環境變數外洩。
- 稽核日誌保存期：SOC 2 = 一年，HIPAA = 六年。

```figure
i4-vault-rotation
```

## 框架應用

`code/main.py` 實作一支帶一致化代碼化的玩具型 PII 清洗器，以及一份只能追加的稽核日誌。

## 產出交付

這一課產出 `outputs/skill-llm-security-plan.md`。給定法遵範圍與現況，規劃保險庫遷移、清洗器、出口控制與稽核日誌。

## 練習

1. 跑 `code/main.py`。送出兩段引用同一組社會安全號碼的提示詞。確認兩者拿到同樣的佔位符。
2. 替一套跑在 EKS 上、會呼叫 OpenAI + Anthropic + Weaviate 的 vLLM 部署，設計網路出口政策。
3. 你在 git 歷史裡發現一把金鑰（兩年前的）。正確的應對是什麼 —— 輪替金鑰、清洗歷史，還是兩者都做？論證一下。
4. 你的稽核日誌每天長 10 GB。設計保存分層（熱 30 天、溫 12 個月、冷 6 年）。
5. 論證反向代碼化（把真實值代換回 LLM 回應裡）值不值得那份複雜度，相對於讓佔位符就那樣露著。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|------|----------------|------------------------|
| 保險庫 | 「密鑰儲存」 | 集中式的憑證管理服務 |
| IAM 角色 | 「以身分為基礎的認證」 | 應用取用的角色；回傳短生命週期憑證 |
| CI/CD 用 OIDC | 「雲端簽發的權杖」 | CI 裡沒有靜態金鑰 —— 身分透過 OIDC |
| TruffleHog / GitGuardian / Gitleaks | 「密鑰掃描器」 | 提交時的密鑰偵測 |
| RBAC / ABAC | 「存取控制」 | 角色式對上屬性式 |
| PII 清洗 | 「資料遮罩」 | 移除或代碼化敏感實體 |
| 一致化代碼化 | 「穩定的佔位符」 | 同樣的值每次都對到同一個代碼 |
| Mesh 做法 | 「Mesh 代碼化」 | 保住語意的代碼化模式 |
| 出口白名單 | 「對外允許清單」 | 只有被許可的網域連得到 |
| 稽核日誌 | 「不可竄改的歷史」 | 供法遵用、只能追加的紀錄 |

## 延伸閱讀

- [Doppler — Advanced LLM Security](https://www.doppler.com/blog/advanced-llm-security)
- [Portkey — Manage LLM API keys with secret references](https://portkey.ai/blog/secret-references-ai-api-key-management/)
- [Datadog — LLM Guardrails Best Practices](https://www.datadoghq.com/blog/llm-guardrails-best-practices/)
- [JumpServer — Secrets Management Best Practices 2026](https://www.jumpserver.com/blog/secret-management-best-practices-2026)
- [Microsoft Presidio](https://github.com/microsoft/presidio) —— PII 偵測與匿名化。
- [HashiCorp Vault docs](https://developer.hashicorp.com/vault/docs)
