# 遊戲上的強化學習 —— AlphaZero、MuZero，與 LLM 推理時代

> 1992 年：TD-Gammon 用純 TD 打敗了西洋雙陸棋的人類冠軍。2016 年：AlphaGo 擊敗李世乭。2017 年：AlphaZero 從零開始碾壓西洋棋、將棋與圍棋。2024 年：DeepSeek-R1 證明了同一套配方——把 PPO 換成 GRPO——在推理上一樣有效。遊戲是這個階段每一次突破背後的基準。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 9 · 05（DQN）、階段 9 · 08（PPO）、階段 9 · 09（RLHF）、階段 9 · 10（多代理強化學習）
**時間：** 約 120 分鐘

## 問題所在

遊戲擁有強化學習想要的一切。乾淨的獎勵（輸／贏）。無限的回合（自我對弈可以一直重置）。完美的模擬（遊戲*本身*就是模擬器）。離散或小型連續的動作空間。逼出對抗韌性的多代理結構。

而且每一次重大的強化學習突破，都是拿遊戲來驗證的。TD-Gammon（西洋雙陸棋，1992）。Atari-DQN（2013）。AlphaGo（2016）。AlphaZero（2017）。OpenAI Five（Dota 2，2019）。AlphaStar（星海爭霸 II，2019）。MuZero（學習型模型，2019）。AlphaTensor（矩陣乘法，2022）。AlphaDev（排序演算法，2023）。DeepSeek-R1（數學推理，2025）——最新一次證明遊戲強化學習的技術也能用在文字上。

這個總結單元用一個統一的視角，綜覽三個里程碑架構——AlphaZero、MuZero 與 GRPO：**自我對弈 + 搜尋 + 策略改進**。每一個都是前一個的推廣；GRPO 尤其就是 AlphaZero 的配方套用到 LLM 推理上，把詞元當動作、把數學驗證當成勝負訊號。

## 核心概念

![AlphaZero ↔ MuZero ↔ GRPO：同一個迴圈，不同的環境](../assets/rl-games.svg)

**統一的迴圈。**

```
while True:
    trajectory = self_play(current_policy, search)     # play game against self
    policy_target = search.improved_policy(trajectory) # search improves raw policy
    policy_net.update(policy_target, value_target)     # supervised on search output
```

**AlphaZero（2017）。** Silver et al. 給定一個規則已知的遊戲（西洋棋、將棋、圍棋）：

- 策略—價值網路：單一塔狀網路 `f_θ(s) → (p, v)`。`p` 是合法著手上的先驗。`v` 是預期的對局結果。
- 蒙地卡羅樹搜尋（MCTS）：每一手都展開一棵可能延續的樹。用 `(p, v)` 當先驗 + 自舉。以 UCB（PUCT）選擇節點：`a* = argmax Q(s, a) + c · p(a|s) · √N(s) / (1 + N(s, a))`。
- 自我對弈：讓代理程式對代理程式下棋。在第 `t` 手，MCTS 的造訪分布 `π_t` 就成為策略的訓練目標。
- 損失函式：`L = (v - z)² - π · log p + c · ||θ||²`。`z` 是對局結果（+1 / 0 / -1）。

零人類知識。零手工啟發式。單一套配方，在各自幾千萬盤自我對弈之後就精通了西洋棋、將棋與圍棋。

**MuZero（2019）。** Schrittwieser et al. 拿掉了「規則必須已知」這個要求。

- 不用固定的環境，而是學一個*潛在動力學模型* `(h, g, f)`：
  - `h(s)`：把觀測編碼成潛在狀態。
  - `g(s_latent, a)`：預測下一個潛在狀態 + 獎勵。
  - `f(s_latent)`：預測策略先驗 + 價值。
- MCTS 跑在*學到的潛在空間*裡。一樣的搜尋，一樣的訓練迴圈。
- 在圍棋、西洋棋、將棋*以及* Atari 上都行——一個演算法，不需要知道規則。

**隨機 MuZero（2022）。** 加入隨機動力學與機率節點；延伸到西洋雙陸棋這一類的遊戲。

**Muesli、Gumbel MuZero（2022-2024）。** 在樣本效率與確定性搜尋上的改進。

**GRPO（2024-2025）。** DeepSeek-R1 的配方。同樣是 AlphaZero 形狀的迴圈，套用到語言模型的推理上：

