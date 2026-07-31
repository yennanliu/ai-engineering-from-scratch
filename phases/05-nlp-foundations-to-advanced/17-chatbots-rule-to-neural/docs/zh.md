# 聊天機器人 —— 從規則式到神經網路再到 LLM 代理程式

> ELIZA 靠樣式比對回話。DialogFlow 對映意圖。GPT 憑權重作答。Claude 會呼叫工具並驗證結果。每一個世代解掉的，都是上一代最刺眼的失敗。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 13（問答系統）、階段 5 · 14（資訊檢索）
**時間：** 約 75 分鐘

## 問題所在

使用者說「我想改機位」。系統得弄清楚他要什麼、缺哪些資訊、怎麼把資訊問出來、以及怎麼把動作做完。接著使用者又說「等等，如果改成取消呢？」——系統必須記住上下文、切換任務，同時保住狀態。

對機器學習系統來說，對話很難。輸入是開放式的。輸出必須跨越很多輪都維持連貫。系統可能還得對真實世界動手（改機位、刷卡）。而每一步做錯，使用者都看得見。

聊天機器人架構歷經四個範式的輪替，每一個都是因為上一個失敗得太明顯才被推出來。本單元按順序走一遍。2026 年的生產環境樣貌，是後兩個範式的混合體。

## 核心概念

![聊天機器人的演進：規則式 → 檢索式 → 神經網路 → 代理程式](../assets/chatbot.svg)

### 腳本統治的半個世紀，1950-2001

第一個範式撐的不是五年，是五十年。認識它的軌跡很重要，因為這五十年裡的每一個系統都是同一台機器——比對輸入、吐出罐頭回應、順手更新一點狀態——而在這台機器上疊了五十年的規則，始終沒能做出通用解。那道天花板，就是範式二到四存在的理由。

**1950 年。** Turing 迴避了「機器能思考嗎？」，改提出一個可操作的替代問題：如果詰問者無法在電報打字機的另一端分辨機器與人，那個哲學問題就無關緊要了。對話成了這個領域的基準——而這個領域當時還沒有名字。

**1956 年。** 名字出現了。Dartmouth 的一場暑期研討會創造了「artificial intelligence」這個詞，前提假設是：智慧的每一項特徵「原則上都能被精確描述到讓機器足以模擬」。那份提案估算兩個月就能有實質進展。

**1966 年。** ELIZA 交出了你在步驟 1 會親手做的反射把戲：拆解規則從輸入裡抽出片段，重組規則再把片段當成問句丟回去。總共大約 200 條樣式，零狀態，零理解——而使用者照樣對它傾訴心事。Weizenbaum 後半輩子都對「這竟然只需要這麼少的機械」感到不安。

**1972 年。** PARRY 在史丹佛誕生，用來模擬偏執症，補上了 ELIZA 缺的那一塊：內部狀態。恐懼、憤怒、不信任各有一個數值變數，每一輪都會更新，並決定下一段腳本要開哪一支，所以同樣的輸入會因為前面的對話走向而得到不同回應。在一場盲測的逐字稿實驗中，精神科醫師區分 PARRY 與真人病患的正確率只有隨機水準。它是人格設定的直系祖先——一個用三個浮點數實作出來的系統提示詞。同一年，兩個機器人被架在 ARPANET 上互相對話：一支心理治療師腳本訪談一台偏執狀態機，這是網路上第一場機器人對機器人的對話。

**1995 年。** ALICE 用 AIML 把 ELIZA 的配方放大規模，AIML 是一種描述「樣式—模板」配對的 XML 方言。大約 40,000 條手寫類目，三座 Loebner Prize。它證明了規則式系統的規模法則：規則愈多，買到的是覆蓋率，永遠不是通用性。而每一條規則都是一筆得有人維護的負債。

**2001 年。** SmarterChild 把這套配方端到 3,000 萬名即時通訊使用者面前，並加上後端查詢——天氣、股價、電影時刻——再拼進模板裡。瞇著眼看，那就是穿著 2001 年戲服的工具呼叫：解析意圖、呼叫服務、把結果算繪進回覆。

五十年，一套機制，規則數不斷攀升。這個範式的終結，不是因為誰證明它錯了，而是因為手寫狀態機的維護成本隨覆蓋率線性成長，而使用者的期待則跟著他們上週看到的東西一起成長。

```figure
chatbot-lineage
```

**規則式（ELIZA、AIML、DialogFlow）。** 手工撰寫的樣式比對使用者輸入，產生回應。意圖分類器把請求導向預先定義好的流程。槽位填充狀態機負責蒐集必要資訊。在它被設計的那個狹窄範圍內表現極好，一出界就立刻壞掉。在不容許幻覺的安全關鍵領域（銀行身分驗證、航班訂票）至今仍在服役。

