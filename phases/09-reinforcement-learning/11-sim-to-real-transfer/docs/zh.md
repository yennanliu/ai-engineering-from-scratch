# 模擬到真實的遷移

> 一個在模擬器裡訓練好、卻在硬體上失敗的策略，就是一個把模擬器背起來的策略。領域隨機化、領域適應與系統辨識，就是讓學到的控制器跨越現實落差的三個工具。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 9 · 08（PPO）、階段 2 · 10（偏差／變異）
**時間：** 約 45 分鐘

## 問題所在

訓練一台真的機器人既慢、又危險、又貴。一台雙足機器人要幾百萬個訓練回合才學得會走路；而一台真的雙足機器人只要摔一次就會弄壞硬體。模擬給你的是無限次重置、確定性的可重現性、平行環境，而且不會有實體損壞。

但模擬器是錯的。軸承的摩擦力比 MuJoCo 模型裡的大。相機有模擬器沒納入的鏡頭畸變。馬達有延遲、齒隙與飽和，而 99% 的模擬模型都跳過這些。風、灰塵與變動的光照，會毀掉一個在無菌渲染畫面上訓練出來的策略。**現實落差**——模擬分布與真實分布之間的系統性差異——是機器人領域中已部署強化學習的核心問題。

你需要一個*對模擬到真實的分布偏移具韌性*的策略。歷史上有三種做法：把模擬器隨機化（領域隨機化）、用少量真實資料調整策略（領域適應／微調），或是辨識出真實系統的參數並把模擬對齊過去（系統辨識）。到 2026 年，主流配方是三者合一，再加上大規模平行模擬（Isaac Sim、Isaac Lab、跑在 GPU 上的 Mujoco MJX）。

## 核心概念

![三種模擬到真實的型態：領域隨機化、領域適應、系統辨識](../assets/sim-to-real.svg)

**領域隨機化（DR）。** Tobin et al. 2017、Peng et al. 2018。訓練期間，把每一個可能與真實機器人有落差的模擬參數都隨機化：質量、摩擦係數、馬達 PD 增益、感測器雜訊、相機位置、光照、材質、接觸模型。策略會學到一個「今天身處哪一個模擬」的條件分布，並在整個範圍上泛化。只要真實機器人落在訓練的涵蓋範圍內，策略就管用。

- **好處：** 不需要真實資料。一套配方，多種機器人。
- **壞處：** 過度隨機化的訓練會產出一個「萬用」但過度保守的策略。雜訊太多 ≈ 正則化太重。

**系統辨識（SI）。** 在訓練前，先用真實世界的資料去擬合模擬器的參數。如果你量得到真實機器人手臂關節的摩擦力，就把那個值填進模擬。然後訓練一個預期會遇到這些數值的策略。這需要能接觸到真實系統，但能直接縮小現實落差。

- **好處：** 訓練目標精確、雜訊低。
- **壞處：** 殘餘的模型誤差對策略是不可見的；沒被辨識出來的小效應（例如馬達死區）照樣會毀掉部署。

**領域適應。** 在模擬裡訓練，再用少量真實資料微調。兩種風味：

- **Real2Sim2Real：** 用真實 rollout 學一個殘差模擬器 `f(s, a, z) - f_sim(s, a)`，再到修正過的模擬裡訓練。不需要太多真實資料就能補上落差。
- **觀測適應：** 訓練一個策略，透過學來的特徵抽取器（例如 GAN 的逐像素轉換）把真實觀測映射成類模擬觀測。控制器本身留在模擬裡。

**特權學習／師生架構。** Miki et al. 2022（ANYmal 四足機器人）。在模擬裡訓練一個能取用特權資訊（真實摩擦力、地形高度、IMU 漂移）的*老師*。再蒸餾出一個只看得到真實感測器觀測的*學生*。學生學會從歷史中推論出那些特權特徵，並在各種物理參數下都保持韌性。

**大規模平行模擬。** 2024–2026 年。Isaac Lab、Mujoco MJX、Brax 都能在單張 GPU 上跑幾千台平行的機器人。配 4,096 台平行人形機器人的 PPO，能在幾小時內蒐集到相當於好幾年的經驗。訓練分布一變寬，「現實落差」就縮小；當那 4,096 個環境各自帶著不同的隨機化參數時，領域隨機化幾乎不用額外成本。

**2026 年真實世界的配方（以四足機器人行走為例）：**

