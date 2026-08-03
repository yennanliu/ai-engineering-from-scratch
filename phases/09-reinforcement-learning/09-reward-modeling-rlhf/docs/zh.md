# 獎勵建模與 RLHF

> 人類寫不出「好的助理回應」的獎勵函式，但人類可以比較兩個回應、挑出比較好的那個。把一個獎勵模型擬合到這些比較上，再用強化學習拿語言模型去對它最佳化。Christiano 2017。InstructGPT 2022。就是這個配方把 GPT-3 變成了 ChatGPT。到 2026 年它大致上已被 DPO 取代——但這套心智模型還在。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 05（情感分析）、階段 9 · 08（PPO）
**時間：** 約 45 分鐘

## 問題所在

你用「預測下一個詞元」的目標訓練了一個語言模型。它寫得出合乎文法的英文。它也會說謊、會囉唆、該拒絕的時候不拒絕。這件事不是靠更多預訓練能修好的——網路文本是病因，不是解藥。

你想要一個*純量獎勵*，能說「對指令 X 而言，回應 A 比回應 B 好」。手寫這種獎勵函式是不可能的。「有幫助」不是一個能對詞元寫出閉式表達的東西。但人類可以比較兩份輸出並標出偏好。這種資料要大量蒐集很便宜。

RLHF（Christiano et al. 2017；Ouyang et al. 2022）蒐集人類對模型輸出的偏好，訓練獎勵模型，再以 PPO 最佳化語言模型。三個步驟：SFT → RM → PPO。它就是把 ChatGPT、Claude、Gemini，以及 2023–2025 年間每一個對齊過的 LLM 送上線的配方。

到 2026 年，PPO 那一步大致上被 DPO（階段 10 · 08）取代了，因為它更便宜，而且在對齊調校上幾乎一樣好。但*獎勵模型*這一塊仍然撐著每一個 Best-of-N 取樣器、每一條「從可驗證獎勵學習」的流水線，以及每一個用上過程獎勵模型的推理模型。搞懂 RLHF，你就搞懂了整個對齊技術堆疊。

## 核心概念

![三階段 RLHF：SFT、以成對偏好訓練 RM、帶 KL 散度懲罰的 PPO](../assets/rlhf.svg)

**階段 1：監督式微調（SFT）。** 從一個預訓練的基礎模型出發。用人類撰寫的目標行為示範（遵循指令的回應、有幫助的答覆等）做微調。結果是一個模型 `π_SFT`：它*偏向好的行為*，但動作空間仍然沒有邊界。

**階段 2：獎勵模型訓練。**

- 針對提示詞 `x` 蒐集成對的回應 `(y_+, y_-)`，由人類標註成「`y_+` 優於 `y_-`」。
- 訓練一個獎勵模型 `R_φ(x, y)`，讓它給 `y_+` 更高的分數。
- 損失函式：**Bradley-Terry 成對邏輯斯迴歸**：

  `L(φ) = -E[ log σ(R_φ(x, y_+) - R_φ(x, y_-)) ]`

  σ 是 sigmoid。獎勵的差值意味著偏好的對數勝算比。BT 從 1952 年（Bradley-Terry）以來就是標準做法，也是現代 RLHF 的主流選擇。

- `R_φ` 通常是從 SFT 模型初始化、在上面加一個純量輸出頭。一樣的 Transformer 骨幹；單一線性層輸出獎勵。

**階段 3：帶 KL 散度懲罰、對 RM 做 PPO。**

- 用 `π_SFT` 初始化可訓練的策略 `π_θ`。同時留一份凍結的*參考模型* `π_ref = π_SFT`。
- 回應 `y` 結尾處的獎勵：

  `r_total(x, y) = R_φ(x, y) - β · KL(π_θ(·|x) || π_ref(·|x))`

  KL 散度懲罰防止 `π_θ` 任意漂離 `π_SFT`——它是個*正則化項*，不是硬性的信賴區域。`β` 一般取 `0.01`-`0.05`。
- 用這個獎勵跑 PPO（單元 08）。優勢是在詞元層級的軌跡上計算的，但 RM 只對完整回應評分。

**為什麼要 KL？** 沒有它，PPO 會很開心地找出獎勵駭入的策略——RM 只在分布內的補全上訓練過。一個分布外的回應，分數可能比任何人類寫的都高。KL 讓 `π_θ` 待在 RM 訓練過的那塊流形附近。它是 RLHF 裡最重要的單一旋鈕。

**2026 年現況：**