**檢索式。** 一套 FAQ 式的系統。把每一組（語句, 回應）配對都編碼起來。執行時把使用者訊息編碼，取出最接近的那條既有回應。想像 Zendesk 那個經典的「相似文章」功能。處理改寫的能力比規則好。因為不生成，所以不會幻覺。

**神經網路（seq2seq）。** 用對話紀錄訓練的編碼器—解碼器，從零生成回應。流暢，但很容易吐出空泛的輸出（「我不知道」）以及事實漂移。從來沒辦法可靠地待在題目上。這就是 Google、Facebook、Microsoft 在 2016-2019 年的聊天機器人都令人失望的原因。

**LLM 代理程式。** 一個語言模型，外面包一圈會規劃、呼叫工具、驗證結果的迴圈。它不是「提示詞很長的聊天機器人」，而是一個代理迴圈：規劃 → 呼叫工具 → 觀察結果 → 決定下一步。檢索優先的接地（RAG）讓它不至於幻覺。工具呼叫讓它真的能做事。這就是 2026 年的架構。

這四個範式不是一個接一個的替換。2026 年的生產級聊天機器人會同時走過四條路：身分驗證與破壞性動作走規則式，FAQ 走檢索，自然的措辭交給神經生成，模稜兩可的開放式查詢交給 LLM 代理程式。

## 動手實作

### 步驟 1：規則式樣式比對

```python
import re


class RulePattern:
    def __init__(self, pattern, response_template):
        self.regex = re.compile(pattern, re.IGNORECASE)
        self.template = response_template


PATTERNS = [
    RulePattern(r"my name is (\w+)", "Nice to meet you, {0}."),
    RulePattern(r"i (need|want) (.+)", "Why do you {0} {1}?"),
    RulePattern(r"i feel (.+)", "Why do you feel {0}?"),
    RulePattern(r"(.*)", "Tell me more about that."),
]


def rule_based_respond(user_input):
    for pattern in PATTERNS:
        m = pattern.regex.match(user_input.strip())
        if m:
            return pattern.template.format(*m.groups())
    return "I don't understand."
```

20 行的 ELIZA。那個反射把戲（"I feel sad" → "Why do you feel sad"）就是 Weizenbaum 1966 年那套經典的心理治療師示範。至今仍有教學價值。

### 步驟 2：檢索式（FAQ）

這段示意用的程式碼需要 `pip install sentence-transformers`（會一併拉進 torch）。本單元可實際執行的 `code/main.py` 改用標準函式庫實作的 Jaccard 相似度，所以不必安裝任何外部套件就能跑。

```python
from sentence_transformers import SentenceTransformer
import numpy as np


FAQ = [
    ("how do i reset my password", "Go to Settings > Security > Reset Password."),
    ("how do i cancel my order", "Go to Orders, find the order, click Cancel."),
    ("what is your return policy", "30-day returns on unused items, original packaging."),
]


encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
faq_questions = [q for q, _ in FAQ]
faq_embeddings = encoder.encode(faq_questions, normalize_embeddings=True)


def faq_respond(user_input, threshold=0.5):
    q_emb = encoder.encode([user_input], normalize_embeddings=True)[0]
    sims = faq_embeddings @ q_emb
    best = int(np.argmax(sims))
    if sims[best] < threshold:
        return None
    return FAQ[best][1]
```

以閾值決定要不要拒答，是這裡最關鍵的設計選擇。如果最佳匹配不夠接近，就回傳 `None`，讓系統往上升級處理。

### 步驟 3：神經生成（基準線）

用一個小型的指令微調編碼器—解碼器（FLAN-T5），或一個微調過的對話模型。在 2026 年，它單獨上生產環境是不可用的（自相矛盾、偏離主題、事實胡扯），但它會被裝在混合式系統裡負責把話說得自然。DialoGPT 那類純解碼器模型需要明確的輪次分隔符與 EOS 處理才能產生連貫的回覆；教學範例用 FLAN-T5 的 text2text pipeline 開箱就能跑。

```python
from transformers import pipeline

chatbot = pipeline("text2text-generation", model="google/flan-t5-small")

response = chatbot("Respond politely to: Hi there!", max_new_tokens=40)
print(response[0]["generated_text"])
```

### 步驟 4：LLM 代理迴圈

2026 年生產環境的形狀：

