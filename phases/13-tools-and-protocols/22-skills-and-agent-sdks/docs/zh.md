# 代理技能：可攜的契約與執行環境邊界

> 一項技能不是換了個好檔名的長提示詞。它是一個可被發現的套件，裝著指示、資源與可執行的輔助程式，並透過一份執行環境契約進入代理的上下文。

**類型：** 實作
**程式語言：** Python (stdlib)
**先修單元：** 階段 13 · 01（工具介面）、階段 13 · 05（工具 schema 設計）
**時間：** 約 90 分鐘

## 學習目標

- 定義什麼是代理技能，並且不把它跟提示詞、儲存庫指示、工具、掛鉤、子代理或外掛混為一談。
- 讀懂可攜的 `SKILL.md` 契約，並把它跟執行環境專屬的擴充分開。
- 把發現、選擇、啟用、資源載入、工具使用與驗證，說明成各自獨立的生命週期階段。
- 在執行環境把一項技能放進代理的目錄之前先驗證這個技能套件。
- 針對一件具體任務，在技能、MCP 工具、掛鉤、子代理或普通程式碼之間做出選擇。

## 十分鐘先跑出結果

先做這件事，再看長篇解釋。你會建立一個小技能、把完整的審查器套組安裝進一個真實的代理宿主、叫用它、驗證結果，然後移除它。這會用一個看得見的結果證明整條生命週期。

### 真實宿主實驗的事前檢查

真實宿主的檢查點需要 Node.js、`npx`、Python 3、一個你選定的支援技能的宿主，以及你在安裝程式裡所選的專案或使用者範圍的寫入權限。先確認本機指令：

```bash
node --version
npx --version
python3 --version
```

在安裝之前先決定你要用哪個宿主與哪個範圍。如果其中任何一項無法取得，就到網站上讀這一課，或改做下面手動打包的練習。那條退路教得到契約，但它證明不了宿主的發現、叫用、隨附腳本的執行或解除安裝的行為。把那幾項觀察標記為待確認。

### 1. 從一個空的工作目錄開始

在任何你用來放學習素材的上層目錄裡執行這些指令：

```bash
mkdir -p agent-skills-first-run
cd agent-skills-first-run
TARGET_ROOT="$(pwd -P)"
printf 'TARGET_ROOT=%s\n' "$TARGET_ROOT"
ls -A
```

最後那個指令應該什麼都不印。如果它印出檔案，就換一個空目錄，讓這次審查有一條清楚的邊界。

為你的第一個技能建一個目錄：

```bash
mkdir -p my-first-skill
```

用這份內容建立 `my-first-skill/SKILL.md`：

```markdown
---
name: my-first-skill
description: Turn rough meeting notes into a compact decision record when the user asks to capture a technical decision.
---

# Decision record

Extract the decision, context, alternatives, owner, and next review date.
If the notes do not contain a decision, ask one clarifying question instead
of inventing one.
```

確認你是在原本想放的那個目錄裡建立這個檔案：

```bash
test -f my-first-skill/SKILL.md
```

沒有輸出、離開碼為 0，就表示檔案存在。

### 2. 安裝完整的審查器套組

留在 `agent-skills-first-run` 裡，然後執行：

```bash
npx skills add rohitg00/ai-engineering-from-scratch --skill skill-contract-reviewer --full-depth
```

選擇你正在用的代理宿主與範圍。安裝程式應該會列出 `skill-contract-reviewer` 以及它寫入的目的地。`--full-depth` 是必要的，因為這一課的技能是一個嵌套的套組，帶有參考資料、一支腳本與一份素材。

把 `SKILL_ROOT` 設成安裝程式回報的那個絕對路徑目錄。它必須是內含已安裝 `SKILL.md` 的那個目錄，不是課程原始碼目錄，也不是目前的工作區：

