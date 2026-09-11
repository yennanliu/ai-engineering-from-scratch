# 技能叫用與路由

> 叫用是一次權限決策，後面接一次相關性決策。一段好的描述幫模型做選擇；一套好的政策決定那個選擇准不准。

**類型：** 實作
**程式語言：** Python (stdlib)
**先修單元：** 階段 13 · 24（技能發現與漸進揭露）
**時間：** 約 105 分鐘

## 學習目標

- 分辨明確的使用者叫用、隱含的模型叫用、應用程式叫用，以及技能對技能的叫用。
- 把「人看得見」與「模型有資格」建模成兩個互相獨立的政策維度。
- 寫出帶正向觸發與差一點邊界的路由描述。
- 在追蹤與測試裡，把資格、選擇、啟用、引數繫結與執行分開。
- 轉接執行環境專屬的叫用欄位，但不把它們說成可攜的 frontmatter。

## 問題所在

你裝了一項 `database-migration` 技能。使用者可以依名稱執行它，但模型也看得到它的描述，於是有人問一般的資料庫問題時它就被選中。這項技能接著替一件只需要一段說明的任務提出了 schema 變更。

你加上 `user-invocable: false`，期待這能擋住人手動執行它。在另一個執行環境裡，那個欄位被忽略了。你加上 `disable-model-invocation: true`，期待這項技能會整個消失。在懂這個欄位的執行環境裡，使用者照樣可以明確叫用它。

那些欄位名稱沒有錯。錯的是模型。「使用者看得見它」、「模型可以選它」、「應用程式可以預先載入它」與「它裡面的工具可以執行」是分開的事實。單一個叫 `invocable` 的布林值表達不出它們。

路由還有第二種失敗模式。如果描述含糊，好幾項技能都變得有可能。如果描述塞滿關鍵字，不相關的任務就會觸發它們。目錄是一個機率性的介面：精簡到塞得進去，具體到路得對。

## 核心概念

### 有五個通道可以啟動這條生命週期

| 行動者 | 叫用形狀 | 典型用途 | 主要風險 |
|---|---|---|---|
| 人類使用者 | 在 UI 或提示詞裡指名一項技能 | 刻意選定的工作流程 | 使用者以為有的可用性或權限，宿主其實沒給 |
| 模型或自主代理 | 從任務脈絡選出一筆目錄項目 | 自動套用專家程序 | 誤判的路由 |
| 應用程式 | 透過執行環境的程式碼啟用或預先載入一項技能 | 固定的產品流程 | 對單一宿主的隱藏耦合 |
| 另一項技能或子代理 | 把某項確切的技能當成流程依賴請求過來 | 組合 | 循環、依賴缺漏，或上下文滲漏 |
| 評估框架 | 在固定情境下啟用某項確切的技能 | 可重複的量測 | 測到了技能，卻不小心繞過了正在研究的那條生產政策 |

可攜的 Agent Skills 規格定義的是套件。它沒有把某一套通用的斜線指令 UI、隱含路由旗標、應用程式 API 或子代理生命週期標準化。

### 叫用的五個階段

```figure
skill-invocation-stages
```

把這幾個詞用精確：

- **有資格** 是說政策允許這個行動者請求這項技能。
- **被選中** 是說使用者指名了它，或某個路由器判斷它相關。
- **已啟用** 是說它的指示進入了工作上下文。
- **正在執行** 是說代理在那些指示之下開始了模型或工具的工作。
- **已完成** 是說輸出通過了一次獨立的成功檢查。

一份只記下 `skill_used=true` 的追蹤，會藏住失敗發生在哪一道邊界。

### 人與模型的叫用構成一個 2x2 矩陣

| 人可以叫用 | 模型可以叫用 | 模式 | 合適的例子 |
|:---:|:---:|---|---|
| 是 | 是 | 共用 | 程式碼講解、測試規劃、文件審查 |
| 是 | 否 | 只給人 | 發布前準備、帳務匯出、破壞性清理計畫 |
| 否 | 是 | 只給模型 | 內部風格指南、領域參考、自動化的支援程序 |
| 否 | 否 | 停用，或只給應用程式 | 分批推出、已棄用的套件、程式化的預先載入 |