- **DPO**（Rafailov 2023）：閉式的代數推導把階段 2+3 收成在偏好資料上的單一監督式損失。不用 RM，不用 PPO。在對齊基準上品質相當，但算力只要一小部分。收錄在階段 10 · 08。
- **GRPO**（DeepSeek 2024–2025）：用群組相對基準取代評論家的 PPO，獎勵來自*驗證器*（程式跑得過／數學答案對得上）而不是人類訓練出來的 RM。推理模型的主流做法。收錄在階段 9 · 12。
- **過程獎勵模型（PRM）：** 對部分解答（每一個推理步驟）評分，在 RLHF 與推理用的 GRPO 變體裡都會用到。
- **Constitutional AI／RLAIF：** 用一個已對齊的 LLM 來生成偏好，取代人類。把偏好資料的預算放大。

```figure
reward-model
```

## 動手實作

這個單元用極小的合成「提示詞」與「回應」，都以字串表示。RM 是一個建立在詞袋表示上的線性評分器。沒有真的 LLM——重點在流水線的*形狀*，不在規模。見 `code/main.py`。

### 步驟 1：合成偏好資料

```python
PROMPTS = ["help me", "answer me", "explain this"]
GOOD_WORDS = {"clear", "specific", "kind", "thorough"}
BAD_WORDS = {"vague", "rude", "wrong", "short"}

def make_pair(rng):
    x = rng.choice(PROMPTS)
    y_good = rng.choice(list(GOOD_WORDS)) + " " + rng.choice(list(GOOD_WORDS))
    y_bad = rng.choice(list(BAD_WORDS)) + " " + rng.choice(list(BAD_WORDS))
    return (x, y_good, y_bad)
```

在真實的 RLHF 裡，這一段換成人類標註者。形狀——`(prompt, preferred_response, rejected_response)`——完全一樣。

### 步驟 2：Bradley-Terry 獎勵模型

線性分數：`R(x, y) = w · bag(y)`。訓練目標是最小化 BT 的成對對數損失：

```python
def rm_train_step(w, x, y_pos, y_neg, lr):
    r_pos = dot(w, bag(y_pos))
    r_neg = dot(w, bag(y_neg))
    p = sigmoid(r_pos - r_neg)
    for tok, cnt in bag(y_pos).items():
        w[tok] += lr * (1 - p) * cnt
    for tok, cnt in bag(y_neg).items():
        w[tok] -= lr * (1 - p) * cnt
```

跑幾百次更新之後，`w` 會給好詞的詞元正權重、給壞詞負權重。

### 步驟 3：架在 RM 之上的類 PPO 策略

我們的玩具策略從一個詞彙表裡產生單一詞元。我們用 RM 對這個詞元評分，計算 `log π_θ(token | prompt)`，加上對參考模型的 KL 懲罰，然後套用 PPO 的裁剪代理目標。

```python
def rlhf_step(theta, ref, w, prompt, rng, eps=0.2, beta=0.1, lr=0.05):
    logits_theta = policy_logits(theta, prompt)
    probs = softmax(logits_theta)
    token = sample(probs, rng)
    logits_ref = policy_logits(ref, prompt)
    probs_ref = softmax(logits_ref)
    reward = dot(w, bag([token])) - beta * kl(probs, probs_ref)
    # ppo-style update on theta, treating reward as the return
    ...
```

### 步驟 4：盯著 KL

每次更新都追蹤平均 `KL(π_θ || π_ref)`。如果它爬過 `~5-10`，代表策略已經遠離 `π_SFT`——不是 `β` 太低，就是獎勵駭入開始了。這是真實 RLHF 裡的首要診斷指標。

### 步驟 5：用 TRL 寫的生產級配方