```bash
# Replace the placeholder with the destination printed by the installer.
SKILL_ROOT="$(cd "/absolute/path/to/skill-contract-reviewer" && pwd -P)"
test -f "$SKILL_ROOT/SKILL.md"
printf 'SKILL_ROOT=%s\n' "$SKILL_ROOT"
```

如果代理工作階段本來就開著，開一個新的工作階段，或用那個宿主的技能重新掃描指令。不要假設每個宿主都會熱重載自己的目錄。

### 3. 明確叫用它

在裝好的代理裡，以 `agent-skills-first-run` 作為工作目錄，用那個宿主支援的語法：

| 宿主 | 明確叫用 |
|---|---|
| Codex | `skill-contract-reviewer`，或從 `/skills` 裡選它，然後給出審查請求 |
| Claude Code | `/skill-contract-reviewer` 後面接審查請求 |
| 可攜的退路 | `Use skill-contract-reviewer to review the target package.` |

在請求裡使用剛才印出來的 `SKILL_ROOT` 與 `TARGET_ROOT` 絕對路徑值。要求宿主在執行前先展開它們，並把解析後的確切指令顯示出來，而不是一個依賴行程工作目錄的指令：

```text
Use skill-contract-reviewer to review <TARGET_ROOT>/my-first-skill. The installed bundle root is <SKILL_ROOT>. Run python3 <SKILL_ROOT>/scripts/check_skill.py <TARGET_ROOT>/my-first-skill. Before running it, show the fully resolved argv. Return the validation report, selected primitives, and one sentence for each selection. Include the resolved script path, resolved target path, cwd, argv, and exit code as execution evidence.
```

解析後的指令應該長成這個樣子，不留任何佔位符：

```bash
python3 "/absolute/install/path/skill-contract-reviewer/scripts/check_skill.py" \
  "/absolute/workspace/path/agent-skills-first-run/my-first-skill"
```

一個成功的結果會同時具備三個性質：

1. 宿主依名稱找到 `skill-contract-reviewer`。
2. 審查器讀取這個套件的契約，並執行它隨附的驗證器。
3. 回應裡包含一份驗證報告，對這個範例沒有任何結構性錯誤，外加一份有理由的原語選擇。

執行證據還必須指出腳本路徑、目標路徑、cwd、確切的引數向量與離開碼。一份很流暢但缺這些欄位的報告，證明不了那支已安裝的隨附腳本真的跑過。

如果宿主回報這個技能不存在，請確認安裝目的地、重新掃描或重啟一次，然後重試那個明確請求。不要為了掩蓋安裝失敗而去改寫技能的 description。

### 4. 試探隱含選擇

開一個全新的代理回合，輸入同一件任務，但不指名這個技能：

```text
Review <TARGET_ROOT>/my-first-skill as a reusable agent package and tell me whether its package contract is valid.
```

如果這個宿主會揭露它選中的技能，記錄它是否選了 `skill-contract-reviewer`。如果這個宿主不揭露路由結果，就把隱含選擇標記為未驗證。明確叫用才是那條可攜的退路。

### 5. 清理

只移除裝好的審查器套組：

```bash
npx skills remove skill-contract-reviewer
```

選擇安裝時用的同一個宿主與同一個範圍。在重新掃描或開新工作階段之後，對 `skill-contract-reviewer` 的明確請求應該回報它不存在。把 `my-first-skill` 留給後面幾課，或在你走完這條路線之後把實驗目錄刪掉。

## 問題所在

假設你的團隊有一套可靠的發布流程。它會找出已合併的變更、檢查遷移說明、更新變更日誌、跑一個打包指令，並產出一份審查清單。

把那套流程放進單一段提示詞，很好貼上，卻很難維運。這段提示詞沒有穩定的身分、沒有發現規則、沒有資源邊界、沒有可測試的套件形狀，也回答不出幾個基本問題：誰可以叫用它？模型什麼時候該選它？它能跑哪些腳本？哪些檔案是可信的？上下文被壓縮時有什麼會留下來？