這個矩陣是一個政策模型，不是標準的 YAML。

某個現行宿主用 `disable-model-invocation: true` 表達「只給人」那一列，用 `user-invocable: false` 表達「只給模型」那一列。預設是兩者皆可。另一個宿主用 `agents/openai.yaml` 裡的 `allow_implicit_invocation: false` 來保留明確叫用、同時關掉隱含選擇。這些都是執行環境轉接器。不認識它們的宿主可能會忽略。

那個容易搞混的細節很重要：`user-invocable: false` 不是「模型不能用這個」。它拿掉的是定義這個欄位的那個宿主裡的直接使用者叫用。`disable-model-invocation: true` 也不是「這項技能被停用了」。它拿掉的是模型自己發起的選擇，同時保留明確的使用者存取。

### 明確叫用是身分優先

明確叫用直接把身分給出來：

```text
/release-readiness v2.4.0
```

或者：

```text
release-readiness check v2.4.0 without publishing
```

現行的 Codex 介面記載的是用 `/skills` 做選擇，並在請求裡直接寫技能名稱來做明確叫用。Claude Code 記載的是 `/skill-name` 與宿主專屬的引數展開。確切的語法、選單可見性、引號規則與變數展開都屬於宿主。

一個明確請求仍然要過政策。指名一項技能，不該繞過缺少的權限、工作區限制、核可閘門或執行環境隔離。

### 隱含叫用是描述優先

在隱含路由裡，模型一開始看到的是目錄中繼資料，不是完整本體。因此描述就是這項技能的路由介面。

太弱：

```yaml
description: Helps with releases.
```

太寬：

```yaml
description: Use for release, version, package, build, deploy, publish, tag, changelog, GitHub, CI, or software tasks.
```

有界：

```yaml
description: Inspect an already prepared release candidate and produce a readiness report. Use when the user asks whether a version, tag, package, or image is ready to publish; do not use for ordinary build failures or feature development.
```

那個有界的版本含有：

1. **能力：** 檢視一個已經準備好的候選版本。
2. **輸出：** 一份就緒報告。
3. **正向邊界：** 使用者在問某個發布產物準備好了沒有。
4. **負向邊界：** 一般的建置與開發不在範圍內。

當兩項相鄰的技能共用詞彙時，負向邊界很有用。但它取代不了差一點的評估。

### 路由是一個帶「棄權」選項的分類問題

對一項技能 `s` 與一個請求 `x`，想像一個路由器分數：

```text
score(s, x) = capability_match + trigger_match + context_match - exclusion_match - ambiguity_penalty
```

實際的評分可能是一次 LLM 的判斷，而不是算術。工程原則不變：選擇要同時勝過一個門檻與一個競爭技能。當證據薄弱時，棄權。

```figure
skill-routing-abstention
```

對影響大的技能，就算描述很強，隱含路由也可能不合適。當一次誤判的代價超過自動選擇的方便時，就用「只給人」的政策。

### 資格必須排在排名之前

不要把每一個被發現的技能都評分、挑出最強的那個，然後才去檢查那一項技能的政策。一個被擋掉的第一名，會錯誤地讓一個有資格但分數較低的候選連被考慮的機會都沒有。

隱含路由請用這個順序：

1. 依請求方的行動者與當前生效的宿主轉接器，過濾被發現的技能。
2. 只替有資格的候選評分。
3. 若最強的合格匹配過了門檻與歧義規則，就選它。
4. 當沒有候選有資格，或沒有任何合格分數夠強時，棄權。

假設 `incident-triage` 得 `0.80`，但它的宿主擴充關掉了模型叫用。`incident-review` 得 `0.55`，而且允許模型叫用。路由器應該把 `incident-review` 評為最好的合格候選。它不該選了 `incident-triage`、把它拒掉，然後就停下來。

這個順序也讓政策的變動不會改變相關性分數的意義。資格定義的是選擇集合。相關性替那個集合排名。

