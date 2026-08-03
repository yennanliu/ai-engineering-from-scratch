# 瀏覽器代理與長時程網頁任務

> ChatGPT agent（2025 年 7 月）把 Operator 與 deep research 併成單一個瀏覽器／終端機代理，並在 BrowseComp 上以 68.9% 創下 SOTA。OpenAI 在 2025 年 8 月 31 日關掉了 Operator —— 產品層的整併。Anthropic 併購 Vercept 之後，把 Claude Sonnet 在 OSWorld 上的成績從 15% 以下推到 72.5%。WebArena-Verified（ServiceNow，ICLR 2026）修掉了原始 WebArena 中 11.3 個百分點的偽陰性率，並出貨了 258 項任務的 Hard 子集。這些數字都是真的。攻擊面也是：OpenAI 的準備度負責人公開表示，對瀏覽器代理的間接提示詞注入「不是一個可以被完全修補的臭蟲」。2025–2026 年有記錄的攻擊：Tainted Memories（Atlas CSRF）、HashJack（Cato Networks），以及 Perplexity Comet 中的一鍵劫持。

**類型：** 學習
**程式語言：** Python (stdlib, indirect prompt-injection attack surface model)
**先修單元：** 階段 15 · 10（權限模式）、階段 15 · 01（長時程代理）
**時間：** 約 45 分鐘

## 問題所在

瀏覽器代理是一個「讀不可信內容、又採取有後果行動」的長時程代理。代理造訪的每個頁面，都是一份使用者沒有寫的輸入。每個頁面上的每張表單，都是一條潛在的命令通道。2025–2026 年的攻擊語料顯示這不是假想：Tainted Memories 讓攻擊者透過一個特製頁面，把惡意指令綁進代理的記憶；HashJack 把命令藏在代理造訪的 URL 片段裡；Perplexity Comet 的劫持只要一次點擊就中。

防禦這一面的圖景令人不安。OpenAI 的準備度負責人把大家不敢說的話說白了：間接提示詞注入「不是一個可以被完全修補的臭蟲」。原因在於這種攻擊住在代理的「閱讀對行動」邊界上，而那條邊界在架構上就是模糊的 —— 原則上，模型讀到的每一個詞元都可能被讀成一道指令。

這一課點名那片攻擊面、點名基準版圖（BrowseComp、OSWorld、WebArena-Verified），並模型化一個最小的間接提示詞注入情境，好讓你在第 14 與 18 課推敲真正的防禦。

## 核心概念

### 2026 年的版圖，一個系統一段話

**ChatGPT agent（OpenAI）。** 2025 年 7 月推出。整合 Operator（瀏覽）與 Deep Research（多小時研究）。2025 年 8 月 31 日關閉獨立的 Operator。在 BrowseComp 上以 68.9% 為 SOTA；在 OSWorld 與 WebArena-Verified 上數字也很強。

**Claude Sonnet + Vercept（Anthropic）。** Anthropic 併購 Vercept 聚焦在 computer-use 能力上。把 Claude Sonnet 在 OSWorld 上從 <15% 推到 72.5%。Claude Computer Use 以工具 API 的形式出貨。

**Gemini 3 Pro 加 Browser Use（DeepMind）。** Browser Use 的整合出貨了 computer-use 控制項；FSF v3（2026 年 4 月，第 20 課）特別追蹤 ML 研發領域中的自主性。

**WebArena-Verified（ServiceNow，ICLR 2026）。** 修掉一個有充分記錄的問題：原始 WebArena 有約 11.3% 的偽陰性率（被標為失敗、其實已解決的任務）。Verified 版本以人策展的成功判準重新批改，並加上一個 258 項任務的 Hard 子集（ICLR 2026 論文，openreview.net/forum?id=94tlGxmqkN）。

### BrowseComp、OSWorld 與 WebArena 的對照

| 基準 | 它量什麼 | 時程 |
|---|---|---|
| BrowseComp | 在時間壓力下於開放網路上找出特定事實 | 幾分鐘 |
| OSWorld | 代理操作一整台桌機（滑鼠、鍵盤、shell） | 數十分鐘 |
| WebArena-Verified | 在模擬網站上的交易型網頁任務 | 幾分鐘 |
| Hard 子集 | 帶多頁狀態轉移的 WebArena-Verified 任務 | 數十分鐘 |

不同的軸。高 BrowseComp 分數說的是代理找得到事實；它沒說代理訂得了機票。OSWorld 的分數比較接近「它在我的桌機上行不行」。WebArena-Verified 比較接近「它跑不跑得完一條流程」。任何生產決策都需要那個與任務分布相符的基準。

### 點名那片攻擊面

1. **間接提示詞注入。** 不可信的頁面內容含有指令。代理讀了它們。代理執行了它們。公開例子：2024 年 Kai Greshake 等人、2025 年的 Tainted Memories 論文、2026 年的 HashJack（Cato Networks）。
2. **URL 片段／查詢字串注入。** 被抓取 URL 的 `#fragment` 或查詢字串裡含有命令。從不被可見地渲染出來；卻仍在代理的脈絡裡。
3. **記憶綁定攻擊。** 頁面指示代理寫下一則持久記憶（第 12 課涵蓋持久狀態）。下一個工作階段，那則記憶就在沒有可見觸發的情況下引爆酬載。
4. **對已驗證工作階段的 CSRF 式攻擊。** Tainted Memories 這一類：代理在某處已登入；攻擊者的頁面發出會改變狀態的請求，而代理帶著使用者的 cookie 去執行它們。
5. **一鍵劫持。** 一顆視覺上人畜無害的按鈕，載著一段代理會跟隨的酬載。Comet 那一類。
6. **代理宿主表面上的 Content-Security-Policy 漏洞。** 渲染層與工具層本身就可能是攻擊向量；瀏覽器套在瀏覽器代理裡的這整個堆疊很寬。

