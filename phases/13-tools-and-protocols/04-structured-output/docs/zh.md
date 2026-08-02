# 結構化輸出 —— JSON Schema、Pydantic、Zod、受限解碼

> 「好聲好氣地請模型回傳 JSON」有 5% 到 15% 的失敗率，就算是前沿模型也一樣。結構化輸出用受限解碼補上這道落差：模型會被實實在在地阻止吐出任何違反 schema 的詞元。OpenAI 的嚴格模式、Anthropic 帶 schema 定型的工具使用、Gemini 的 `responseSchema`、Pydantic AI 的 `output_type`，以及 Zod 的 `.parse`，是同一個想法的五種表面形式。這一課會做出 schema 驗證器與嚴格模式契約，往後每一條生產級抽取管線學習者都會用到。

**類型：** 實作
**程式語言：** Python (stdlib, JSON Schema 2020-12 subset)
**先修單元：** 階段 13 · 02（函數呼叫深入剖析）
**時間：** 約 75 分鐘

## 學習目標

- 用對的約束（enum、min/max、required、pattern）為一個抽取目標寫出 JSON Schema 2020-12。
- 說明為什麼嚴格模式與受限解碼，給出的保證與「生成後再驗證」不同。
- 區分三種失敗模式：解析錯誤、schema 違規、模型拒絕。
- 出貨一條帶定型修復與定型拒絕處理的抽取管線。

## 問題所在

一個在讀採購單郵件的代理，得把自由文字變成 `{customer, line_items, total_usd}`。有三種做法。

**做法一：用提示詞要求 JSON。** 「請用 JSON 回覆，欄位為 customer、line_items、total_usd。」在前沿模型上有 85% 到 95% 的成功率。它會以六種方式失敗：漏了大括號、多餘逗號、型別錯誤、幻覺欄位、在詞元上限處被截斷，以及漏出像「以下是您的 JSON：」這樣的散文。

**做法二：生成後再驗證。** 自由生成、解析、對照 schema 驗證、失敗就重試。可靠但昂貴 —— 每次重試你都要付費，而截斷型 bug 每發生一次就多花一輪。

**做法三：受限解碼。** 供應商在解碼時就強制 schema。無效的詞元會從取樣分布中被遮蔽掉。輸出保證能解析，也保證通過驗證。失敗只塌縮成一種模式：拒絕（模型判定這份輸入不適合這個 schema）。

2026 年的每家前沿供應商，都出貨了某種形式的做法三。

- **OpenAI。** `response_format: {type: "json_schema", strict: true}`，並在模型婉拒時於回應中附上 `refusal`。
- **Anthropic。** 在 `tool_use` 的輸入上強制 schema；沒有 `stop_reason: "refusal"` 這種東西，但沒帶工具呼叫的 `end_turn` 就是那個訊號。
- **Gemini。** 請求層級的 `responseSchema`；2026 年 Gemini 為選定的型別出貨了詞元層級的文法約束。
- **Pydantic AI。** `output_type=InvoiceModel` 會吐出一個定型為 `InvoiceModel` 的結構化 `RunResult`。
- **Zod（TypeScript）。** 一個對照 Zod schema 驗證供應商輸出的執行期解析器；與 OpenAI 的 `beta.chat.completions.parse` 搭配使用。

共通的主線是：schema 宣告一次，從頭到尾強制執行。

## 核心概念

### JSON Schema 2020-12 —— 通用語

每家供應商都接受 JSON Schema 2020-12。你最常用到的構件有：

- `type`：`object`、`array`、`string`、`number`、`integer`、`boolean`、`null` 之一。
- `properties`：欄位名稱到子 schema 的映射。
- `required`：必須出現的欄位名稱清單。
- `enum`：允許值的封閉集合。
- `minimum`／`maximum`（數字）、`minLength`／`maxLength`／`pattern`（字串）。
- `items`：套用到每個陣列元素的子 schema。
- `additionalProperties`：設 `false` 就禁止額外欄位（預設值依模式而異）。

