# 對話狀態追蹤

> 「I want a cheap restaurant in the north... actually make it moderate... and add Italian.」三輪對話，三次狀態更新。對話狀態追蹤（DST）負責讓槽位—值字典保持同步，訂位才會成功。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 17（聊天機器人）、階段 5 · 20（結構化輸出）
**時間：** 約 75 分鐘

## 問題所在

在任務導向的對話系統裡，使用者的目標會被編碼成一組槽位—值配對：`{cuisine: italian, area: north, price: moderate}`。使用者的每一輪都可能新增、修改或移除一個槽位。系統必須讀完整段對話，然後正確輸出當前狀態。

只要錯一個槽位，系統就會訂錯餐廳、排錯航班，或刷錯卡。對話狀態追蹤是「使用者說了什麼」與「後端執行什麼」之間的那道樞紐。

即使有了 LLM，它在 2026 年依然重要的理由：

- 合規敏感的領域（銀行、醫療、航班訂票）需要確定性的槽位值，不是自由生成的文字。
- 使用工具的代理程式在呼叫 API 之前，仍然得先把槽位解析出來。
- 多輪對話裡的修正比看起來難得多：「actually no, make it Thursday.」

現代的流程是：古典的對話狀態追蹤概念 + LLM 抽取器 + 結構化輸出護欄。

## 核心概念

![對話狀態追蹤：對話歷史 → 槽位—值狀態](../assets/dst.svg)

**任務結構。** 一份 schema 定義了領域（restaurant、hotel、taxi）以及各自的槽位（cuisine、area、price、people）。每個槽位可以是空的、填入來自封閉集合的值（price: {cheap, moderate, expensive}），或填入自由形式的值（name: "The Copper Kettle"）。

**兩種對話狀態追蹤的表述方式。**

- **分類。** 對每一組（slot, candidate_value）配對預測是／否。適用於封閉詞彙的槽位。2020 年之前的標準做法。
- **生成。** 給定對話，把槽位值當成自由文字生成出來。適用於開放詞彙槽位。現代的預設做法。

**評估指標。** 聯合目標準確率（Joint Goal Accuracy, JGA）—— *每一個*槽位都正確的輪次比例。全對或全錯，沒有中間值。2026 年 MultiWOZ 2.4 排行榜的頂端大約在 83%。

**架構。**

1. **規則式（槽位正規表示式 + 關鍵字）。** 在狹窄領域裡是強力的基準線。可除錯。
2. **TripPy / BERT-DST。** 以 BERT 編碼的複製式生成。前 LLM 時代的標準。
3. **LDST（LLaMA + LoRA）。** 用領域—槽位提示詞做指令微調的 LLM。在 MultiWOZ 2.4 上達到 ChatGPT 等級的品質。
4. **無本體（2024–26）。** 跳過 schema，直接生成槽位名稱與值。能處理開放領域。
5. **提示詞 + 結構化輸出（2024–26）。** 搭配 Pydantic schema 與受限解碼的 LLM。5 行程式碼，可直接上生產環境。

### 那些經典的失效模式

- **跨輪次的指代。** 「Let's stay with the first option.」得先解析出那是哪一個選項。
- **覆寫還是附加。** 使用者說「add Italian.」你該替換 cuisine，還是把它附加上去？
- **隱含的確認。** 「OK cool」—— 這到底有沒有接受剛剛提供的訂位？
- **修正。** 「Actually make it 7 pm.」必須更新時間，同時不能清掉其他槽位。
- **指代前一輪系統語句。** 「Yes, that one.」哪一個「that」？

```figure
n5-slot-tracker
```

## 動手實作

### 步驟 1：規則式槽位抽取器

見 `code/main.py`。正規表示式加上同義詞字典，能覆蓋狹窄領域中 70% 的標準語句：

```python
CUISINE_SYNONYMS = {
    "italian": ["italian", "pasta", "pizza", "italy"],
    "chinese": ["chinese", "chow mein", "noodles"],
}


def extract_cuisine(utterance):
    for canonical, synonyms in CUISINE_SYNONYMS.items():
        if any(syn in utterance.lower() for syn in synonyms):
            return canonical
    return None
```

一出標準詞彙表就很脆弱。用在確定性的槽位確認上剛好。

### 步驟 2：狀態更新迴圈

```python
def update_state(state, utterance):
    new_state = dict(state)
    for slot, extractor in SLOT_EXTRACTORS.items():
        value = extractor(utterance)
        if value is not None:
            new_state[slot] = value
    for slot in NEGATION_CLEARS:
        if is_negated(utterance, slot):
            new_state[slot] = None
    return new_state
```

三條不變量：

- 使用者沒碰到的槽位，絕不重設。
- 明確的否定（「never mind the cuisine」）必須清空。
- 使用者的修正（「actually...」）必須覆寫，不是附加。

### 步驟 3：以 LLM 驅動、帶結構化輸出的對話狀態追蹤

```python
from pydantic import BaseModel
from typing import Literal, Optional
import instructor

class RestaurantState(BaseModel):
    cuisine: Optional[Literal["italian", "chinese", "indian", "thai", "any"]] = None
    area: Optional[Literal["north", "south", "east", "west", "center"]] = None
    price: Optional[Literal["cheap", "moderate", "expensive"]] = None
    people: Optional[int] = None
    day: Optional[str] = None


def llm_dst(history, llm):
    prompt = f"""You track the slot values of a restaurant booking across turns.
Dialogue so far:
{render(history)}

Update the state based on the latest user turn. Output only the JSON state."""
    return llm(prompt, response_model=RestaurantState)
```

Instructor 加 Pydantic 保證你拿到一個合法的狀態物件。不用正規表示式，不會 schema 對不上，也不會生出幻覺槽位。

### 步驟 4：JGA 評估