- 「遊戲」：回答一道數學／程式／推理題。「贏」＝驗證器（測資通過、數值答案吻合）回傳 1。
- 策略：那個 LLM。動作：詞元。狀態：提示詞 + 到目前為止的回應。
- 沒有評論家（PPO 式的 `V_φ`）。取而代之的是，對每一個提示詞從策略取樣 `G` 份補全。算出每一份的獎勵。用**群組相對優勢** `A_i = (r_i - mean_r) / std_r` 當作 REINFORCE 式更新的訊號。
- 對參考模型加 KL 散度懲罰以防漂移（跟 RLHF 一樣）。
- 完整損失：

  `L_GRPO(θ) = -E_{q, {o_i}} [ (1/G) Σ_i A_i · log π_θ(o_i | q) ] + β · KL(π_θ || π_ref)`

沒有獎勵模型，沒有評論家，沒有 MCTS。群組相對基準一口氣取代了三者。在推理基準上，品質追平甚至超越 PPO-RLHF，而算力只要一小部分。

**完整的 R1 配方。** DeepSeek-R1（DeepSeek 2025）在同一篇論文裡其實是兩個模型：

- **R1-Zero。** 從 DeepSeek-V3 基礎模型出發。不做 SFT。直接套用 GRPO，配兩種獎勵成分：*準確性獎勵*（規則式的——最終答案能不能解析成正確數字／程式能不能通過單元測試）與*格式獎勵*（補全有沒有把思維鏈包在 `<think>…</think>` 標籤裡）。跑上幾千步之後，平均回應長度從約 100 個詞元長到約 10,000 個，數學基準分數也爬到接近 o1-preview 的水準。模型從零學會了推理。壞處是：它的思維鏈常常讀不懂、語言混用，也缺乏文字上的打磨。
- **R1。** 用一條四階段流水線來修掉 R1-Zero 的可讀性問題：
  1. **冷啟動 SFT。** 蒐集幾千筆格式乾淨的長思維鏈示範。拿它們對基礎模型做監督式微調。這給了一個可讀的起點。
  2. **推理導向的 GRPO。** 套用 GRPO，用準確性 + 格式獎勵，再加一個*語言一致性*獎勵來防止語碼轉換。
  3. **拒絕取樣 + 第二輪 SFT。** 從強化學習的檢查點取樣約 60 萬筆推理軌跡，只留下最終答案正確且思維鏈可讀的那些，再併上約 20 萬筆非推理的 SFT 樣本（寫作、問答、自我認知）。再把基礎模型微調一次。
  4. **全光譜 GRPO。** 再跑一輪強化學習，同時涵蓋推理（規則式獎勵）與一般對齊（以有幫助／無害為基礎的偏好資料獎勵）。

結果是在開放權重的前提下，於 AIME 與 MATH-500 上追平 o1，而且小到可以蒸餾。同一篇論文另外釋出六個蒸餾出來的稠密模型（從 Qwen-1.5B 到 Llama-70B），做法是拿 R1 的推理軌跡做 SFT——學生端完全不跑強化學習。從一個強的強化學習老師蒸餾，在學生的規模上一貫地勝過從零開始跑強化學習。

**推理為什麼用 GRPO 而不用 PPO。** DeepSeekMath 論文（2024 年 2 月）給了三個理由：（1）沒有價值網路要訓練，記憶體省一半；（2）群組基準天生就能處理推理任務產生的那種稀疏、只在軌跡結尾出現的獎勵；（3）逐提示詞的正規化讓難度天差地遠的題目之間，優勢仍然可以互相比較，而 PPO 的單一評論家做不到這件事。

**無搜尋 vs 有搜尋。** 遊戲這條路已經分岔了：

- *長時程的完全資訊賽局*（圍棋、西洋棋）：仍然是搜尋派。AlphaZero／MuZero 稱霸。
- *LLM 推理*：目前生產環境還沒用上 MCTS；用的是在完整 rollout 上跑 GRPO，推論算力則靠 best-of-N。過程獎勵模型（PRM）暗示著步驟層級的搜尋正要被加回來。

## 動手實作

`code/main.py` 裡的程式碼實作了**迷你版的 GRPO**——一個帶多組樣本的吃角子老虎機。演算法跟在 LLM 上跑的完全一樣；只是策略與環境更簡單。它教的是那個*損失函式*與*群組相對優勢*，也就是 2025 年的那項創新。

### 步驟 1：極小的驗證器環境

```python
QUESTIONS = [
    {"prompt": "q1", "correct": 3},
    {"prompt": "q2", "correct": 1},
]

def verify(prompt_idx, answer_token):
    return 1.0 if answer_token == QUESTIONS[prompt_idx]["correct"] else 0.0
```

在真的 GRPO 裡，驗證器會去跑單元測試或檢查數學等式。

### 步驟 2：策略——每個提示詞在 K 個答案詞元上的 softmax

```python
def policy_probs(theta, p_idx):
    return softmax(theta[p_idx])
```