1. 大規模平行模擬，對重力、摩擦力、馬達增益、負載做領域隨機化。
2. 用特權資訊（地形圖、機身速度真值）訓練老師策略。
3. 從老師蒸餾出只用本體感覺（腿部關節編碼器）的學生策略。
4. 選配：用自編碼器對真實 IMU 做觀測適應。
5. 部署。在 10 種以上的環境上做零樣本測試。如果失敗，就用受安全約束的 PPO 做幾分鐘的真實世界微調。

```figure
f3-reality-gap
```

## 動手實作

這個單元的程式碼，是在一個轉移帶有*雜訊*的 GridWorld 上對領域隨機化做的迷你示範。我們訓練一個策略，讓它在「模擬」裡經歷隨機化的打滑機率，再拿一個訓練時沒見過的打滑程度在「真實」上評估。這個形狀直接對應到 MuJoCo 到硬體的遷移。

### 步驟 1：參數化的模擬

```python
def step(state, action, slip):
    if rng.random() < slip:
        action = random_perpendicular(action)
    ...
```

`slip` 是模擬器對外暴露的一個參數。在真實機器人上，它可能是摩擦力、質量、馬達增益——任何會在模擬與真實之間偏移的東西。

### 步驟 2：用領域隨機化訓練

每個回合開始時，取樣 `slip ~ Uniform[0.0, 0.4]`。訓練 PPO／Q-learning／隨便什麼都行。這樣跑很多個回合。

### 步驟 3：在「真實」的打滑程度上做零樣本評估

在 `slip ∈ {0.0, 0.1, 0.2, 0.3, 0.5, 0.7}` 上評估。前四個落在訓練支撐集內；`0.5` 與 `0.7` 在外面。用領域隨機化訓練出來的策略，在支撐集內應該接近最佳，在外面則應該優雅地退化。用固定打滑值訓練的策略，一離開它的訓練值就會很脆弱。

### 步驟 4：跟窄幅訓練比較

再訓練第二個策略，只用 `slip = 0.0`。在同一組 `slip` 掃描上評估。你應該會看到只要真實打滑值大於 0，表現就災難性地掉下來。

## 常見陷阱

- **隨機化太多。** 用 `slip ∈ [0, 0.9]` 訓練，你的策略會保守到永遠不敢走最佳路徑。要對齊真實世界的*期望*分布，而不是「什麼都可能發生」。
- **隨機化太少。** 只在一小片區間上訓練，策略就完全泛化不了。改用自適應課程學習（自動領域隨機化），隨著策略進步逐步放寬分布。
- **參數空間辨識錯了。** 隨機化錯的東西（真實落差在馬達延遲，你卻去隨機化相機色調），領域隨機化就幫不上忙。先把真實機器人量測清楚。
- **特權資訊外洩。** 一個用全域狀態（而不只是觀測）決定動作的老師，可能會產出一個永遠追不上它的學生。要確保老師的策略，在學生只有觀測歷史的條件下是可實現的。
- **模擬到模擬的遷移失敗。** 如果你的策略連一個更難的模擬變體都撐不住，那它在真實世界也撐不住。部署前一定要在一個保留的模擬變體上測試。
- **沒有真實世界的安全包絡。** 一個在模擬裡管用、在真實裡「看起來也管用」的策略，少了底層的安全防護罩，照樣會弄壞硬體。要在非學習型的控制器裡加上速率限制、扭矩限制、關節限制。

## 框架應用

2026 年的模擬到真實技術堆疊：

| 領域 | 技術堆疊 |
|--------|-------|
| 足式移動（ANYmal、Spot、人形機器人） | Isaac Lab + DR + 特權老師／學生 |
| 操作（靈巧手、取放） | Isaac Lab + DR + 給視覺用的 DR-GAN |
| 自動駕駛 | CARLA／NVIDIA DRIVE Sim + DR + 真實微調 |
| 無人機競速 | RotorS／Flightmare + DR + 線上適應 |
| 手指／手中操作 | OpenAI Dactyl（規模空前的 DR） |
| 工業機械手臂 | MuJoCo-Warp + SI + 少量真實微調 |

不論規模大小，控制問題的工作流程都一致：能擬合的就盡量把模擬擬合好，擬合不了的就隨機化，訓練超大的策略，蒸餾，再帶著安全防護罩部署。

## 產出交付

存成 `outputs/skill-sim2real-planner.md`：