```python
def agent_loop(user_message, tools, llm, max_steps=5):
    history = [{"role": "user", "content": user_message}]
    for _ in range(max_steps):
        response = llm(history, tools=tools)
        tool_call = response.get("tool_call")
        if tool_call:
            tool_name = tool_call.get("name")
            args = tool_call.get("arguments")
            if not isinstance(tool_name, str) or tool_name not in tools:
                history.append({"role": "assistant", "tool_call": tool_call})
                history.append({"role": "tool", "name": str(tool_name), "content": f"error: unknown tool {tool_name!r}"})
                continue
            if not isinstance(args, dict):
                history.append({"role": "assistant", "tool_call": tool_call})
                history.append({"role": "tool", "name": tool_name, "content": f"error: arguments must be a dict, got {type(args).__name__}"})
                continue
            fn = tools[tool_name]
            result = fn(**args)
            history.append({"role": "assistant", "tool_call": tool_call})
            history.append({"role": "tool", "name": tool_name, "content": result})
        else:
            return response["content"]
    return "I could not complete the task in the step budget."
```

有三件事要點名。工具是 LLM 可以呼叫的函式。當 LLM 回傳最終答案而不是工具呼叫時，迴圈就結束。步驟預算則避免在模稜兩可的任務上無限迴圈。

真正的生產環境還要加上：檢索優先的接地（每次呼叫 LLM 之前先注入相關文件）、護欄（沒有確認就拒絕破壞性動作）、可觀測性（記錄每一步），以及評估（自動檢查代理程式的行為有沒有走出規格）。

### 步驟 5：混合式路由

```python
def hybrid_chat(user_input):
    if is_destructive_action(user_input):
        return structured_flow(user_input)

    faq_answer = faq_respond(user_input, threshold=0.6)
    if faq_answer:
        return faq_answer

    return agent_loop(user_input, tools, llm)


def is_destructive_action(text):
    danger_words = ["delete", "cancel", "charge", "refund", "transfer"]
    return any(w in text.lower() for w in danger_words)
```

樣式就是這樣：只要帶破壞性就走確定性規則，罐頭 FAQ 走檢索，其餘全部交給 LLM 代理程式。這就是 2026 年客服系統實際出貨的樣子。

## 框架應用

2026 年的技術堆疊：

| 使用場景 | 架構 |
|---------|---------------|
| 訂票、付款、身分驗證 | 規則式狀態機 + 槽位填充 |
| 客服 FAQ | 在人工整理過的答案上做檢索 |
| 開放式協助對話 | LLM 代理程式加 RAG + 工具呼叫 |
| 內部工具／IDE 助理 | LLM 代理程式加工具呼叫（搜尋、讀取、寫入） |
| 陪伴型／角色型聊天機器人 | 帶人格設定系統提示詞的調校過 LLM，知識部分靠檢索 |

生產環境永遠採用混合式路由。沒有任何單一架構能把每一種請求都處理好。而路由層本身通常就是一個小型的意圖分類器。

## 至今仍在出貨的失效模式

- **自信的編造。** LLM 代理程式聲稱它完成了一個其實沒做的動作。緩解做法：驗證結果、記錄工具呼叫、絕不讓 LLM 在沒有成功的工具回傳的情況下聲稱自己做了什麼。
- **提示詞注入。** 使用者塞進一段文字，覆寫掉系統提示詞。在 OWASP Top 10 for LLM Applications 2025 中排名 LLM01。有兩種口味：直接注入（貼進聊天視窗）與間接注入（藏在代理程式會讀到的文件、電子郵件或工具輸出裡）。

  攻擊成功率因情境而異。在通用工具使用與程式撰寫的基準上，前沿模型的實測成功率大約落在 0.5-8.5%。特定的高風險設定（針對 AI 程式撰寫代理程式的適應性攻擊、脆弱的協作編排）已達到約 84%。生產環境的 CVE 包括 EchoLeak（CVE-2025-32711，CVSS 9.3）——Microsoft 365 Copilot 上一個由攻擊者控制的電子郵件觸發、零點擊的資料外洩漏洞。

  緩解做法：在整個迴圈中都把使用者輸入視為不可信；呼叫工具前先清洗；把工具輸出與主提示詞隔離開；採用 Plan-Verify-Execute（PVE）模式，讓代理程式先規劃，再逐一對照計畫驗證每個動作才執行（這能阻止工具結果注入計畫外的新動作）；破壞性動作一律要求使用者確認；對工具權限範圍施行最小權限原則。

  再怎麼做提示詞工程，都無法完全消除這個風險。外部的執行期防禦層（LLM Guard、允許清單驗證、語意異常偵測）是必要的。
- **範圍蔓延。** 代理程式因為某次工具呼叫回傳了沾親帶故的資訊，就偏離了任務。緩解做法：收窄工具契約；讓系統提示詞保持聚焦；為偏題率加上評估。
- **無限迴圈。** 代理程式一直呼叫同一個工具。緩解做法：步驟預算、工具呼叫去重、用 LLM 當評審判斷「我們有在推進嗎」。
- **上下文視窗耗盡。** 長對話會把最早的幾輪推出上下文之外。緩解做法：把較舊的輪次摘要起來、用相似度檢索出相關的過往輪次，或改用長上下文模型。