反過來的錯誤，是把每一份可重用的指示都當成技能。儲存庫慣例、決定性的自動化、外部工具、事件掛鉤與被委派的代理，解的是不同的問題。把它們全部塞進 `SKILL.md`，做出來的目錄看起來可攜，實際上卻依賴某一個宿主未寫進文件的行為。

第一件工程工作是分類。先決定這個產物是什麼，再決定怎麼把它打包。

## 核心概念

### 技能編碼的是程序性知識

一項代理技能是一個目錄，它的進入點是 `SKILL.md`。這個進入檔含有 YAML frontmatter，後面接 Markdown 指示。這個目錄還可以裝參考資料、腳本與素材。

```figure
skill-package-anatomy
```

可部署的單位是這個目錄，不是那個 Markdown 檔本身。一份被抄走、卻少了參考資料的 `SKILL.md`，就算 frontmatter 解析得過，也是一個壞掉的套件。

### 相鄰的那些抽象

| 產物 | 主要職責 | 何時被載入或執行 | 它不該假扮什麼 |
|---|---|---|---|
| 提示詞 | 塑造單一次模型互動 | 由應用程式或使用者夾帶進去 | 一個帶資源、有版本的套件 |
| 儲存庫指示 | 說明某一份程式碼庫的常設規則 | 寫程式的執行環境進入那個範圍時 | 一套可重用的任務流程 |
| 代理技能 | 提供可重用的程序性知識 | 明確或隱含的啟用 | 一道硬性的授權邊界 |
| MCP 工具 | 揭露一項有型別的遠端能力 | 模型或應用程式呼叫它時 | 一份詳細的作業程序 |
| 掛鉤 | 在事件發生時執行決定性的邏輯 | 宣告的那個事件發生時 | 機率性的模型路由 |
| 子代理 | 用獨立的上下文與狀態去委派工作 | 一個協調者建立或呼叫它時 | 一份靜態的指示套組 |
| 外掛 | 散布一份更大的執行環境擴充 | 宿主安裝或啟用它時 | 可攜的技能契約本身 |
| 學到的技能庫 | 儲存從經驗中發現的行為 | 一個策略取回先前的程式或軌跡時 | 一個符合標準的 `SKILL.md` 套件 |

一項發布技能可以告訴代理怎麼檢視一次發布。一台 MCP 伺服器可以揭露發布登錄。一個掛鉤可以禁止直接推送。一個子代理可以獨立稽核候選版本。這些零件能組起來，是因為它們各自守住不同的職責。

### 「技能」這個詞指的是兩件不同的事

研究型系統有時會把一個學到的程式、一條成功的軌跡，或一段環境專屬的策略片段叫做技能。代理可以在探索過程中製造這些產物、依任務相似度取回它們、執行它們，並根據回饋修訂這個庫。階段 14 · 10 做的就是那種終身學習的庫。

這條迷你路線裡的代理技能不一樣。它是一個被撰寫出來的套件，帶有宣告好的檔案系統契約、目錄中繼資料、漸進揭露、由執行環境仲裁的叫用，以及由宿主控制的工具。它可以由代理生成或改良，但這個格式並不要求學習。

| 面向 | 代理技能套件 | 學到的技能庫 |
|---|---|---|
| 主要單位 | `SKILL.md` 目錄 | 程式、策略、軌跡或記憶紀錄 |
| 產生方式 | 撰寫、生成或策劃 | 通常是從環境經驗中發現的 |
| 選擇方式 | 目錄裡的 description 加上執行環境政策 | 對任務狀態做取回或套用策略 |
| 執行方式 | 模型照著指示做，並呼叫宿主工具 | 環境執行一段存起來的行為或程式產物 |
| 可攜性 | 套件契約可以跨相容的宿主 | 常綁在單一環境與動作空間上 |
| 評估方式 | 路由、產物、安全與宿主相容性 | 獎勵、成功率、遷移與庫的成長 |

