# 機器翻譯

> 翻譯是那個養了 NLP 研究三十年、現在還在養它的任務。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 5 · 10（注意力機制）、階段 5 · 04（GloVe、FastText 與子詞）
**時間：** 約 75 分鐘

## 問題所在

模型讀進一種語言的句子，產出另一種語言的句子。長度會變。詞序會變。有些來源詞對應到多個目標詞，反過來也一樣。慣用語拒絕一對一映射。「I miss you」在法文是「tu me manques」——字面上是「你對我而言是缺席的」。任何詞層級的對齊都撐不過這一句。

機器翻譯正是那個逼著 NLP 發明編碼器解碼器、注意力機制、transformer，最後催生出整個 LLM 範式的任務。每一次向前的進展之所以到來，都是因為翻譯品質可以量測，而人與機器之間的差距又頑固得離譜。

本單元跳過歷史課，直接教 2026 年真正在運作的流程：預訓練的多語言編碼器解碼器（NLLB-200 或 mBART）、子詞分詞、beam search、BLEU 與 chrF 評估，以及少數幾種至今仍會沒被攔住就上線的失效模式。

## 核心概念

![機器翻譯流程：分詞 → 編碼 → 帶注意力的解碼 → 還原文字](../assets/mt-pipeline.svg)

現代機器翻譯是一個在平行語料上訓練的 transformer 編碼器解碼器。編碼器以來源語言自己的分詞方式讀入來源句。解碼器透過交叉注意力（單元 10）用上編碼器的輸出，一次生成一個目標子詞。解碼採用 beam search，以避開貪婪解碼的陷阱。輸出再經過還原分詞、還原大小寫，並與參考譯文比對評分。

有三個操作面的選擇決定了真實世界的機器翻譯品質。

- **分詞器。** 在混合語言語料上訓練的 SentencePiece BPE。跨語言共用一份詞彙表，正是 NLLB 能做到零樣本語言對的原因。
- **模型大小。** NLLB-200 蒸餾版 600M 塞得進一台筆電。NLLB-200 3.3B 是官方公布的生產環境預設。54.5B 是研究上的天花板。
- **解碼。** 一般內容用 beam 寬度 4-5。加上長度懲罰，避免輸出太短。需要術語一致時，用受約束解碼。

```figure
seq2seq-alignment
```

## 動手實作

### 步驟 1：呼叫一個預訓練的機器翻譯模型

```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

model_id = "facebook/nllb-200-distilled-600M"
tok = AutoTokenizer.from_pretrained(model_id, src_lang="eng_Latn")
model = AutoModelForSeq2SeqLM.from_pretrained(model_id)

src = "The cats are running."
inputs = tok(src, return_tensors="pt")

out = model.generate(
    **inputs,
    forced_bos_token_id=tok.convert_tokens_to_ids("fra_Latn"),
    num_beams=5,
    length_penalty=1.0,
    max_new_tokens=64,
)
print(tok.batch_decode(out, skip_special_tokens=True)[0])
```

```text
Les chats courent.
```

這裡有三件事要緊。`src_lang` 告訴分詞器要套用哪一種文字系統與切分方式。`forced_bos_token_id` 告訴解碼器要生成哪一種語言。兩者都是 NLLB 專屬的招數；mBART 與 M2M-100 各有自己的慣例，彼此不能互換。

### 步驟 2：BLEU 與 chrF

BLEU 量測輸出與參考譯文之間的 n-gram 重疊。四種參考 n-gram 大小（1-4）、各精確率的幾何平均，以及對過短輸出的簡短懲罰。分數落在 [0, 100]。很常用，卻很難解讀：30 BLEU 是「堪用」；40 是「好」；50 是「出色」；差距小於 1 BLEU 的都是雜訊。

chrF 量測字元層級的 F 分數。對形態豐富的語言更敏感——BLEU 在那些語言上會低估匹配。通常會與 BLEU 一起回報。

```python
import sacrebleu

hypotheses = ["Les chats courent."]
references = [["Les chats courent."]]

bleu = sacrebleu.corpus_bleu(hypotheses, references)
chrf = sacrebleu.corpus_chrf(hypotheses, references)
print(f"BLEU: {bleu.score:.1f}  chrF: {chrf.score:.1f}")
```