搞懂玩具版流水線之後，這裡是同一個迴圈在真正函式庫使用者手上的樣子。Hugging Face 的 [TRL](https://huggingface.co/docs/trl) 是參考實作——階段 2 用 `RewardTrainer`，階段 3 用 `PPOTrainer`（內建對參考模型的 KL）。

```python
# Stage 2: reward model from pairwise preferences
from trl import RewardTrainer, RewardConfig
from transformers import AutoModelForSequenceClassification, AutoTokenizer

tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
rm = AutoModelForSequenceClassification.from_pretrained(
    "meta-llama/Llama-3.1-8B-Instruct", num_labels=1
)

# dataset rows: {"prompt", "chosen", "rejected"} — Bradley-Terry format
trainer = RewardTrainer(
    model=rm,
    tokenizer=tok,
    train_dataset=preference_data,
    args=RewardConfig(output_dir="./rm", num_train_epochs=1, learning_rate=1e-5),
)
trainer.train()
```

```python
# Stage 3: PPO against the RM with KL penalty to the SFT reference
from trl import PPOTrainer, PPOConfig, AutoModelForCausalLMWithValueHead

policy = AutoModelForCausalLMWithValueHead.from_pretrained("./sft-checkpoint")
ref    = AutoModelForCausalLMWithValueHead.from_pretrained("./sft-checkpoint")  # frozen

ppo = PPOTrainer(
    config=PPOConfig(learning_rate=1.41e-5, batch_size=64, init_kl_coef=0.05,
                     target_kl=6.0, adap_kl_ctrl=True),
    model=policy, ref_model=ref, tokenizer=tok,
)

for batch in dataloader:
    responses = ppo.generate(batch["query_ids"], max_new_tokens=128)
    rewards   = rm(torch.cat([batch["query_ids"], responses], dim=-1)).logits[:, 0]
    stats     = ppo.step(batch["query_ids"], responses, rewards)
    # stats includes: mean_kl, clip_frac, value_loss — the three PPO diagnostics
```

有三件事是函式庫幫你做掉的。`adap_kl_ctrl=True` 實作了自適應 β 排程：觀測到的 KL 超過 `target_kl` 就把 β 加倍，低於一半就減半。參考模型依慣例要凍結——你絕不能不小心讓它跟 `policy` 共用參數。而價值頭是掛在跟策略同一個骨幹上的（`AutoModelForCausalLMWithValueHead` 接了一個純量 MLP 頭），這也是為什麼 TRL 會分開回報 `policy/kl` 與 `value/loss`。

## 常見陷阱

- **過度最佳化／獎勵駭入。** RM 並不完美；`π_θ` 會找到分數很高但實際上很爛的對抗性補全。症狀：獎勵一路往上爬，但人工評估分數卻持平或下滑。解法：提早停止、調高 `β`、擴大 RM 的訓練資料。
- **長度駭入。** 在「有幫助的回應」上訓練出來的 RM，常常隱含地獎勵長度。策略就學會把回應灌水。補救：做長度正規化的獎勵，或改用長度感知 RM 的 RLAIF。
- **RM 太小。** RM 至少要跟策略一樣大。太小的 RM 沒辦法忠實地為策略的輸出評分。
- **KL 沒調好。** β 太低 → 漂移與獎勵駭入。β 太高 → 策略幾乎不動。標準技巧是用*自適應*的 β，把每一步的 KL 釘在固定值上。
- **偏好資料的雜訊。** 大約 30% 的人類標註是有雜訊或有歧義的。做法是用經過標註者共識過濾的資料訓練 RM，或在 BT 上加一個溫度參數來校準。
- **異策略問題。** 第一個回合數之後，PPO 的資料就略為異策略了。像單元 08 那樣盯著裁剪比例。

## 框架應用

2026 年的 RLHF 是分層的：

| 層次 | 目標 | 方法 |
|-------|--------|--------|
| 遵循指令、有幫助、無害 | 對齊 | DPO（階段 10 · 08）優於 RLHF-PPO。 |
| 推理正確性（數學、程式） | 能力 | 配驗證器獎勵的 GRPO（階段 9 · 12）。 |
| 長時程的多步驟任務 | 代理程式 | 配跨步驟過程獎勵模型的 PPO／GRPO。 |
| 安全性／拒答行為 | 安全 | 配獨立安全 RM 的 RLHF-PPO，或 Constitutional AI。 |
| 推論時的 Best-of-N | 快速對齊 | 在解碼時用 RM；不需要訓練策略。 |
| 獎勵蒸餾 | 推論算力 | 在凍結的語言模型上訓練一個小的「獎勵頭」。 |

RLHF 在 2022–2024 年是*那個*方法。到 2026 年，生產環境的對齊流水線是 DPO 優先，只在 RM 吃重或安全關鍵的環節才動用 PPO。

## 產出交付

存成 `outputs/skill-rlhf-architect.md`：

```markdown
---
name: rlhf-architect
description: Design an RLHF / DPO / GRPO alignment pipeline for a language model, including RM, KL, and data strategy.
version: 1.0.0
phase: 9
lesson: 9
tags: [rl, rlhf, alignment, llm]
---

Given a base LM, a target behavior (alignment / reasoning / refusal / agent), and a preference or verifier budget, output:

1. Stage. SFT? RM? DPO? GRPO? With justification.
2. Preference or verifier source. Humans, AI feedback, rule-based, unit-test-pass, or reward distillation.
3. KL strategy. Fixed β, adaptive β, or DPO (implicit KL).
4. Diagnostics. Mean KL, reward stability, over-optimization guard (holdout human eval).
5. Safety gate. Red-team set, refusal rate, safety RM separate from helpfulness RM.

Refuse to ship RLHF-PPO without a KL monitor. Refuse to use an RM smaller than the target policy. Refuse length-only rewards. Flag any pipeline that does not hold back a blind human-eval set as lacking over-optimization protection.
```

## 練習

1. **簡單。** 用 500 對合成偏好資料訓練 `code/main.py` 裡的 Bradley-Terry 獎勵模型。在保留的 100 對上量測成對比較準確率。應該超過 90%。
2. **中等。** 用 `β ∈ {0.0, 0.1, 1.0}` 跑玩具版 PPO-RLHF 迴圈。針對每一種，畫出 RM 分數對「相對參考模型的 KL」隨更新次數的變化。哪幾次跑出了獎勵駭入？
3. **困難。** 在同一批偏好資料上實作 DPO（閉式的偏好似然損失），並在「用掉多少算力」與「最終達到的 RM 分數」兩方面跟 RLHF-PPO 流水線比較。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| RLHF | 「對齊用的強化學習」 | SFT + RM + PPO 的三階段流水線（Christiano 2017、Ouyang 2022）。 |
| 獎勵模型（RM） | 「那個評分網路」 | 透過 Bradley-Terry 擬合到成對比較上的學習型純量函式。 |
| Bradley-Terry | 「成對邏輯斯損失」 | `P(y_+ ≻ y_-) = σ(R(y_+) - R(y_-))`；標準的 RM 目標。 |
| KL 散度懲罰 | 「別離參考模型太遠」 | 獎勵裡的 `β · KL(π_θ \|\| π_ref)`；防獎勵駭入的正則化項。 |
| 獎勵駭入 | 「Goodhart 定律」 | 策略鑽 RM 的漏洞；症狀是獎勵上升、人工評估持平。 |
| RLAIF | 「AI 標的偏好」 | 標註來自另一個語言模型而非人類的 RLHF。 |
| PRM | 「過程獎勵模型」 | 對部分推理步驟評分；用在推理流水線裡。 |
| Constitutional AI | 「Anthropic 的方法」 | 由明文規則引導、AI 生成的偏好。 |

## 延伸閱讀

- [Christiano et al. (2017). Deep Reinforcement Learning from Human Preferences](https://arxiv.org/abs/1706.03741) —— 開啟 RLHF 的那篇論文。
- [Ouyang et al. (2022). InstructGPT — Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155) —— ChatGPT 背後的配方。
- [Stiennon et al. (2020). Learning to summarize with human feedback](https://arxiv.org/abs/2009.01325) —— 更早的、用在摘要上的 RLHF。
- [Rafailov et al. (2023). Direct Preference Optimization](https://arxiv.org/abs/2305.18290) —— DPO；2026 年後 RLHF 時代的預設做法。
- [Bai et al. (2022). Constitutional AI: Harmlessness from AI Feedback](https://arxiv.org/abs/2212.08073) —— RLAIF 與自我批判迴圈。
- [Anthropic RLHF paper (Bai et al. 2022). Training a Helpful and Harmless Assistant](https://arxiv.org/abs/2204.05862) —— 那篇 HH 論文。
- [Hugging Face TRL library](https://huggingface.co/docs/trl) —— 生產級的 `RewardTrainer` 與 `PPOTrainer`。想搞懂自適應 KL 與價值頭的細節，就去讀 trainer 的原始碼。
- [Hugging Face — Illustrating Reinforcement Learning from Human Feedback](https://huggingface.co/blog/rlhf) by Lambert, Castricato, von Werra, Havrilla —— 三階段流水線的經典圖解導覽。
- [von Werra et al. (2020). TRL: Transformer Reinforcement Learning](https://github.com/huggingface/trl) —— 那個函式庫；`examples/` 裡有給 Llama、Mistral、Qwen 的端到端 RLHF 腳本。
- [Sutton & Barto (2018). Ch. 17.4 — Designing Reward Signals](http://incompleteideas.net/book/RLbook2020.pdf) —— 獎勵假說的觀點；思考獎勵駭入前必讀的先備知識。