### 路由評估需要差一點的案例

正例證明召回率：

```json
{"prompt":"Is version 2.4.0 ready to publish?","expected":"release-readiness"}
```

明確的負例證明基本的精確率：

```json
{"prompt":"Explain rotary position embeddings.","expected":null}
```

差一點的案例暴露邊界品質：

```json
{"prompt":"Why did today's package build fail?","expected":"build-diagnostics"}
```

這個差一點的案例跟那個發布技能共用了 `package` 與 `build`，但它屬於別的地方。一組只由明顯正例與不相關負例組成的路由測試集，會把品質高估。

### 引數有三種表現形式

一個叫用引數會跨過好幾道邊界：

```figure
skill-argument-boundaries
```

在每一道邊界上，都要保住意圖，同時不把文字當成程式碼。

- 宿主的解析器決定指令語法與引號規則。
- 技能依宿主規則收到被繫結的文字或變數。
- 指示驗證必要的值與預設值。
- 一次工具呼叫把值轉成有型別的 schema，並重新驗證它們。

不要把原始引數插值進 shell 指令。優先用一支以引數向量呼叫的腳本，或一個有型別的 MCP 工具。

### 應用程式叫用是明確的編排

一個產品可以直接啟用一項技能，因為它的流程已經知道任務類型。舉例來說，一個 pull request 審查服務可以在使用者按下 Review 之後，先載入 `pull-request-risk-review`。

這消掉了路由的不確定性，但造出了對執行環境 API 的依賴。把那個轉接器留在可攜的本體之外：

```figure
skill-host-adapter
```

當這項技能被另一個相容客戶端打開時，它應該還是讀得懂。

### 技能對技能的叫用是一條類似工具的邊

假設 `release-readiness` 在依賴檔案有變動時，會去要 `security-change-review`。

呼叫方應該提供：

- 目標技能的身分；
- 一件有界的任務與產物路徑；
- 預期的回應契約；
- 叫用的理由；
- 對方不存在時的退路；
- 一條最大深度或循環規則。

```json
{
  "target_skill": "security-change-review",
  "task": "Review dependency changes in the candidate diff",
  "inputs": ["artifacts/release.diff"],
  "expected": "risk-report.json",
  "max_depth": 2
}
```

第二項技能不是被盲目貼進第一項裡。宿主決定怎麼啟用它，以及它要不要共用上下文、跑在一個分叉裡，還是透過一個工具結果回傳。

### 上下文的生命週期由宿主決定

啟用之後，技能本體可能留在對話裡、在壓縮時被摘要，或跑在一個被委派的上下文裡。工具許可可能只撐一個回合，而指示活得更久。一個子代理可能收到這項技能，卻沒有收到父代理的完整歷史。

不要寫一項依賴看不見的存活期假設的技能。把持久的產出放進檔案或有型別的狀態、讓重新進入是安全的，並且說清楚被中斷之後有什麼必須重新載入。

```markdown
On resume, read `artifacts/release-readiness.json` if it exists.
Revalidate the candidate commit before continuing.
Do not repeat an external write whose idempotency key is already recorded.
```

## 動手實作

`code/main.py` 把政策與路由實作成分開的轉接器。

這個模型包含：

- `Actor`，代表人類、模型、自主代理、應用程式、技能與框架這些呼叫方；
- `SkillMetadata`，代表路由身分；
- `InvocationPolicy`，代表那個人／模型矩陣；
- `InvocationRequest` 與 `InvocationDecision`，代表可被追蹤的輸入與結果；
- `CorePolicyAdapter`，代表沒有任何宿主擴充的可攜行為；
- `ExtensionPolicyAdapter`，代表被認得的執行環境欄位；
- `build_invocation_matrix(policy)`，產出那個 2x2 視圖；
- `route_request(skills, request, adapter)`，在相關性排名、選擇與拒絕之前先做資格過濾。

跑它：

```bash
cd phases/13-tools-and-protocols/25-skill-invocation-and-routing
python3 code/main.py
python3 -m unittest discover -s code/tests -v
```