```markdown
---
name: sim2real-planner
description: Plan a sim-to-real transfer pipeline for a given robot + task, covering DR, SI, and safety.
version: 1.0.0
phase: 9
lesson: 11
tags: [rl, sim2real, robotics, domain-randomization]
---

Given a robot platform, a task, and access to real hardware time, output:

1. Reality gap inventory. Suspected sources ranked by expected impact (contact, sensing, actuation delay, vision).
2. DR parameters. Exact list, ranges, distribution. Justify each range against real measurements.
3. SI steps. Which parameters to measure; measurement method.
4. Teacher/student split. What privileged info the teacher uses; what obs the student uses.
5. Safety envelope. Low-level limits, emergency stops, backup controller.

Refuse to deploy without (a) a zero-shot sim-variant test, (b) a safety shield, (c) a rollback plan. Flag any DR range wider than 3× measured real variability as likely over-randomized.
```

## 練習

1. **簡單。** 在固定打滑值（slip=0.0）的 GridWorld 上訓練一個 Q-learning 代理程式。在 slip ∈ {0.0, 0.1, 0.3, 0.5} 上評估。畫出回報對 slip 的曲線。
2. **中等。** 訓練一個取樣 `slip ~ Uniform[0, 0.3]` 的領域隨機化 Q-learning 代理程式。跑同一組掃描。在 slip=0.5（分布外）時，領域隨機化替你賺到多少？
3. **困難。** 實作一套課程學習：從 slip=0.0 開始，每當策略達到最佳值的 90% 就把領域隨機化的範圍放寬一次。量測要零樣本達到 slip=0.3 總共需要多少環境步數，並跟固定領域隨機化的基準線比較。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 現實落差 | 「模擬與真實的差別」 | 訓練與部署之間在物理／感測上的分布偏移。 |
| 領域隨機化（DR） | 「在隨機的一堆模擬上訓練」 | 訓練期間隨機化模擬參數，好讓策略泛化。 |
| 系統辨識（SI） | 「量真實、擬合模擬」 | 估計真實的物理參數；把模擬設成一致。 |
| 領域適應 | 「用真實資料微調」 | 模擬訓練後用少量真實世界資料微調；可調整觀測或動力學。 |
| 特權資訊 | 「給老師的真值」 | 只有模擬才有的資訊；學生必須從觀測歷史推論出來。 |
| 師生架構 | 「把特權蒸餾成可觀測」 | 老師帶著捷徑訓練；學生學著在沒有捷徑的情況下模仿它。 |
| ADR | 「自動領域隨機化」 | 隨著策略進步而放寬領域隨機化範圍的課程學習。 |
| Real2Sim | 「用真實資料補上落差」 | 學一個殘差項，讓模擬去模仿真實的 rollout。 |

## 延伸閱讀

- [Tobin et al. (2017). Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World](https://arxiv.org/abs/1703.06907) —— 領域隨機化的原始論文（機器人視覺）。
- [Peng et al. (2018). Sim-to-Real Transfer of Robotic Control with Dynamics Randomization](https://arxiv.org/abs/1710.06537) —— 用在動力學上的領域隨機化，四足移動。
- [OpenAI et al. (2019). Solving Rubik's Cube with a Robot Hand](https://arxiv.org/abs/1910.07113) —— Dactyl，大規模的 ADR。
- [Miki et al. (2022). Learning robust perceptive locomotion for quadrupedal robots in the wild](https://www.science.org/doi/10.1126/scirobotics.abk2822) —— ANYmal 的師生架構。
- [Makoviychuk et al. (2021). Isaac Gym: High Performance GPU Based Physics Simulation for Robot Learning](https://arxiv.org/abs/2108.10470) —— 驅動 2025–2026 年各種部署的大規模平行模擬。
- [Akkaya et al. (2019). Automatic Domain Randomization](https://arxiv.org/abs/1910.07113) —— ADR 的課程學習方法。
- [Sutton & Barto (2018). Ch. 8 — Planning and Learning with Tabular Methods](http://incompleteideas.net/book/RLbook2020.pdf) —— Dyna 的框架（用模型做規劃 + rollout），現代模擬到真實流水線的底層思路。
- [Zhao, Queralta & Westerlund (2020). Sim-to-Real Transfer in Deep Reinforcement Learning for Robotics: a Survey](https://arxiv.org/abs/2009.13303) —— 模擬到真實各類方法的分類法，附基準結果。