## 產出交付

存成 `outputs/skill-chatbot-architect.md`：

```markdown
---
name: chatbot-architect
description: Design a chatbot stack for a given use case.
version: 1.0.0
phase: 5
lesson: 17
tags: [nlp, agents, chatbot]
---

Given a product context (user need, compliance constraints, available tools, data volume), output:

1. Architecture. Rule-based, retrieval, neural, LLM agent, or hybrid (specify which paths go where).
2. LLM choice if applicable. Name the model family (Claude, GPT-4, Llama-3.1, Mixtral). Match to tool-use quality and cost.
3. Grounding strategy. RAG sources, retrieval method (see lesson 14), tool contracts.
4. Evaluation plan. Task success rate, tool-call correctness, off-task rate, hallucination rate on held-out dialogs.

Refuse to recommend a pure-LLM agent for any destructive action (payments, account deletion, data modification) without a structured confirmation flow. Refuse to skip the prompt-injection audit if the agent has write access to anything.
```

## 練習

1. **簡單。** 把上面的規則式回應實作出來，為一家咖啡店的點餐機器人寫 10 條樣式。測試邊界情況：重複下單、修改訂單、取消、意圖不明。
2. **中等。** 做一個「FAQ + LLM 後備」的混合式系統。為一款 SaaS 產品準備 50 條罐頭 FAQ，LLM 後備則在文件網站上做檢索。用 100 個真實客服問題量測拒答率與正確率。
3. **困難。** 實作上面的代理迴圈，配三個工具（search、read-user-data、send-email）。用 50 個測試情境跑一次評估，其中要包含提示詞注入的嘗試。回報偏題率、任務失敗率，以及任何注入成功的案例。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 意圖 | 「使用者想幹什麼」 | 一個類別標籤（book_flight、reset_password），會被導向對應的處理器。 |
| 槽位 | 「一項資訊」 | 機器人需要的參數（日期、目的地）。槽位填充就是一連串的詢問。 |
| RAG | 「檢索加生成」 | 先取出相關文件，再讓 LLM 的回應以它們為依據。 |
| 工具呼叫 | 「呼叫函式」 | LLM 吐出一個結構化的呼叫，含名稱與參數。執行環境執行它並回傳結果。 |
| 代理迴圈 | 「規劃、行動、驗證」 | 一個控制器，交錯執行 LLM 呼叫與工具呼叫，直到任務完成。 |
| 提示詞注入 | 「使用者攻擊提示詞」 | 試圖覆寫系統提示詞的惡意輸入。 |

## 延伸閱讀

- [Turing (1950). Computing Machinery and Intelligence](https://academic.oup.com/mind/article/LIX/236/433/986238) —— 讓對話成為這個領域基準的那篇論文。
- [Weizenbaum (1966). ELIZA — A Computer Program For the Study of Natural Language Communication](https://web.stanford.edu/class/cs124/p36-weizenabaum.pdf) —— 規則式聊天機器人的原始論文。
- [Colby, Weber, Hilf (1971). Artificial Paranoia](https://doi.org/10.1016/0004-3702(71)90002-6) —— PARRY 的情感變數架構，第一個帶狀態的聊天機器人。
- [Thoppilan et al. (2022). LaMDA: Language Models for Dialog Applications](https://arxiv.org/abs/2201.08239) —— Google 神經聊天機器人時代晚期的論文，就在 LLM 代理程式接手之前。
- [Yao et al. (2022). ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) —— 為代理迴圈這個樣式命名的論文。
- [Anthropic's guide on building effective agents](https://www.anthropic.com/research/building-effective-agents) —— 2024 年的生產環境指引，2026 年依然成立。
- [Greshake et al. (2023). Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection](https://arxiv.org/abs/2302.12173) —— 提示詞注入的那篇論文。
- [OWASP Top 10 for LLM Applications 2025 — LLM01 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) —— 讓提示詞注入登上頭號安全隱憂的那份排名。
- [AWS — Securing Amazon Bedrock Agents against Indirect Prompt Injections](https://aws.amazon.com/blogs/machine-learning/securing-amazon-bedrock-agents-a-guide-to-safeguarding-against-indirect-prompt-injections/) —— 協作編排層的實務防禦，包含 Plan-Verify-Execute 與使用者確認流程。
- [EchoLeak (CVE-2025-32711)](https://www.vectra.ai/topics/prompt-injection) —— 由間接提示詞注入造成、零點擊資料外洩的經典 CVE。它是「有寫入權限的代理程式為何需要執行期防禦」的參考案例。