永遠用 `sacrebleu`。它會把分詞正規化，讓分數在不同論文之間可以互相比較。自己土炮一份 BLEU 計算，正是誤導性基準測試的由來。

### 三層評估指標體系（2026）

現代機器翻譯評估使用三個互補的評估指標家族。上線時至少用其中兩種。

- **啟發式**（BLEU、chrF）。快、依賴參考譯文、可解讀，但對改寫不敏感。用於與舊有結果比較，以及偵測回歸。
- **學習式**（COMET、BLEURT、BERTScore）。以人工評分訓練出來的神經網路模型；比較譯文與來源、參考譯文之間的語意相似度。COMET 自 2023 年起與機器翻譯研究的關聯度最高，也是 2026 年在乎品質時的生產環境預設。
- **LLM 當評審**（不需參考譯文）。提示一個大模型，就流暢度、忠實度、語氣與文化適切性給譯文評分。評分準則設計得好時，GPT-4 當評審與人類判斷的一致率約 80%。用於沒有參考譯文的開放式內容。

2026 年的務實組合：`sacrebleu` 算 BLEU 與 chrF、`unbabel-comet` 算 COMET，再加一個被提示過的 LLM 作為最終面向人的訊號。在把任何評估指標拿去信任生產資料之前，先用 50-100 個人工標註的例子校正它。

不需參考譯文的評估指標（COMET-QE、BLEURT-QE、LLM 當評審）讓你在沒有參考譯文的情況下也能評估翻譯，這對長尾的低資源語言對很重要——那些語言對根本不存在參考譯文。

### 步驟 3：生產環境裡會壞掉的東西

上面那套能運作的流程，八成時間會翻得很流暢，剩下兩成則無聲地失敗。有名字的失效模式：

- **幻覺。** 模型憑空生出來源裡沒有的內容。在不熟悉的領域詞彙上很常見。症狀：輸出很流暢，卻聲稱了來源沒說過的事實。緩解方式：對領域術語做受約束解碼、對受規範內容做人工審查、監控輸出遠長於輸入的情況。
- **翻錯語言。** 模型翻成了錯的語言。NLLB 在罕見的低資源語言對上出乎意料地容易犯這個錯。緩解方式：確認 `forced_bos_token_id`，並且一律用語言辨識模型檢查輸出。
- **術語漂移。** 「Sign up」在文件 1 變成「s'inscrire」，在文件 2 變成「créer un compte」。對 UI 文字與面向使用者的字串來說，一致性比原始品質更重要。緩解方式：以詞彙表約束解碼，或用譯後編輯詞典。
- **敬語層級不匹配。** 法文的「tu」與「vous」、日文的敬語層級。模型會挑訓練資料裡比較常見的那一種。對面向客戶的內容而言，這通常是錯的。緩解方式：如果模型支援，就在提示詞前面加一個敬語層級的詞元；或者用只含正式語體的語料微調一個小模型。
- **短輸入的長度爆炸。** 非常短的來源句常常產出過長的譯文，因為長度懲罰在來源不到約 5 個詞元時會直接崩掉。緩解方式：設一個與來源長度成比例的硬性最大長度上限。

### 步驟 4：針對領域做微調

預訓練模型是通才。法律、醫療或遊戲對白的翻譯，在領域平行語料上微調後會有可量測的收穫。配方並不神秘：

```python
from transformers import Trainer, TrainingArguments
from datasets import Dataset

pairs = [
    {"src": "The defendant pleaded guilty.", "tgt": "L'accusé a plaidé coupable."},
]

ds = Dataset.from_list(pairs)


def preprocess(ex):
    return tok(
        ex["src"],
        text_target=ex["tgt"],
        truncation=True,
        max_length=128,
        padding="max_length",
    )


ds = ds.map(preprocess, remove_columns=["src", "tgt"])

args = TrainingArguments(output_dir="out", per_device_train_batch_size=4, num_train_epochs=3, learning_rate=3e-5)
Trainer(model=model, args=args, train_dataset=ds).train()
```

幾千筆高品質的平行語料，勝過幾十萬筆從網路爬來的雜訊語料。訓練資料的品質是生產環境裡最大的那一根槓桿。

## 框架應用