OpenAI 的嚴格模式多加三項要求：每個屬性都必須列進 `required`、所有層級都要 `additionalProperties: false`，且不得有未解析的 `$ref`。違反這些，API 會在請求時就回 400。

### Pydantic，Python 這一側的繫結

Pydantic v2 透過 `model_json_schema()`，從 dataclass 形狀的模型生成 JSON Schema。Pydantic AI 把這一層包起來，讓你只要寫：

```python
class Invoice(BaseModel):
    customer: str
    line_items: list[LineItem]
    total_usd: Decimal
```

代理框架就會在邊緣把這份 schema 翻譯成 OpenAI 的嚴格模式、Anthropic 的 `input_schema`，或 Gemini 的 `responseSchema`。模型的輸出會以一個定型的 `Invoice` 實例回來。驗證錯誤則拋出帶定型錯誤路徑的 `ValidationError`。

### Zod，TypeScript 這一側的繫結

Zod（`z.object({customer: z.string(), ...})`）是 TS 的對應物。OpenAI 的 Node SDK 暴露了 `zodResponseFormat(Invoice)`，會把它翻譯成 API 的 JSON Schema 酬載。

### 拒絕

嚴格模式沒辦法逼模型作答。如果輸入塞不進那個 schema（「這封郵件是一首詩，不是發票」），模型就會吐出一個內含理由的 `refusal` 欄位。你的程式碼必須把它當成一等的結果來處理，而不是當成失敗。這個拒絕也是有用的安全訊號：當你要求模型從一封受保護內容的郵件中抽出信用卡號時，它會回傳一個附帶安全理由的拒絕。

### 開放權重世界裡的受限解碼

開放權重的實作用三種技巧。

1. **基於文法的解碼**（`outlines`、`guidance`、`lm-format-enforcer`）：從 schema 建出一個確定性有限自動機；在每一步遮蔽掉那些會違反該 FSM 的詞元 logits。
2. **搭配 JSON 解析器的 logit 遮蔽**：讓一個串流 JSON 解析器與模型同步前進；在每一步算出合法的下一詞元集合。
3. **搭配驗證器的推測式解碼**：便宜的草稿模型提出詞元，驗證器強制 schema。

商用供應商會在幕後挑其中一種。2026 年的技術水準是：短的結構化輸出比純生成更快，長的則速度相當。

### 三種失敗模式

1. **解析錯誤。** 輸出不是有效的 JSON。在嚴格模式下不可能發生。在非嚴格的供應商上仍會發生。
2. **schema 違規。** 輸出解析得了，但違反 schema。在嚴格模式下不可能發生。在嚴格模式之外很常見。
3. **拒絕。** 模型婉拒。必須當成一種定型的結果來處理。

### 重試策略

當你不在嚴格模式時（Anthropic 的工具使用、非嚴格的 OpenAI、較舊的 Gemini），復原的模式是：

```
generate -> parse -> validate -> if fail, inject error and retry, max 3x
```

重試一次通常就夠了。重試三次能抓住弱模型的偶發抖動。超過三次就是 schema 有問題的徵兆：模型對某些輸入根本滿足不了它，該修的是提示詞或 schema。

### 小模型的支援

受限解碼在小模型上也管用。一個帶文法強制的 30 億參數開放模型，在結構化任務上勝過一個純靠提示詞的 700 億參數模型。這正是結構化輸出對生產環境如此重要的主因：它把可靠性與模型大小解耦了。

## 框架應用

`code/main.py` 用 stdlib 出貨了一個最小的 JSON Schema 2020-12 驗證器（型別、required、enum、min/max、pattern、items、additionalProperties）。它包住一份 `Invoice` schema，並把一段假的 LLM 輸出送過驗證器，展示解析錯誤、schema 違規與拒絕三條路徑。到了生產環境，把那段假輸出換成任何供應商的真實回應即可。

要看的地方有：