```python
def joint_goal_accuracy(predicted_states, gold_states):
    correct = sum(1 for p, g in zip(predicted_states, gold_states) if p == g)
    return correct / len(predicted_states)
```

用它來校準：系統把*所有*槽位都答對的輪次占多少比例？在 MultiWOZ 2.4 上，2026 年頂尖系統是 80-83%。你自己領域內的系統在你那套狹窄詞彙上應該要超過這個數字，否則 LLM 基準線就贏你了。

### 步驟 5：處理修正

```python
CORRECTION_CUES = {"actually", "no wait", "on second thought", "change that to"}


def is_correction(utterance):
    return any(cue in utterance.lower() for cue in CORRECTION_CUES)
```

一旦偵測到修正，就覆寫最近一次更新的槽位，而不是附加上去。沒有 LLM 幫忙的話很難做對。現代的樣式是：永遠讓 LLM 從歷史重新生成整份狀態，而不是增量更新——這樣自然就把修正處理掉了。

## 常見陷阱

- **全歷史重新生成的成本。** 每一輪都讓 LLM 重新生成狀態，總詞元量是 O(n²)。要限制歷史長度，或把較舊的輪次摘要起來。
- **Schema 漂移。** 事後追加新槽位會讓舊的訓練資料失效。給你的 schema 加上版本。
- **大小寫敏感。** "Italian" 與 "italian" 與 "ITALIAN" —— 每一處都要正規化。
- **隱含的繼承。** 如果使用者先前已經指定「for 4 people」，接著換一個時間的新請求不應該清掉 people。永遠把完整歷史傳進去。
- **自由形式與封閉集合。** 名稱、時間、地址需要自由形式的槽位；cuisine 與 area 則是封閉的。schema 裡兩種要混用。

## 框架應用

2026 年的技術堆疊：

| 情境 | 做法 |
|-----------|----------|
| 狹窄領域（一到兩個意圖） | 規則式 + 正規表示式 |
| 廣領域，有標註資料 | LDST（在 MultiWOZ 風格的資料上做 LLaMA + LoRA） |
| 廣領域，沒有標註，要能上線 | LLM + Instructor + Pydantic schema |
| 語音／口語 | ASR + 正規化器 + LLM 對話狀態追蹤 |
| 多領域訂位流程 | schema 引導的 LLM，每個領域一份 Pydantic 模型 |
| 合規敏感 | 規則式為主，LLM 為備，搭配確認流程 |

## 產出交付

存成 `outputs/skill-dst-designer.md`：

```markdown
---
name: dst-designer
description: Design a dialogue state tracker — schema, extractor, update policy, evaluation.
version: 1.0.0
phase: 5
lesson: 29
tags: [nlp, dialogue, task-oriented]
---

Given a use case (domain, languages, vocab openness, compliance needs), output:

1. Schema. Domain list, slots per domain, open vs closed vocabulary per slot.
2. Extractor. Rule-based / seq2seq / LLM-with-Pydantic. Reason.
3. Update policy. Regenerate-whole-state / incremental; correction handling; negation handling.
4. Evaluation. Joint Goal Accuracy on a held-out dialogue set, slot-level precision/recall, confusion on the hardest slot.
5. Confirmation flow. When to explicitly ask the user to confirm (destructive actions, low-confidence extractions).

Refuse LLM-only DST for compliance-sensitive slots without a rule-based secondary check. Refuse any DST that cannot roll back a slot on user correction. Flag schemas without version tags.
```

## 練習

1. **簡單。** 在 `code/main.py` 裡為 3 個槽位（cuisine、area、price）做出規則式狀態追蹤器。用 10 段手寫對話測試。量測 JGA。
2. **中等。** 同一份資料集改用 Instructor + Pydantic + 一個小型 LLM。比較 JGA。檢視最難的那幾輪。
3. **困難。** 兩種都實作並做路由：規則式為主，當規則式產出少於 2 個有信心的槽位時退回 LLM。量測合併後的 JGA 以及每輪的推論成本。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| DST | 對話狀態追蹤 | 在對話的各輪之間維護槽位—值字典。 |
| 槽位 | 「使用者意圖的一個單位」 | 後端需要的具名參數（cuisine、date）。 |
| 領域 | 「任務範圍」 | restaurant、hotel、taxi —— 一組組槽位。 |
| JGA | 聯合目標準確率 | 每一個槽位都正確的輪次比例。全對或全錯。 |
| MultiWOZ | 「那個基準」 | 多領域的 Wizard-of-Oz 資料集；對話狀態追蹤的標準評估。 |
| 無本體 DST | 「不用 schema」 | 直接生成槽位名稱與值，沒有固定清單。 |
| 修正 | 「Actually...」 | 會覆寫先前已填槽位的那一輪。 |

## 延伸閱讀

- [Budzianowski et al. (2018). MultiWOZ — A Large-Scale Multi-Domain Wizard-of-Oz](https://arxiv.org/abs/1810.00278) —— 這個領域的標準基準。
- [Feng et al. (2023). Towards LLM-driven Dialogue State Tracking (LDST)](https://arxiv.org/abs/2310.14970) —— 用 LLaMA + LoRA 做對話狀態追蹤的指令微調。
- [Heck et al. (2020). TripPy — A Triple Copy Strategy for Value Independent Neural Dialog State Tracking](https://arxiv.org/abs/2005.02877) —— 複製式對話狀態追蹤的主力方法。
- [King, Flanigan (2024). Unsupervised End-to-End Task-Oriented Dialogue with LLMs](https://arxiv.org/abs/2404.10753) —— 基於 EM 的無監督任務導向對話。
- [MultiWOZ leaderboard](https://github.com/budzianowski/multiwoz) —— 對話狀態追蹤的標準結果。