2026 年機器翻譯的生產環境組合：

| 使用情境 | 建議的起點 |
|---------|---------------------------|
| 任意語言互譯、200 種語言 | `facebook/nllb-200-distilled-600M`（筆電）或 `nllb-200-3.3B`（生產環境） |
| 以英文為中心、高品質、50 種語言 | `facebook/mbart-large-50-many-to-many-mmt` |
| 短量執行、推論便宜、英文對法／德／西 | Helsinki-NLP／Marian 模型 |
| 對延遲敏感、跑在瀏覽器端 | ONNX 量化的 Marian（約 50 MB） |
| 追求最高品質、願意付錢 | GPT-4／Claude／Gemini 搭配翻譯提示詞 |

到 2026 年，LLM 在好幾個語言對上已經勝過專用的機器翻譯模型，尤其是慣用語內容與長脈絡。代價是每詞元成本與延遲。當脈絡長度、風格一致性，或靠提示詞做領域適配比吞吐量更重要時，就選 LLM。

## 產出交付

存成 `outputs/skill-mt-evaluator.md`：

```markdown
---
name: mt-evaluator
description: Evaluate a machine translation output for shipping.
version: 1.0.0
phase: 5
lesson: 11
tags: [nlp, translation, evaluation]
---

Given a source text and a candidate translation, output:

1. Automatic score estimate. BLEU and chrF ranges you would expect. State whether a reference is available.
2. Five-point human-verifiable check list: (a) content preservation (no hallucinations), (b) correct language, (c) register / formality match, (d) terminology consistency with glossary if provided, (e) no truncation or length explosion.
3. One domain-specific issue to probe. E.g., for legal: named entities and statute citations. For medical: drug names and dosages. For UI: placeholder variables `{name}`.
4. Confidence flag. "Ship" / "Ship with review" / "Do not ship". Tie to the severity of issues found in step 2.

Refuse to ship a translation without a language-ID check on output. Refuse to evaluate without a reference unless the user explicitly opts in to reference-free scoring (COMET-QE, BLEURT-QE). Flag any content over 1000 tokens as likely needing chunked translation.
```

## 練習

1. **簡單。** 用 `nllb-200-distilled-600M` 把一段 5 句的英文段落翻成法文，再回譯成英文。量測這趟來回與原文有多接近。你應該會看到語意保留下來，但用詞出現漂移。
2. **中等。** 用 `fasttext lid.176` 或 `langdetect` 為翻譯輸出實作語言辨識檢查。把它整合進機器翻譯的呼叫裡，讓翻錯語言的輸出在回傳前就被攔下來。
3. **困難。** 在你自選的 5,000 組配對領域語料上微調 `nllb-200-distilled-600M`。在另外保留的測試集上量測微調前後的 BLEU。回報哪些類型的句子變好了、哪些退步了。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| BLEU | 「翻譯分數」 | 帶簡短懲罰的 n-gram 精確率。落在 [0, 100]。 |
| chrF | 「字元 F 分數」 | 字元層級的 F 分數。對形態豐富的語言更敏感。 |
| NMT | 「神經機器翻譯」 | 在平行語料上訓練的 transformer 編碼器解碼器。2017 年以後的預設做法。 |
| NLLB | 「No Language Left Behind」 | Meta 的 200 語言機器翻譯模型家族。 |
| 受約束解碼 | 「可控的輸出」 | 強制特定詞元或 n-gram 出現／不出現在輸出裡。 |
| 幻覺 | 「憑空生出來的內容」 | 模型輸出中沒有來源支持的部分。 |

## 延伸閱讀

- [Costa-jussà et al. (2022). No Language Left Behind: Scaling Human-Centered Machine Translation](https://arxiv.org/abs/2207.04672) —— NLLB 論文。
- [Post (2018). A Call for Clarity in Reporting BLEU Scores](https://aclanthology.org/W18-6319/) —— 為什麼 `sacrebleu` 是回報 BLEU 唯一正確的方式。
- [Popović (2015). chrF: character n-gram F-score for automatic MT evaluation](https://aclanthology.org/W15-3049/) —— chrF 論文。
- [Hugging Face MT guide](https://huggingface.co/docs/transformers/tasks/translation) —— 實務微調走一遍。