等同於一個以提示詞為條件的 LLM 最後一層的輸出。

### 步驟 3：群組取樣與群組相對優勢

```python
def grpo_step(theta, p_idx, G=8, beta=0.01, lr=0.1, rng=None):
    probs = policy_probs(theta, p_idx)
    samples = [sample(probs, rng) for _ in range(G)]
    rewards = [verify(p_idx, s) for s in samples]
    mean_r = sum(rewards) / G
    std_r = stddev(rewards) + 1e-8
    advs = [(r - mean_r) / std_r for r in rewards]

    for a, A in zip(samples, advs):
        grad = onehot(a) - probs
        for i in range(len(probs)):
            theta[p_idx][i] += lr * A * grad[i]
    # KL penalty: pull theta toward reference
    for i in range(len(probs)):
        theta[p_idx][i] -= beta * (theta[p_idx][i] - reference[p_idx][i])
```

群組相對優勢就是 2024 年 DeepSeek 的那個技巧。不需要評論家。「基準」是群組平均，正規化則用群組標準差。

### 步驟 4：跟 REINFORCE 基準線（無價值函式）比較

一樣的設定、一樣的算力，跑普通的 REINFORCE。GRPO 收斂更快也更穩。

### 步驟 5：觀察熵與 KL

診斷指標跟 RLHF 一樣：對參考模型的平均 KL、策略的熵、獎勵隨時間的變化。等這些都穩定下來，訓練就完成了。

## 常見陷阱

- **靠鑽驗證器漏洞做的獎勵駭入。** GRPO 承襲了 RLHF 的風險：只要驗證器是錯的或可被利用的，LLM 就會找到那個漏洞。夠穩健的驗證器（多組測資、形式化證明）很重要。
- **群組太小。** 群組基準的變異數大約是 `1/√G`。低於 `G = 4`，優勢訊號就很吵；標準選擇是 `G = 8` 到 `64`。
- **長度偏差。** 長度不同的 LLM 補全，對數機率天生就不同。要依詞元數正規化，或改用序列層級的對數機率，或截斷到最大長度。
- **純自我對弈的循環。** AlphaZero 式的訓練在一般和賽局上可能卡進支配迴圈。用多樣的對手池（聯賽式對戰，單元 10）來緩解。
- **搜尋與策略不匹配。** AlphaZero 訓練策略去模仿搜尋的輸出。如果策略網路小到表達不了搜尋的分布，訓練就會停滯。
- **算力門檻。** MuZero／AlphaZero 需要巨量算力。單做一次消融實驗往往就是好幾百 GPU 小時。學習用的迷你示範是有的（例如在四子棋上跑 AlphaZero）。
- **驗證器涵蓋不足。** 一份有 bug 的解答如果照樣通過單元測試，那就是在強化那個 bug。設計驗證器時要顧到邊界情況。

## 框架應用

2026 年遊戲強化學習的版圖，依領域分：

| 領域 | 主流方法 |
|--------|-----------------|
| 雙人零和棋盤遊戲（圍棋、西洋棋、將棋） | AlphaZero／MuZero／KataGo |
| 不完全資訊的紙牌遊戲（撲克） | CFR + 深度學習（DeepStack、Libratus、Pluribus） |
| Atari／像素遊戲 | Muesli／MuZero／IMPALA-PPO |
| 大型多人策略遊戲（Dota、星海爭霸） | PPO + 自我對弈 + 聯賽式對戰（OpenAI Five、AlphaStar） |
| LLM 的數學／程式推理 | GRPO（DeepSeek-R1、Qwen-RL、各種開源復現） |
| LLM 對齊 | DPO／RLHF-PPO（不是 GRPO；這裡的判準是偏好，不是可驗證的東西） |
| 機器人 | PPO + DR（不算遊戲強化學習，但用的是同一套策略梯度工具） |
| 組合最佳化問題 | AlphaZero 的各種變體（AlphaTensor、AlphaDev） |

這套*配方*——自我對弈、以搜尋增強的改進、策略蒸餾——橫跨文字、像素與實體控制。GRPO 是最年輕的一個實例；後面還會有更多。

## 產出交付

存成 `outputs/skill-game-rl-designer.md`：