這兩個想法都在打包可重用的能力。它們不該只因為共用一個名字，就共用實作上的主張。

### 可攜的核心

Agent Skills 規格要求兩個 frontmatter 欄位：

```yaml
---
name: release-readiness
description: Inspect a release candidate when the user asks whether a version is ready to publish.
---
```

`name` 是那個穩定的識別碼。它必須滿足規格的命名規則，並且跟上層目錄同名。`description` 同時是文件與路由中繼資料。它應該說出這個技能做什麼，以及什麼時候適用。

可攜的選配欄位有：

| 欄位 | 用途 | 可攜性註記 |
|---|---|---|
| `license` | 說明這個套件的授權條款 | 核心規格 |
| `compatibility` | 說明環境上的需求 | 核心規格 |
| `metadata` | 承載值為字串的擴充資料 | 核心規格 |
| `allowed-tools` | 建議預先核可的工具 | 實驗性；宿主支援程度不一 |

Markdown 本體裝的是作業指示。它應該定義流程、決策點、失敗行為，以及通往支援資源的直接路徑。

```markdown
# Release readiness

Use this workflow for a release candidate, not for ordinary development builds.

1. Read `references/release-policy.md`.
2. Run `python3 scripts/inspect_release.py --format json`.
3. Stop if the report contains a blocking failure.
4. Produce the checklist from `assets/release-checklist.md`.
5. Ask for approval before any publish or tag action.
```

### 執行環境擴充是第二層

有些宿主接受額外的 frontmatter 或隨附的設定。那些欄位可以很有用，但它們不會自動可攜。

| 行為 | 宿主擴充的例子 | 屬於可攜核心？ |
|---|---|:---:|
| 把技能從模型路由裡藏起來，但保留使用者直接叫用 | `disable-model-invocation` | 否 |
| 把技能從使用者的指令選單裡藏起來，但允許模型路由 | `user-invocable` | 否 |
| 在指令選單裡顯示引數說明 | `argument-hint` | 否 |
| 在被委派的上下文裡執行這個技能 | `context`、`agent` | 否 |
| 釘住模型或推理設定 | `model`、`effort` | 否 |
| 註冊生命週期自動化 | `hooks` | 否 |
| 在 Codex 裡關掉隱含叫用 | `agents/openai.yaml` 政策 | 否 |

把每一個擴充都當成一個轉接器。沒有它時核心流程也要成立，把退路寫進文件，並測試那個真的會吃它的宿主。一個執行環境可能忽略未知欄位、拒絕它，或保留它卻不實作那個行為。

### frontmatter 是會被執行的中繼資料

在技能本體被讀到之前，中繼資料就已經改變了系統行為。

- 一個格式不對的 `name` 可以讓發現失敗。
- 一段含糊的 `description` 可以把錯誤的請求路由過來。
- 一個只給人用的旗標可以把這個技能從模型的目錄裡拿掉。
- 一項工具許可可以改變宿主要不要來要權限。
- 一項上下文設定可以把執行搬到另一個代理工作階段裡。

像審查設定檔程式碼那樣審查 frontmatter。驗證它、給它版本，並把它的行為納進評估。

### 技能的生命週期

```figure
skill-runtime-lifecycle
```

每一支箭頭都是一道邊界，各有自己的失敗模式。

1. **發現** 在設定好的位置找出可能的套件。
2. **驗證** 在套件被公布到目錄之前，擋掉格式不對或不安全的套件。
3. **編目** 只揭露精簡的 `name` 與 `description`，不是整個套件。
4. **選擇** 判斷這個技能是否相關。
5. **啟用** 把本體載入模型看得見的上下文。
6. **揭露** 只在某個分支需要時才去讀參考資料或素材。
7. **執行** 在宿主的權限與隔離規則下使用宿主工具。
8. **驗證結果** 獨立於模型的說法去檢查產出的產物。

