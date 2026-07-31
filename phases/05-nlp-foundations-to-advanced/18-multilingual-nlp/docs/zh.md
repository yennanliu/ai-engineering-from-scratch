# 多語言 NLP

> 一個模型、100 種以上語言，而其中大多數語言的訓練資料是零。跨語言遷移是 2020 年代真正管用的奇蹟。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 04（GloVe、FastText 與子詞）、階段 5 · 11（機器翻譯）
**時間：** 約 45 分鐘

## 問題所在

英文有數十億筆標註過的例子。烏爾都語有幾千筆。邁蒂利語幾乎沒有。任何要服務全球使用者的實用 NLP 系統，都得在那條長尾上運作——那裡根本不存在針對任務的訓練資料。

多語言模型的解法是：同時用很多語言訓練同一個模型。共享的表徵讓模型能把在高資源語言上學到的能力，遷移到低資源語言上。你在英文情感分析上微調模型，它就能對烏爾都語直接產出好得出乎意料的情感預測。這就是零樣本跨語言遷移，它重塑了 NLP 交付到全世界的方式。

本單元把取捨、幾個經典模型，以及一個讓初次接觸多語言工作的團隊踩坑的決定講清楚：怎麼挑遷移用的來源語言。

## 核心概念

![透過共享的多語言嵌入空間完成跨語言遷移](../assets/multilingual.svg)

**共享詞彙表。** 多語言模型使用一個在所有目標語言文本上訓練出來的 SentencePiece 或 WordPiece 分詞器。詞彙表是共用的：同一個子詞單元在相近語言之間代表同一個語素。英文和義大利文的 `anti-` 會拿到同一個詞元。

**共享表徵。** 一個跨多語言以遮罩語言模型預訓練的 transformer，會學到不同語言中語意相近的句子會產生相近的隱藏狀態。mBERT、XLM-R 與 NLLB 都表現出這個性質。英文「cat」的嵌入會聚在法文「chat」與西班牙文「gato」附近，整句層級的嵌入也一樣。

**零樣本遷移。** 在某一種語言（通常是英文）的標註資料上微調模型。推論時，直接拿去跑模型支援的任何其他語言。不需要目標語言的標註。對類型學上相近的語言結果很強，對距離遠的語言就比較弱。

**少樣本微調。** 加進 100-500 筆目標語言的標註例子。在分類任務上，準確率會跳到英文基線的 95-98%。這是多語言 NLP 裡性價比最高的那一根槓桿。

## 模型一覽

| 模型 | 年份 | 涵蓋範圍 | 說明 |
|-------|------|----------|-------|
| mBERT | 2018 | 104 種語言 | 用 Wikipedia 訓練。第一個實用的多語言語言模型。在低資源語言上很弱。 |
| XLM-R | 2019 | 100 種語言 | 用 CommonCrawl 訓練（比 Wikipedia 大得多）。定義了跨語言的基線。Base 270M、Large 550M。 |
| XLM-V | 2023 | 100 種語言 | 詞彙表擴到 100 萬詞元的 XLM-R（原本是 25 萬）。在低資源語言上更好。 |
| mT5 | 2020 | 101 種語言 | 用於多語言生成的 T5 架構。 |
| NLLB-200 | 2022 | 200 種語言 | Meta 的翻譯模型；含 55 種低資源語言。 |
| BLOOM | 2022 | 46 種語言 + 13 種程式語言 | 以多語言方式訓練的開放 176B LLM。 |
| Aya-23 | 2024 | 23 種語言 | Cohere 的多語言 LLM。在阿拉伯語、印地語、史瓦希里語上很強。 |

按使用情境挑。分類任務用 XLM-R-base 當合理的預設就很好。生成任務則看是翻譯還是開放式生成，分別找 mT5 或 NLLB。LLM 風格的工作，搭 Aya-23 或 Claude 並明確做多語言提示。

## 來源語言的決定（2026 年的研究）

大多數團隊預設拿英文當微調的來源。近期研究（2026）顯示這常常是錯的。

語言相似度比語料的原始大小更能預測遷移品質。對斯拉夫語系的目標語言，德文或俄文常常勝過英文。對印度語系的目標語言，印地語常常勝過英文。**qWALS** 相似度指標（2026，以 World Atlas of Language Structures 的特徵為基礎）把這件事量化了。**LANGRANK**（Lin et al., ACL 2019）是另一個更早的方法，它結合語言相似度、語料大小與親緣關係，替候選來源語言排序。

務實的規則：如果你的目標語言有一個類型學上相近的高資源親戚，先試著在那一個上面微調，再跟英文微調的結果比。

## 動手實作

### 步驟 1：零樣本跨語言分類

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

