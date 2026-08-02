# 自主寫程式代理的版圖（2026）

> SWE-bench Verified 在不到三年內從 4% 走到 80.9%。同一個 Claude Sonnet 4.5 在 SWE-agent v1 上是 43.2%，在 Cline autonomous 上是 59.8% —— 圍繞模型的鷹架，如今跟模型本身一樣要緊。OpenHands（前身 OpenDevin）是最活躍的 MIT 授權平台，而它的 CodeAct 迴圈是在沙箱中直接執行 Python 行動，而不是走 JSON 工具呼叫。這些頭條數字藏著一個方法論問題：SWE-bench Verified 的 500 項任務中有 161 項只需要改 1–2 行，而同一批前沿模型在 SWE-bench Pro（改 10 行以上的任務）上只有 23–59%。

**類型：** 學習
**程式語言：** Python (stdlib, CodeAct vs JSON tool-call comparison)
**先修單元：** 階段 14 · 07（工具使用）、階段 15 · 01（長時程代理）
**時間：** 約 45 分鐘

## 問題所在

「哪個寫程式代理最好」是錯的問題。對的問題是：在一個與我的工作相符的任務分布上、配上我會在生產環境跑的鷹架，我得到的端到端可靠度是多少？

2022 到 2026 年間，這個領域學到鷹架 —— 檢索層、規劃器、沙箱、編輯—查證迴圈、回饋格式 —— 是承重的。Claude Sonnet 4.5 在 SWE-agent v1 上於 SWE-bench Verified 拿 43.2%；同一個模型放進 Cline 的自主鷹架則拿 59.8%。絕對值差 16.6 分，權重完全一樣。基礎模型是一個組件；那個迴圈才是產品。

伴隨而來的問題是：基準飽和會把回歸藏起來。SWE-bench Verified 已接近飽和，而那條容易任務的尾巴（500 項中有 161 項只要改 ≤2 行）把頂尖分數往上拉。真實世界的品質，用 SWE-bench Pro（改 10 行以上）這類分布來量比較好，在那裡同一批領先者仍然只有 23–59%。

## 核心概念

### 一段話講完 SWE-bench

SWE-bench（Jimenez 等人）拿真實的 GitHub issue 與其基準真值修補，要求代理產出一份能讓測試套件通過的修補。SWE-bench Verified（OpenAI，2024）是一個由人策展的 500 項任務子集，把語意含糊與壞掉的任務移除了。SWE-bench Pro 是更難的後繼者 —— 需要改 10 行以上的任務，當前前沿代理在上面是 23–59%。

### 2022 → 2026 那條曲線實際上顯示了什麼

- **2022**：研究模型在原始 SWE-bench 上約 4%。
- **2024**：GPT-4 加 Devin 式鷹架約 14%；SWE-agent 約 12%。
- **2025**：Claude 3.5/3.7 Sonnet 在 Aider 與 SWE-agent 裡推進到 40–55% 的區間。
- **2026**：Claude Sonnet 4.5 與前沿競爭者在 SWE-bench Verified 上達到 70–80%+。Epoch AI 的排行榜即時追蹤這件事。

這條斜率來自三個複利的來源：更好的基礎模型、更好的鷹架（CodeAct、反思、查證器迴圈），以及更好的基準（Verified 移除了雜訊）。

### CodeAct vs JSON 工具呼叫

OpenHands（All-Hands-AI，arXiv:2407.16741，前身 OpenDevin）下了一個特定的架構賭注：模型不是吐出讓宿主解碼並執行的 JSON 工具呼叫，而是吐出 Python 程式碼，由一個 Jupyter 式的核心在沙箱裡跑它。代理可以在同一個行動裡遍歷檔案、串接工具，並接住自己的例外。

取捨：

- **JSON 工具呼叫**：每個行動就是一輪；容易稽核；可組合性有限；預設安全，因為每次呼叫都會經過一個明寫的驗證器。
- **CodeAct**：一個行動可以是一整支程式；可組合；需要一個硬化過的沙箱（OpenHands 用 Docker 隔離）；失敗模式包含沙箱執行環境所允許的任何事。

兩種架構都在生產環境中。CodeAct 在開放平台上占主導（OpenHands、smolagents）。JSON 工具呼叫在託管服務中仍占主導（Anthropic Managed Agents、OpenAI Assistants），因為供應商掌控那個執行器。

### 2026 年版圖中的各種鷹架

| 鷹架 | 授權 | 執行模型 | 值得注意的性質 |
|---|---|---|---|
| OpenHands（OpenDevin） | MIT | Docker 裡的 CodeAct | 最活躍的開放平台；事件串流可重播 |
| SWE-agent | MIT | Agent-Computer Interface（ACI） | 第一個端到端的 SWE-bench 鷹架 |
| Aider | Apache-2 | 在本地儲存庫以 diff 編輯 | 極簡鷹架，回歸穩定性強 |
| Cline | Apache-2 | 帶工具政策的 VS Code 代理 | 在 Sonnet 4.5 上分數最高的開放鷹架 |
| Devin（Cognition） | 專有 | 託管 VM + 規劃器 | 開創「AI 軟體工程師」這個產品類別 |
| Claude Code | 專有 | 權限模式 + 例行程序 | 第 10 課詳細介紹那個代理迴圈 |