把這些階段壓成一團，會養出錯的心智模型。被發現的技能不等於已啟用。已啟用的技能不等於被授權做它描述的每一件事。一次被允許的工具呼叫，不能證明結果是對的。

### 技能與工具是互相垂直的

MCP 回答的是「這個應用程式能呼叫哪些能力，它們的 schema 是什麼？」技能回答的是「代理面對這一類任務該怎麼下手？」

```figure
skill-tool-orthogonality
```

技能可以指名一項工具，但真正的能力登錄是宿主擁有的。如果那項工具不存在，技能應該說出退路，或明確地失敗。它絕不該讓人以為指名一項能力就等於創造了它。

### 技能與儲存庫指示是不同的範圍

儲存庫指示描述的是你已經身在其中的那個環境：指令、慣例、產生出來的檔案，以及邊界。技能提供的是一套可重用的程序，用於可能出現在許多儲存庫裡的任務。

當兩者都適用時，當下的使用者請求與儲存庫規則會限制這個技能。一個通用的重構技能，不能推翻儲存庫裡「不准編輯產生檔案」的規則。

### 技能之間不會互相 import

一項技能可以指示代理去叫用另一項技能，但這不是語言層級的 import。第二項技能仍然要走一遍執行環境的發現、資格、啟用、權限與上下文處理。

把跨技能的依賴寫成看得見的流程邊：

```markdown
After producing the candidate changelog, invoke the `release-risk-review` skill.
Pass the candidate path and require a blocking or non-blocking verdict.
If that skill is unavailable, stop and report the missing dependency.
```

這讓依賴變成可測試的，也給宿主一個執行政策的機會。

## 動手實作

`code/main.py` 實作了一個小型、以標準為導向的驗證器，以及一個產物選擇器。它只用標準庫，所以每一條規則都看得見。

驗證器提供：

- `parse_frontmatter(text)`，把中繼資料跟本體分開。
- `validate_skill_text(text, directory_name, allowed_runtime_extensions=())`，檢查必填欄位、命名、未知擴充、本體是否存在，以及可攜性上的上限。
- `ValidationIssue` 與 `SkillReport`，回傳有結構的證據，而不是單一個不透明的布林值。
- `FrontmatterSyntaxError`，用於無法被安全解讀的輸入。

選擇器提供 `TaskShape` 與 `select_primitives(task)`。它把一件任務的需求映射到普通程式碼、儲存庫指示、技能、掛鉤、子代理或 MCP 工具。

跑這個實驗：

```bash
cd "$(git rev-parse --show-toplevel)"
cd phases/13-tools-and-protocols/22-skills-and-agent-sdks
python3 code/main.py
python3 -m unittest discover -s code/tests -v
```

這段指令需要一份本機 clone，而且必須從那份 clone 裡的任何位置出發，`git rev-parse --show-toplevel` 才解析得出儲存庫根目錄。

這支示範會為一個有效的可攜技能、一個帶宿主擴充的技能、一個無效的套件，以及好幾個任務形狀的決定，各印出一段 JSON。仔細看那些 issue 代碼。一個套件驗證器應該說明怎麼修好一份產物，而不是替作者亂猜。

### 驗證順序很重要

先驗便宜的結構事實，再驗更深的內容規則：

```figure
skill-validation-order
```

這個順序能防止次生的錯誤蓋掉第一個被打破的不變條件。

## 框架應用

在寫技能之前，先填完這張決策卡：