tok = AutoTokenizer.from_pretrained("joeddav/xlm-roberta-large-xnli")
model = AutoModelForSequenceClassification.from_pretrained("joeddav/xlm-roberta-large-xnli")


def classify(text, candidate_labels, hypothesis_template="This text is about {}."):
    scores = {}
    for label in candidate_labels:
        hypothesis = hypothesis_template.format(label)
        inputs = tok(text, hypothesis, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = model(**inputs).logits[0]
        entail_score = torch.softmax(logits, dim=-1)[2].item()
        scores[label] = entail_score
    return dict(sorted(scores.items(), key=lambda x: -x[1]))


print(classify("I love this product!", ["positive", "negative", "neutral"]))
print(classify("मुझे यह उत्पाद पसंद है!", ["positive", "negative", "neutral"]))
print(classify("J'adore ce produit !", ["positive", "negative", "neutral"]))
```

一個模型、三種語言、同一組 API。用 NLI 資料訓練出來的 XLM-R，透過蘊涵這招能很好地遷移到分類任務上。

### 步驟 2：多語言嵌入空間

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

pairs = [
    ("The cat is sleeping.", "Le chat dort."),
    ("The cat is sleeping.", "El gato está durmiendo."),
    ("The cat is sleeping.", "Die Katze schläft."),
    ("The cat is sleeping.", "The dog is barking."),
]

for eng, other in pairs:
    emb_eng = model.encode([eng], normalize_embeddings=True)[0]
    emb_other = model.encode([other], normalize_embeddings=True)[0]
    sim = float(np.dot(emb_eng, emb_other))
    print(f"  {eng!r} <-> {other!r}: cos={sim:.3f}")
```

互為譯文的句子在嵌入空間裡落得很近。換一句不同意思的英文句子就落得更遠。跨語言檢索、分群與相似度之所以行得通，靠的就是這個。

### 步驟 3：少樣本微調策略

```python
from transformers import TrainingArguments, Trainer
from datasets import Dataset


def few_shot_finetune(base_model, base_tokenizer, examples):
    ds = Dataset.from_list(examples)

    def tokenize_fn(ex):
        out = base_tokenizer(ex["text"], truncation=True, max_length=128)
        out["labels"] = ex["label"]
        return out

    ds = ds.map(tokenize_fn)
    args = TrainingArguments(
        output_dir="out",
        per_device_train_batch_size=8,
        num_train_epochs=5,
        learning_rate=2e-5,
        save_strategy="no",
    )
    trainer = Trainer(model=base_model, args=args, train_dataset=ds)
    trainer.train()
    return base_model
```

目標語言有 100-500 筆例子時，`num_train_epochs=5` 與 `learning_rate=2e-5` 是安全的預設值。學習率再高，多語言的對齊就會塌掉，你會得到一個只會英文的模型。

## 真正有效的評估

- **逐語言在保留集上的準確率。** 不要匯總。匯總數字會把長尾藏起來。
- **與單語言基線比較。** 對資料夠多的語言，從頭訓練的單語言模型有時會勝過多語言模型。要測。
- **實體層級的測試。** 用目標語言的具名實體來測。多語言模型對離拉丁字母很遠的書寫系統，分詞常常很弱。
- **跨語言一致性。** 同一個意思用兩種語言表達，應該得到同一個預測。把落差量出來。

## 框架應用

2026 年的組合：

| 任務 | 建議 |
|-----|-------------|
| 分類、100 種語言 | 微調過的 XLM-R-base（約 270M） |
| 零樣本文本分類 | `joeddav/xlm-roberta-large-xnli` |
| 多語言句子嵌入 | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| 翻譯、200 種語言 | `facebook/nllb-200-distilled-600M`（見單元 11） |
| 生成式多語言 | Claude、GPT-4、Aya-23、mT5-XXL |
| 低資源語言 NLP | XLM-V，或在相近的高資源語言上做針對領域的微調 |

只要在意效能，就一定要為目標語言的微調留預算。零樣本是起點，不是最終答案。

### 分詞稅（低資源語言會壞在哪裡）

多語言模型在它支援的所有語言之間共用一個分詞器。那份詞彙表是在一份由英文、法文、西班牙文、中文、德文主導的語料上訓練出來的。對這個主導集合以外的任何語言，有三種稅會無聲地疊加起來：

- **詞元膨脹稅。** 低資源語言的文本，每個詞被切出來的詞元數遠多於英文。一句印地語可能需要等價英文句子 3-5 倍的詞元。這 3-5 倍會吃掉你的脈絡窗口、訓練效率與延遲。
- **變體還原稅。** 每一個錯字、變音符號變體、Unicode 正規化不一致或大小寫變化，在嵌入空間裡都變成一段冷啟動、彼此無關的序列。母語者覺得理所當然的正字法對應關係，模型學不到。
- **容量排擠稅。** 前兩種稅吃掉了脈絡位置、層數深度與嵌入維度。真正留給推論本身的部分，系統性地少於同一個模型給高資源語言的份量。

務實的症狀是：你的模型在印地語上訓練起來一切正常，損失曲線看起來對，評估的困惑度看起來合理，然後生產環境的輸出微妙地錯了。形態在句子中段崩掉。罕見的屈折變化始終救不回來。**分詞器壞掉這件事，是沒辦法靠加資料規模繞過去的。**

緩解方式：挑一個對你目標語言涵蓋良好的分詞器（XLM-V 的 100 萬詞元詞彙表是直接的解法）；訓練前先在保留的目標語言文本上驗證分詞的膨脹程度；對真正長尾的書寫系統，用位元組層級的後備方案（SentencePiece 的 `byte_fallback=True`、GPT-2 風格的位元組層級 BPE），讓任何東西都不會變成 OOV。

## 產出交付

存成 `outputs/skill-multilingual-picker.md`：

```markdown
---
name: multilingual-picker
description: Pick source language, target model, and evaluation plan for a multilingual NLP task.
version: 1.0.0
phase: 5
lesson: 18
tags: [nlp, multilingual, cross-lingual]
---

Given requirements (target languages, task type, available labeled data per language), output:

1. Source language for fine-tuning. Default English; check LANGRANK or qWALS if target language has a typologically close high-resource language.
2. Base model. XLM-R (classification), mT5 (generation), NLLB (translation), Aya-23 (generative LLM).
3. Few-shot budget. Start with 100-500 target-language examples if available. Zero-shot only if labeling is infeasible.
4. Evaluation plan. Per-language accuracy (not aggregate), cross-lingual consistency, entity-level F1 on non-Latin scripts.

Refuse to ship a multilingual model without per-language evaluation — aggregate metrics hide long-tail failures. Flag scripts with low tokenization coverage (Amharic, Tigrinya, many African languages) as needing a model with byte-fallback (SentencePiece with byte_fallback=True, or byte-level tokenizer like GPT-2).
```

## 練習

1. **簡單。** 拿零樣本分類流程，在英文、法文、印地語與阿拉伯語各 10 句上跑一遍。回報各語言的準確率。你應該會看到法文很強、印地語堪用、阿拉伯語不穩定。
2. **中等。** 用 `paraphrase-multilingual-MiniLM-L12-v2` 在一個小型混合語言語料庫上建一個跨語言檢索器。用英文查詢，檢索任何語言的文件。量測 recall@5。
3. **困難。** 針對一個印地語分類任務，比較以英文為來源與以印地語為來源的微調。兩種做法都用 500 筆目標語言例子做少樣本微調。回報哪一個來源產出更好的印地語準確率、差多少。這就是 LANGRANK 論點的縮影。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 多語言模型 | 「一個模型、很多語言」 | 跨語言共享詞彙表與參數。 |
| 跨語言遷移 | 「用一種語言訓練，跑另一種語言」 | 在來源語言上微調，在目標語言上評估，不需要目標語言的標註。 |
| 零樣本 | 「沒有目標語言的標註」 | 不在目標語言上微調就完成遷移。 |
| 少樣本 | 「少量目標語言標註」 | 用 100-500 筆目標語言例子做微調。 |
| mBERT | 「第一個多語言語言模型」 | 在 Wikipedia 上預訓練的 104 語言 BERT。 |
| XLM-R | 「標準的跨語言基線」 | 在 CommonCrawl 上預訓練的 100 語言 RoBERTa。 |
| NLLB | 「Meta 的 200 語言機器翻譯模型」 | No Language Left Behind。含 55 種低資源語言。 |

## 延伸閱讀

- [Conneau et al. (2019). Unsupervised Cross-lingual Representation Learning at Scale](https://arxiv.org/abs/1911.02116) —— XLM-R 論文。
- [Pires, Schlinger, Garrette (2019). How Multilingual is Multilingual BERT?](https://arxiv.org/abs/1906.01502) —— 開啟跨語言遷移這條研究線的分析論文。
- [Costa-jussà et al. (2022). No Language Left Behind](https://arxiv.org/abs/2207.04672) —— NLLB-200 論文。
- [Üstün et al. (2024). Aya Model: An Instruction Finetuned Open-Access Multilingual Language Model](https://arxiv.org/abs/2402.07827) —— Aya，Cohere 的多語言 LLM。
- [Language Similarity Predicts Cross-Lingual Transfer Learning Performance (2026)](https://www.mdpi.com/2504-4990/8/3/65) —— qWALS／LANGRANK 那篇來源語言論文。