### 為什麼鷹架會主導

一趟寫程式的執行是一條長時程軌跡（第 1 課）。可靠度會跨步複利。鷹架能買到分數的三個地方：

1. **檢索**：找到該讀的那些檔案，是那個無聲的瓶頸。SWE-agent 的 ACI、OpenHands 的檔案索引，以及 Aider 的 repo-map 都在攻這一塊。
2. **查證器迴圈**：跑測試、讀堆疊追蹤、再試一次，在 SWE-bench 上是 10 分以上的差距。
3. **失敗圍堵**：一個出錯就回捲的沙箱，能防止損害複利。同一個模型有沒有查證器迴圈，看起來像兩個不同的產品。

### 基準飽和與真實分布

OpenHands 的作者與 Epoch AI 都標示了 SWE-bench Verified 有一條容易的尾巴：500 項任務中有 161 項只需改 1–2 行。高分有一部分是被這條尾巴推上去的。SWE-bench Pro 限縮到改 10 行以上，即使是前沿系統，分數也回到 23–59% 的區間。你的生產分布幾乎肯定比較接近 Pro，而不是 Verified。

對選代理的意涵：拿你自己臭蟲待辦清單中類 Pro 的子集去跑。要緊的分數，是在那些足以代表你實際出貨內容的任務上的分數。

## 框架應用

`code/main.py` 在一個固定的迷你任務分布上比較兩個玩具代理鷹架：

1. 一個 **JSON 工具呼叫** 鷹架，每輪一個行動。
2. 一個 **CodeAct** 鷹架，每個行動可以吐出一小段 Python。

兩者都用一個樁「模型」（決定性規則），好讓比較把鷹架從模型品質中隔離出來。輸出顯示 CodeAct 鷹架用更少輪次解掉更多任務，代價是每個行動的爆炸半徑更大。

## 產出交付

`outputs/skill-scaffold-audit.md` 幫你在採用之前稽核一個被提議的寫程式代理鷹架：檢索品質、有沒有查證器、沙箱隔離，以及基準與分布的契合度。

## 練習

1. 跑 `code/main.py`。在同一組任務上，各鷹架各花幾輪？各自每個行動的爆炸半徑是多少？

2. 讀 OpenHands 論文（arXiv:2407.16741）。論文主張 CodeAct 在複雜任務上勝過 JSON 工具呼叫。找出論文自己承認的一種失敗模式，並用一句話說明那種模式在生產環境何時會占主導。

3. 從你的臭蟲待辦清單中挑一項需要跨兩個檔案改 10 行以上的任務。估算一個前沿模型在 (a) JSON 工具呼叫與 (b) CodeAct 之下的端到端成功機率。替那個落差辯護。

4. SWE-bench Verified 有 161 項單檔、1–2 行的任務。造一個把它們排除掉的分數。排行榜怎麼洗牌？

5. 讀〈Introducing SWE-bench Verified〉（OpenAI）。解釋它用來移除語意含糊任務的那套具體方法論，並說出一個那份策展會漏掉的類別。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際是什麼意思 |
|---|---|---|
| SWE-bench | 「寫程式的基準」 | 帶基準真值修補與測試套件的真實 GitHub issue |
| SWE-bench Verified | 「清理過的子集」 | 500 項由人策展的任務，容易的尾巴仍在 |
| SWE-bench Pro | 「更難的子集」 | 改 10 行以上；前沿落在 23–59% |
| CodeAct | 「程式碼即行動」 | 代理吐出 Python；Jupyter 式核心在沙箱中執行 |
| JSON 工具呼叫 | 「函數呼叫」 | 每個行動都是執行前先驗證的結構化 JSON 酬載 |
| 鷹架 | 「代理框架」 | 圍繞基礎模型的檢索 + 規劃器 + 執行器 + 查證器迴圈 |
| ACI（Agent-Computer Interface） | 「SWE-agent 的那套格式」 | 為 LLM 人體工學而非人類 shell 設計的指令集 |
| 查證器迴圈 | 「測試後重試」 | 跑測試、讀輸出、修訂修補；模型之外最大的可靠度收穫 |

## 延伸閱讀

- [Jimenez et al. — SWE-bench](https://www.swebench.com/) —— 那個原始基準與方法論。
- [OpenAI — Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) —— 那個策展子集是怎麼做出來的。
- [Wang et al. — OpenHands: An Open Platform for AI Software Developers](https://arxiv.org/abs/2407.16741) —— CodeAct 架構與事件串流設計。
- [Epoch AI — SWE-bench leaderboard](https://epoch.ai/benchmarks) —— 即時追蹤的分數。
- [Anthropic — Measuring agent autonomy](https://www.anthropic.com/research/measuring-agent-autonomy) —— 長時程寫程式代理可靠度的框架。