| 問題 | 如果是 | 可能的原語 |
|---|---|---|
| 這件事需要跨好幾個步驟、可重用的模型判斷嗎？ | 程序是穩定的，但決定會變 | 技能 |
| 這件事一定要在每次事件觸發時都發生嗎？ | 漏跑一次就不能接受 | 掛鉤或應用程式碼 |
| 模型需要一項有型別輸入的外部能力嗎？ | 這個操作住在模型上下文之外 | 工具或 MCP 伺服器 |
| 這件工作需要被隔離的上下文、狀態或所有權嗎？ | 由另一個工作者回傳一個有界的結果 | 子代理 |
| 這份指引只對某一個儲存庫成立嗎？ | 它描述的是本地的指令與限制 | 儲存庫指示 |
| 一次互動就夠了嗎？ | 不需要任何套件生命週期 | 提示詞 |

很多生產環境的流程會用到不只一列。這張卡能防止一份產物假裝自己提供了每一種性質。

## 產出交付

本單元會在 `outputs/` 底下產出 `skill-contract-reviewer` 套組。它包含：

- 一份可攜的 `SKILL.md`，用來審查一個被提出的技能套件；
- 針對可攜契約與原語選擇的參考清單；
- 一支決定性的驗證腳本；
- 涵蓋提示詞、技能、工具、掛鉤、普通程式碼與子代理的任務形狀測試素材。

安裝完整套組，不要只裝它的進入檔：

```bash
cd "$(git rev-parse --show-toplevel)"
python3 scripts/install_skills.py /tmp/aiefs-skills --phase 13 --type skill
```

課程安裝程式會回報每一個被複製的階段 13 技能，並寫出 `/tmp/aiefs-skills/manifest.json`。這個乾淨的目的地檢查的是套件形狀；上面那個先跑出結果的迴圈檢查的是發現與叫用。

接下來幾課會把每個生命週期階段挖深。第 24 課做發現與漸進揭露。第 25 課做叫用政策與路由。第 26 課把權限跟沙箱分開。第 27 課把整個套件變成一份被評估過的發布產物。

## 練習

1. 用 `TaskShape` 把你自己團隊的五套流程分類。凡是你選了不只一種原語的案例，都要說得出理由。
2. 加上邊界測試，證明一個 500 字元的 `compatibility` 值會過，而 501 字元的值會以規格錯誤失敗。
3. 把一個執行環境擴充加進允許清單。寫一個測試，證明同一份檔案仍然分得出來跟只用可攜核心的技能不同。
4. 把一段 400 行的提示詞拆成 `SKILL.md`、一份參考資料、一份腳本契約與一份輸出樣板。讓每個檔案只負責一種資訊。
5. 為一個引用了不存在 MCP 工具的技能設計失敗回應。不要默默換上一個權限更大的工具。
6. 審查一個現成的技能，把每一句話標成路由、程序、政策、參考指標或輸出契約。把不屬於那裡的東西搬走。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|---|---|---|
| 代理技能 | 「一段存起來的提示詞」 | 一個可被發現的目錄，裝著程序性指示與選配資源 |
| 可攜核心 | 「每個執行環境都有的欄位」 | 由 Agent Skills 規格定義的那份契約 |
| 執行環境擴充 | 「多出來的 frontmatter」 | 宿主專屬的設定，它的行為需要一個相容的轉接器 |
| 啟用 | 「這個技能跑了」 | 技能本體進入了模型看得見的上下文；執行可能還在後面 |
| 技能依賴 | 「import 另一個技能」 | 一條由執行環境仲裁的叫用邊，帶可用性與政策檢查 |
| 工具契約 | 「一份函式 schema」 | 一項能力的輸入、輸出、權限、副作用、錯誤與證據 |

## 延伸閱讀

- [Agent Skills specification](https://agentskills.io/specification)，可攜的目錄與 frontmatter 契約。
- [Agent Skills best practices](https://agentskills.io/skill-creation/best-practices)，範圍、指示與資源組織。
- [OpenAI: Build skills](https://learn.chatgpt.com/docs/build-skills)，Codex 目前的發現與叫用行為。
- [Claude Code skills](https://code.claude.com/docs/en/skills)，某一個執行環境的叫用、引數、工具與委派上下文擴充。
