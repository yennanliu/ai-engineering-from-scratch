# 長脈絡評估 —— NIAH、RULER、LongBench、MRCR

> Gemini 3 Pro 標稱 10M 詞元的脈絡。可是在 1M 詞元上，8-needle MRCR 掉到 26.3%。標稱 ≠ 可用。長脈絡評估告訴你的，是你真正要上線的那個模型有多少容量。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 13（問答）、階段 5 · 23（切塊策略）
**時間：** 約 60 分鐘

## 問題所在

你手上有一份 200 頁的合約。模型宣稱脈絡窗口有 1M 詞元。你把整份合約貼進去，然後問：「What is the termination clause?」模型答了 —— 但它是拿封面那頁在回答，因為終止條款躺在 120k 詞元深的地方，早就超出模型實際會去注意的範圍。

這就是 2026 年的脈絡容量落差。規格表上寫 1M 或 10M。現實是其中只有 60-70% 可用，而且「可用」還要看任務是什麼。

- **檢索（大海撈針，單根針）：** 前沿模型在標稱上限以內幾乎全對。
- **多跳／聚合：** 在多數模型上，超過約 128k 就急速崩壞。
- **對分散事實做推論：** 最先陣亡的那一類。

長脈絡評估量的就是這幾個面向。這個單元要點出各個基準測試的名字、每一個真正在量什麼，以及怎麼替你自己的領域做一套自訂的大海撈針測試。

## 核心概念

![NIAH 作為基線、RULER 的多任務、LongBench 的全景評估](../assets/long-context-eval.svg)

**大海撈針（Needle-in-a-Haystack，NIAH，2023）。** 把一個事實（「the magic word is pineapple」）放在長脈絡中一個受控的深度上，要模型把它撈出來。掃過深度 × 長度的網格。這是最早的長脈絡基準測試。前沿模型現在已經把它跑滿了；它是必要的基線，但遠遠不夠。

**RULER（Nvidia，2024）。** 13 種任務型態、4 大類：檢索（單鍵／多鍵／多值）、多跳追蹤（變數追蹤）、聚合（常見詞頻率）、問答。脈絡長度可設定（4k 到 128k 以上）。它能揭出那些在 NIAH 上滿分、卻在多跳上翻車的模型。在 2024 年的那一版裡，17 個聲稱支援 32k 以上脈絡的模型，只有一半真的在 32k 上維持住品質。

**LongBench v2（2024）。** 503 道選擇題、8k-2M 字的脈絡、六類任務：單文件問答、多文件問答、長脈絡內學習、長對話、程式碼儲存庫、長結構化資料。要看真實世界的長脈絡行為，這是生產級的基準測試。

**MRCR（Multi-Round Coreference Resolution，多輪共指解析）。** 把多輪共指解析拉到大規模。有 8-needle、24-needle、100-needle 幾種變體。它暴露的是：注意力崩壞之前，一個模型到底能同時抓住多少個事實。

**NoLiMa。** 「非字面的針」。針和查詢之間沒有任何字面重疊，要撈出來就得先做一步語意推論。比 NIAH 難。

**HELMET。** 把很多份文件串起來，然後問其中任一份裡的問題。測的是選擇性注意力。

**BABILong。** 把 bAbI 的推論鏈嵌進不相關的乾草堆裡。測的是「在乾草堆裡推論」，不只是撈出來而已。

### 真正該回報的數字

- **標稱脈絡窗口。** 規格表上那個數字。
- **有效檢索長度。** NIAH 在某個門檻（例如 90%）下還能過關的長度。
- **有效推論長度。** 多跳或聚合任務在同一個門檻下還能過關的長度。
- **衰退曲線。** 準確率對脈絡長度，依任務型態分別畫出來。

你自己的規格表上要有兩個數字：檢索有效長度與推論有效長度。推論有效長度通常只有標稱窗口的 25-50%。

```figure
gx-niah-decay
```

## 動手實作

### 步驟 1：替你的領域做一套自訂 NIAH

見 `code/main.py`。骨架是這樣：