這支示範會印出一個矩陣，以及明確的人類、隱含的模型、自主代理、應用程式、技能組合與框架這幾個通道的決策。它那個擴充轉接器的結果，會展示一個被擋掉的字面最高分在有資格的替代者被排名之前就先被移除。它也包含確切名稱的允許清單。不需要任何模型 API。這個決定性的路由器存在的目的是讓政策邊界可以被檢視，不是主張字面比對能重現生產環境的模型路由。

### 為什麼核心轉接器與擴充轉接器是分開的

如果一個解析器替每一個看到的 frontmatter 欄位都賦予意義，它就會默默把執行環境的慣例升級成一個假的標準。把轉接器分開，會逼呼叫方指名現在生效的是哪一套宿主語意。

`CorePolicyAdapter` 只用應用程式提供的政策。`ExtensionPolicyAdapter` 認得一組明確列出的宿主欄位，並記下是哪一個欄位改變了決策。

## 框架應用

在發布一項技能之前，先寫下一份叫用契約：

```yaml
actors:
  human: allow
  model: deny
  application: allow
  skill: deny
explicit_name: release-readiness
arguments:
  candidate: required
  publish: fixed_false
ambiguity: ask_user
missing_dependency: stop
context:
  durable_state: artifacts/release-readiness.json
  max_composition_depth: 2
```

這份契約是給轉接器與測試看的設計文件。除非有標準明確採用它，它就不是可攜的 `SKILL.md` frontmatter。

## 產出交付

本單元會產出 `skill-invocation-router` 套組。它包含一份叫用模型的參考資料、一份範例宿主政策，以及一個不執行任何東西的 CLI，能評估一個人類、模型、自主代理、應用程式、技能組合或框架的請求，並回傳一份帶通道、轉接器、分數與理由的 JSON 決策。

那個單一請求的 CLI 是一支政策探針，不是一次完整的觸發評估。要算出混淆計數、精確率、召回率與重跑穩定性，請用第 27 課那套有標註的正例與差一點案例的設計。

## 練習

1. 把人／模型矩陣的四列都做出來，並替每一列寫一個合理的使用情境。
2. 替 `CorePolicyAdapter` 加上「只給應用程式」的啟用。證明人類與模型呼叫方仍然被拒絕。
3. 替一項部署技能寫十個差一點的案例。每一個提示詞都必須跟這項技能共用詞彙，但屬於另一條流程。
4. 在前兩名路由分數之間加上一個歧義邊際。當邊際太小時回傳 `ask`。
5. 替技能對技能的請求加上最大組合深度，並偵測出一個兩項技能的循環。
6. 把同一組有標註的測試集分別跑過核心與擴充轉接器。解釋每一個變掉的決策。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|---|---|---|
| 明確叫用 | 「斜線指令」 | 一個行動者直接給出技能身分，並且仍然受政策約束 |
| 隱含叫用 | 「模型自己選」 | 路由器依任務脈絡，從有資格的目錄中繼資料裡選出一個 |
| 使用者可叫用 | 「人可以用它」 | 一個宿主專屬的選單或直接叫用性質，不是核心欄位 |
| 模型可叫用 | 「代理可以用它」 | 在宿主政策之下，具備被隱含選擇的資格 |
| 叫用轉接器 | 「frontmatter 解析器」 | 把某個宿主的欄位與 API 對映到一個宣告好的政策模型的程式碼 |
| 差一點的案例 | 「困難負例」 | 一個不該觸發、但長得很像這項技能預期輸入的請求 |
| 棄權 | 「沒有選任何技能」 | 在證據缺漏或有歧義時，一個刻意做出的路由結果 |

## 延伸閱讀

- [Optimizing skill descriptions](https://agentskills.io/skill-creation/optimizing-descriptions)，正向觸發、具體性與評估。
- [Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills)，觸發與輸出評估的設計。
- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)，Codex 現行的明確與隱含叫用控制。
- [Claude Code skills](https://code.claude.com/docs/en/skills)，某一個宿主的 `user-invocable`、`disable-model-invocation`、引數與委派上下文。