- 驗證器回傳一份帶路徑與訊息的定型 `[ValidationError]` 清單。那正是你想呈現給重試提示詞的形狀。
- 拒絕那條分支「不」會重試。它會記錄下來並回傳一個定型的拒絕。階段 14 · 09 會把拒絕當成安全訊號使用。
- `additionalProperties: false` 的檢查會在那筆對抗性測試輸入上觸發，顯示嚴格模式為什麼能對幻覺欄位關上大門。

## 產出交付

這一課產出 `outputs/skill-structured-output-designer.md`。給定一個自由文字的抽取目標（發票、客服工單、履歷等等），這項技能會產出一份相容於嚴格模式的 JSON Schema 2020-12，以及一個與之對映的 Pydantic 模型，並附上定型拒絕與重試處理的樁。

## 練習

1. 跑一次 `code/main.py`。加上第四筆測試案例，其 `total_usd` 是負數。確認驗證器會以 `minimum` 約束的路徑拒絕它。

2. 擴充驗證器以支援帶鑑別欄位的 `oneOf`。常見情境是：`line_item` 要嘛是商品、要嘛是服務，以 `kind` 標記。嚴格模式在這裡有些微妙的規則；查一下 OpenAI 的結構化輸出指南。

3. 把同一份 Invoice schema 寫成一個 Pydantic BaseModel，並把 `model_json_schema()` 的輸出與你手寫的 schema 比較。找出那個 Pydantic 預設會設、而手寫版漏掉的欄位。

4. 量測拒絕率。造出十筆不該被抽取的輸入（一段歌詞、一份數學證明、一封空白郵件），用嚴格模式送進一家真實的供應商。數一數拒絕與幻覺輸出各有幾次。這就是你做拒絕感知重試時的基準真值。

5. 把 OpenAI 的結構化輸出指南從頭讀到尾。找出那個純 JSON Schema 允許、但它在嚴格模式下明文禁止的構件。接著設計一份非必要地用上了該構件的 schema，再把它重構成相容嚴格模式的版本。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| JSON Schema 2020-12 | 「那份 schema 規格」 | 每家現代供應商都在說的 IETF 草案 schema 方言 |
| 嚴格模式 | 「保證合 schema」 | OpenAI 的旗標，透過受限解碼強制 schema |
| 受限解碼 | 「logit 遮蔽」 | 在解碼時強制執行，遮蔽掉無效的下一個詞元 |
| 拒絕 | 「模型婉拒」 | 當輸入塞不進 schema 時的定型結果 |
| 解析錯誤 | 「無效的 JSON」 | 輸出無法解析成 JSON；在嚴格模式下不可能發生 |
| schema 違規 | 「形狀不對」 | 解析得了，但違反了型別／required／enum／範圍 |
| `additionalProperties: false` | 「不准有多的」 | 禁止未知欄位；OpenAI 嚴格模式的必要條件 |
| Pydantic BaseModel | 「定型輸出」 | 能吐出並驗證 JSON Schema 的 Python 類別 |
| Zod schema | 「TypeScript 的輸出型別」 | 用來驗證供應商輸出的 TS 執行期 schema |
| 文法強制 | 「開放權重的受限解碼」 | 基於 FSM 的 logit 遮蔽，如 outlines／guidance 所做 |

## 延伸閱讀

- [OpenAI — Structured outputs](https://platform.openai.com/docs/guides/structured-outputs) —— 嚴格模式、拒絕與 schema 要求
- [OpenAI — Introducing structured outputs](https://openai.com/index/introducing-structured-outputs-in-the-api/) —— 2024 年 8 月的發布文，說明那份解碼保證
- [Pydantic AI — Output](https://ai.pydantic.dev/output/) —— 可序列化到各家供應商的定型 output_type 繫結
- [JSON Schema — 2020-12 release notes](https://json-schema.org/draft/2020-12/release-notes) —— 權威規格
- [Microsoft — Structured outputs in Azure OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) —— 企業部署筆記與嚴格模式的注意事項