```python
def build_haystack(filler_text, needle, depth_ratio, total_tokens):
    if not (0.0 <= depth_ratio <= 1.0):
        raise ValueError(f"depth_ratio must be in [0, 1], got {depth_ratio}")
    if total_tokens <= 0:
        raise ValueError(f"total_tokens must be positive, got {total_tokens}")

    filler_tokens = tokenize(filler_text)
    needle_tokens = tokenize(needle)
    if not filler_tokens:
        raise ValueError("filler_text produced no tokens")

    # Repeat filler until long enough to fill the haystack body.
    body_len = max(total_tokens - len(needle_tokens), 0)
    while len(filler_tokens) < body_len:
        filler_tokens = filler_tokens + filler_tokens
    filler_tokens = filler_tokens[:body_len]

    insert_at = min(int(body_len * depth_ratio), body_len)
    haystack = filler_tokens[:insert_at] + needle_tokens + filler_tokens[insert_at:]
    return " ".join(haystack)


def score_niah(model, haystack, question, expected):
    answer = model.complete(f"Context: {haystack}\nQ: {question}\nA:", max_tokens=50)
    return 1 if expected.lower() in answer.lower() else 0
```

掃過 `depth_ratio` ∈ {0, 0.25, 0.5, 0.75, 1.0} × `total_tokens` ∈ {1k, 4k, 16k, 64k}。畫成熱圖。那就是你目標模型的 NIAH 成績卡。

### 步驟 2：多針測試的變體

```python
def build_multi_needle(filler, needles, total_tokens):
    depths = [0.1, 0.4, 0.7]
    chunks = [filler[:int(total_tokens * 0.1)]]
    for depth, needle in zip(depths, needles):
        chunks.append(needle)
        next_chunk = filler[int(total_tokens * depth): int(total_tokens * (depth + 0.3))]
        chunks.append(next_chunk)
    return " ".join(chunks)
```

像「What are the three magic words?」這樣的問題，得把三根針全部撈回來才算過。單針過關並不能預測多針也會過關。

### 步驟 3：多跳變數追蹤（RULER 風格）

```python
haystack = """X1 = 42. ... (filler) ... X2 = X1 + 10. ... (filler) ... X3 = X2 * 2."""
question = "What is X3?"
```

要答對就得把三個賦值串起來。前沿模型在 128k 上，這一項常常掉到 50-70% 的準確率。

### 步驟 4：把 LongBench v2 跑在你的堆疊上

```python
from datasets import load_dataset
longbench = load_dataset("THUDM/LongBench-v2")

def eval_model_on_longbench(model, subset="single-doc-qa"):
    tasks = [x for x in longbench["test"] if x["task"] == subset]
    correct = 0
    for x in tasks:
        answer = model.complete(x["context"] + "\n\nQ: " + x["question"], max_tokens=20)
        if normalize(answer) == normalize(x["answer"]):
            correct += 1
    return correct / len(tasks)
```

要分類別回報準確率。總計分數會把任務層級上的巨大差異藏起來。

## 常見陷阱

- **只跑 NIAH。** 在 1M 詞元上通過 NIAH，對多跳能力什麼都沒說。一定要再跑 RULER 或一套自訂的多跳測試。
- **深度取樣不均。** 很多實作只測 depth=0.5。要測 depth=0、0.25、0.5、0.75、1.0 —— 位置敏感度是真的存在，「中間遺失」也是真的。
- **針和填充內容有字面重疊。** 如果針跟填充內容共用關鍵字，檢索就變得毫無難度。改用 NoLiMa 風格、沒有字面重疊的針，讓填充內容真的是干擾項。
- **忽略延遲。** 1M 詞元的提示詞光是預填充就要 30-120 秒。準確率之外，也要量首個詞元的時間。
- **廠商自報的數字。** OpenAI、Google、Anthropic 都會發自家的分數。永遠要針對你自己的使用情境獨立重跑一次。

## 框架應用

2026 年的技術堆疊：