### 為什麼「無法完全修補」

這種攻擊與代理的能力同構。代理必須讀不可信內容才能做它的工作。代理讀的任何內容都可能含有指令。代理跟隨的任何指令，都可能與使用者真正的請求失準。各種防禦（信任邊界、分類器、工具允許清單、對有後果行動的 HITL）提高攻擊的成本、縮小它的爆炸半徑。它們並不封閉這一整類。

這跟 Löb 定理（第 8 課）是同一種推理樣式：代理沒辦法證明下一個詞元是安全的；它只能架起一套讓不安全詞元更容易被偵測的系統。

### 真的出得了貨的防禦姿態

- **讀／寫邊界。** 讀取永遠不具後果。寫入（送出表單、發布內容、呼叫有副作用的工具）在發起內容來自信任邊界之外時，需要一次新的人工核准。
- **逐任務的工具允許清單。** 代理可以瀏覽；除非該工具被明確為此任務啟用，否則它發不起電匯。第 13 課涵蓋預算。
- **工作階段隔離。** 瀏覽器代理的工作階段只用範圍受限的憑證跑。沒有生產環境認證、沒有私人信箱。每一次 HTTP 請求的日誌都保留供稽核。
- **內容淨化器。** 抓回來的 HTML 在被串進模型脈絡之前，先剝掉已知有害的樣式。（減少容易的攻擊；擋不住精巧的酬載。）
- **對有後果的行動做 HITL。** 先提議後提交的模式（第 15 課）。
- **記憶上的金絲雀詞元。** 若某則記憶被引爆，使用者看得到（第 14 課）。

```figure
injection-boundary
```

## 框架應用

`code/main.py` 針對三個合成頁面模型化一次很小的瀏覽器代理執行。一頁是良性的，一頁在可見文字中帶一團直接提示詞注入，一頁帶 URL 片段注入（不可見，但在代理的脈絡裡）。這支腳本顯示 (a) 一個天真的代理會做什麼、(b) 讀／寫邊界抓得到什麼、(c) 淨化器抓得到什麼、(d) 兩者都抓不到什麼。

## 產出交付

`outputs/skill-browser-agent-trust-boundary.md` 替一次被提議的瀏覽器代理部署劃定範圍：它碰到哪些信任區、它被授權寫什麼，以及第一次執行之前必須就位的防禦有哪些。

## 練習

1. 跑 `code/main.py`。指認出哪個攻擊是淨化器抓得到、讀／寫邊界抓不到的，以及哪個攻擊只有讀／寫邊界抓得到。

2. 擴充淨化器，讓它偵測某一類 HashJack 式的 URL 片段注入。在帶有合法片段的良性 URL 上量偽陽性率。

3. 挑一個你熟悉的真實瀏覽器代理工作流（例如「訂機票」）。列出每一次讀與每一次寫。標出哪些寫入需要 HITL，以及為什麼。

4. 讀 WebArena-Verified 的 ICLR 2026 論文。指認出原始 WebArena 評分不可靠的一類任務，並解釋 Verified 子集怎麼解決它。

5. 替一個瀏覽器代理情境設計一個記憶金絲雀。你會存什麼、存在哪，以及什麼會觸發警報？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|---|---|---|
| 間接提示詞注入 | 「壞掉的頁面文字」 | 代理讀到的頁面中，不可信內容含有代理會執行的指令 |
| Tainted Memories | 「記憶攻擊」 | 代理把攻擊者提供的指令寫進持久記憶；下一個工作階段被觸發 |
| HashJack | 「URL 片段攻擊」 | 藏在 URL 片段／查詢字串中的酬載進了代理脈絡，卻沒有被可見地渲染 |
| 一鍵劫持 | 「壞按鈕」 | 一個可見的能供性載著代理會執行的後續酬載 |
| BrowseComp | 「網頁搜尋基準」 | 在開放網路上找特定事實；分鐘級的時程 |
| OSWorld | 「桌面基準」 | 完整的作業系統操控；多步驟 GUI 任務 |
| WebArena-Verified | 「修好的網頁任務基準」 | ServiceNow 重新批改過的 WebArena，帶 Hard 子集 |
| 讀／寫邊界 | 「副作用閘門」 | 讀取永不具後果；內容若在信任之外，寫入需要新的核准 |

## 延伸閱讀

- [OpenAI — Introducing ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/) —— Operator 與 deep research 的合併；BrowseComp 的 SOTA。
- [OpenAI — Computer-Using Agent](https://openai.com/index/computer-using-agent/) —— Operator 的血脈，以及後來成為 ChatGPT agent 的那個架構。
- [Zhou et al. — WebArena](https://webarena.dev/) —— 那個原始基準。
- [WebArena-Verified (OpenReview)](https://openreview.net/forum?id=94tlGxmqkN) —— ICLR 2026 的修正子集論文。
- [Anthropic — Measuring agent autonomy in practice](https://www.anthropic.com/research/measuring-agent-autonomy) —— 含針對 computer-use 代理的攻擊面討論。