```markdown
---
name: game-rl-designer
description: Design a game-RL or reasoning-RL training pipeline (AlphaZero / MuZero / GRPO) for a given domain.
version: 1.0.0
phase: 9
lesson: 12
tags: [rl, alphazero, muzero, grpo, self-play]
---

Given a target (perfect-info game / imperfect-info / Atari / LLM reasoning / combinatorial), output:

1. Environment fit. Known rules? Markov? Stochastic? Multi-agent? Informs AlphaZero vs MuZero vs GRPO.
2. Search strategy. MCTS (PUCT with learned prior), Gumbel-sampled, best-of-N, or none.
3. Self-play plan. Symmetric self-play / league / offline data / verifier-generated.
4. Target signal. Game outcome / verifier reward / preference / learned model. Include robustness plan.
5. Diagnostics. Win rate vs baseline, ELO curve, verifier pass rate, KL to reference.

Refuse AlphaZero on imperfect-info games (route to CFR). Refuse GRPO without a trusted verifier. Refuse any game-RL pipeline without a fixed baseline opponent set (self-play ELO is uncalibrated otherwise).
```

## 練習

1. **簡單。** 實作 `code/main.py` 裡的 GRPO 吃角子老虎機。在 2 個提示詞 × 每個 4 個答案詞元上訓練。用 `G=8`，在 1,000 次更新內收斂。
2. **中等。** 換上 PPO（裁剪版）與原味 REINFORCE。在同一個吃角子老虎機上，跟 GRPO 比較樣本效率與獎勵的變異數。
3. **困難。** 延伸成長度為 2 的「推理鏈」：代理程式吐出兩個詞元，驗證器針對這一對給獎勵。量測 GRPO 如何處理跨兩步序列的功勞分配。（提示：以*完整序列*為單位計算群組優勢，再傳播到兩個詞元位置。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| MCTS | 「配學習型網路的樹搜尋」 | 蒙地卡羅樹搜尋；用學來的 `(p, v)` 先驗做 UCB1／PUCT 選擇。 |
| AlphaZero | 「自我對弈 + MCTS」 | 訓練策略—價值網路去吻合 MCTS 造訪次數與對局結果。 |
| MuZero | 「配學習型模型的 AlphaZero」 | 同一個迴圈，但透過學到的動力學跑在潛在空間裡。 |
| GRPO | 「不用評論家的 PPO」 | 群組相對策略最佳化；配群組平均基準 + KL 的 REINFORCE。 |
| PUCT | 「AlphaZero 的 UCB」 | `Q + c · p · √N / (1 + N_a)` —— 在價值估計與先驗之間取得平衡。 |
| 自我對弈 | 「代理程式對上過去的自己」 | 零和賽局的標準做法；訓練訊號對稱。 |
| 聯賽式對戰 | 「族群式的自我對弈」 | 從過去的、當前的、加上剋星策略中取樣對手。 |
| 驗證器獎勵 | 「可驗證的強化學習」 | 獎勵來自一個確定性的檢查器（測資通過、答案吻合）。 |
| 過程獎勵 | 「PRM」 | 對每一個推理步驟評分，而不只是最終答案。 |

## 延伸閱讀

- [Silver et al. (2017). Mastering the game of Go without human knowledge (AlphaGo Zero)](https://www.nature.com/articles/nature24270)。
- [Silver et al. (2018). A general reinforcement learning algorithm that masters chess, shogi, and Go through self-play (AlphaZero)](https://www.science.org/doi/10.1126/science.aar6404)。
- [Schrittwieser et al. (2020). Mastering Atari, Go, chess and shogi by planning with a learned model (MuZero)](https://www.nature.com/articles/s41586-020-03051-4)。
- [Vinyals et al. (2019). Grandmaster level in StarCraft II (AlphaStar)](https://www.nature.com/articles/s41586-019-1724-z)。
- [DeepSeek-AI (2024). DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models (GRPO)](https://arxiv.org/abs/2402.03300) —— 提出 GRPO 與群組相對基準的那篇論文。
- [DeepSeek-AI (2025). DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948) —— 完整的四階段 R1 配方，外加 R1-Zero 的消融實驗。
- [Brown et al. (2019). Superhuman AI for multiplayer poker (Pluribus)](https://www.science.org/doi/10.1126/science.aay2400) —— 大規模的 CFR + 深度學習。
- [Tesauro (1995). Temporal Difference Learning and TD-Gammon](https://dl.acm.org/doi/10.1145/203330.203343) —— 開啟這一切的那篇論文。
- [Hugging Face TRL — GRPOTrainer](https://huggingface.co/docs/trl/main/en/grpo_trainer) —— 搭配自訂獎勵函式套用 GRPO 的生產級參考。
- [Qwen Team (2024). Qwen2.5-Math — GRPO replication](https://github.com/QwenLM/Qwen2.5-Math) —— 在多種規模上對 R1 配方的開源復現。
- [Sutton & Barto (2018). Ch. 17 — Frontiers of Reinforcement Learning](http://incompleteideas.net/book/RLbook2020.pdf) —— 教科書對自我對弈、搜尋與「設計出來的獎勵」的框架，而 R1 正是把它實現在 LLM 的規模上。