| 情境 | 基準測試 |
|-----------|-----------|
| 快速健檢 | 自訂 NIAH，3 個深度 × 3 個長度 |
| 生產環境的模型選型 | RULER（13 個任務），跑在你的目標長度上 |
| 真實世界的問答品質 | LongBench v2 的 single-doc-QA 子集 |
| 多跳推論 | BABILong 或自訂的變數追蹤 |
| 對話場景 | MRCR 8-needle，跑在你的目標長度上 |
| 模型升級的迴歸測試 | 固定的自建 NIAH + RULER 測試框架，每上一個新模型就跑一次 |

生產環境的經驗法則：在你打算用的那個長度上跑過 NIAH 加至少一個推論任務之前，永遠不要相信任何脈絡窗口的數字。

## 產出交付

存成 `outputs/skill-long-context-eval.md`：

```markdown
---
name: long-context-eval
description: Design a long-context evaluation battery for a given model and use case.
version: 1.0.0
phase: 5
lesson: 28
tags: [nlp, long-context, evaluation]
---

Given a target model, target context length, and use case, output:

1. Tests. NIAH depth × length grid; RULER multi-hop; custom domain task.
2. Sampling. Depths 0, 0.25, 0.5, 0.75, 1.0 at each length.
3. Metrics. Retrieval pass rate; reasoning pass rate; time-to-first-token; cost-per-query.
4. Cutoff. Effective retrieval length (90% pass) and effective reasoning length (70% pass). Report both.
5. Regression. Fixed harness, rerun on every model upgrade, surface deltas.

Refuse to trust a context window from the model card alone. Refuse NIAH-only evaluation for any multi-hop workload. Refuse vendor self-reported long-context scores as independent evidence.
```

## 練習

1. **簡單。** 做一套 NIAH，3 個深度（0.25、0.5、0.75）× 3 個長度（1k、4k、16k）。挑任何一個模型跑。把過關率畫成 3×3 熱圖。
2. **中等。** 加上 3 根針的變體。量每個長度下三根針全部撈到的比例。跟同一長度下的單針過關率比一比。
3. **困難。** 造一個變數追蹤任務（X1 → X2 → X3，共 3 跳），埋進 64k 的填充內容裡。量三個前沿模型的準確率。分別回報每個模型的有效推論長度。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| NIAH | 「大海撈針」 | 在填充內容裡埋一個事實，要模型把它撈出來。 |
| RULER | 「加強版的 NIAH」 | 13 種任務型態，橫跨檢索／多跳／聚合／問答。 |
| 有效脈絡長度 | 「真正的容量」 | 準確率還維持在門檻之上的那個長度。 |
| 中間遺失 | 「深度偏誤」 | 模型對長輸入中段的內容注意力不足。 |
| 多針測試 | 「一次好幾個事實」 | 埋進多個事實；測的是注意力的分身能力，不只是檢索。 |
| MRCR | 「多輪共指」 | 8、24 或 100 根針的共指解析；暴露注意力飽和的臨界點。 |
| NoLiMa | 「非字面的針」 | 針和查詢沒有共用任何字面詞元；必須靠推論。 |

## 延伸閱讀

- [Kamradt (2023). Needle in a Haystack analysis](https://github.com/gkamradt/LLMTest_NeedleInAHaystack) —— 最初的 NIAH 儲存庫。
- [Hsieh et al. (2024). RULER: What's the Real Context Size of Your Long-Context LMs?](https://arxiv.org/abs/2404.06654) —— 多任務的基準測試。
- [Bai et al. (2024). LongBench v2](https://arxiv.org/abs/2412.15204) —— 真實世界的長脈絡評估。
- [Modarressi et al. (2024). NoLiMa: Non-lexical needles](https://arxiv.org/abs/2404.06666) —— 更難的針。
- [Kuratov et al. (2024). BABILong](https://arxiv.org/abs/2406.10149) —— 在乾草堆裡推論。
- [Liu et al. (2024). Lost in the Middle: How Language Models Use Long Contexts](https://arxiv.org/abs/2307.03172) —— 深度偏誤那篇論文。
