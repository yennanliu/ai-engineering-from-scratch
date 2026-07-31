# BERT —— 遮罩語言建模

> GPT 預測下一個詞。BERT 預測缺掉的那個詞。差別只有一句話 —— 卻換來了長達半個十年、所有跟嵌入有關的東西。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 7 · 05（完整的 Transformer）、階段 5 · 02（文本表示）
**時間：** 約 45 分鐘

## 問題所在

2018 年，每個 NLP 任務 —— 情感分析、NER、問答、蘊涵判斷 —— 都用自己的標註資料從零訓練自己的模型。當時沒有一個預訓練好的「懂英文」檢查點可以拿來微調。ELMo（2018）證明了可以用雙向 LSTM 預訓練脈絡化嵌入；有幫助，但泛化能力不足。

BERT（Devlin et al. 2018）提出的問題是：如果我們拿一個 Transformer 編碼器，在網路上的每一句話上訓練它，並強迫它用兩側的脈絡預測缺掉的詞，會怎麼樣？之後你只要針對下游任務微調一個輸出頭。這種參數效率在當時是一項啟示。

結果是：18 個月內，BERT 及其變體（RoBERTa、ALBERT、ELECTRA）橫掃當時存在的每一份 NLP 排行榜。到 2020 年，地球上每一個搜尋引擎、內容審核流程與語意搜尋系統裡都有一個 BERT。

到了 2026 年，只有編碼器的模型在分類、檢索與結構化抽取上仍然是對的工具 —— 它們每個詞元的執行速度比解碼器快 5–10 倍，而它們的嵌入是每一套現代檢索堆疊的骨幹。ModernBERT（2024 年 12 月）用 Flash Attention + RoPE + GeGLU 把這個架構推進到 8K 脈絡長度。

## 核心概念

![遮罩語言建模：挑選詞元、把它們遮住、預測原本的詞元](../assets/bert-mlm.svg)

### 訓練訊號

取一句話：`the quick brown fox jumps over the lazy dog`。

隨機遮住 15% 的詞元：

```
input:  the [MASK] brown fox jumps [MASK] the lazy dog
target: the  quick brown fox jumps  over  the lazy dog
```

訓練模型在被遮住的位置預測原本的詞元。因為編碼器是雙向的，預測位置 1 的 `[MASK]` 時可以用到位置 2 之後的 `brown fox jumps`。這正是 GPT 做不到的事。

### BERT 的遮罩規則

在被選中要預測的那 15% 詞元裡：

- 80% 換成 `[MASK]`。
- 10% 換成一個隨機詞元。
- 10% 保持原樣。

為什麼不一律用 `[MASK]`？因為 `[MASK]` 在推論時從來不會出現。如果訓練時 100% 的被遮位置都是 `[MASK]`，就會在預訓練與微調之間製造分布偏移。那 10% 隨機加 10% 原樣，讓模型保持誠實。

### 下一句預測（NSP）—— 以及它為什麼被拿掉

原始的 BERT 也在 NSP 上訓練：給定兩句 A 與 B，判斷 B 是否接在 A 之後。RoBERTa（2019）做了消融實驗，顯示 NSP 是扣分而非加分。現代的編碼器都跳過它。

### 2026 年有什麼變了：ModernBERT

2024 年的 ModernBERT 論文用 2026 年的原語重建了整個區塊：

| 組件 | 原始 BERT（2018） | ModernBERT（2024） |
|-----------|----------------------|-------------------|
| 位置資訊 | 學習式絕對位置 | RoPE |
| 激活函數 | GELU | GeGLU |
| 正規化 | LayerNorm | pre-norm RMSNorm |
| 注意力 | 完整稠密 | 交替的局部（128）+ 全域 |
| 脈絡長度 | 512 | 8192 |
| 分詞器 | WordPiece | BPE |

而且不像 2018 年那套堆疊，它原生支援 Flash Attention。在序列長度 8K 時，推論比 DeBERTa-v3 快 2–3 倍，GLUE 分數還更好。

### 2026 年仍然會選編碼器的使用情境

| 任務 | 編碼器為何勝過解碼器 |
|------|---------------------------|
| 檢索／語意搜尋嵌入 | 雙向脈絡 = 每個詞元的嵌入品質更好 |
| 分類（情感、意圖、毒性） | 一次前向傳播；沒有生成的額外開銷 |
| NER／詞元標註 | 逐位置輸出，天生就是雙向的 |
| 零樣本蘊涵判斷（NLI） | 在編碼器上加一個分類頭 |
| RAG 的重排器 | 交叉編碼器評分，比 LLM 重排器快 10 倍 |

```figure
transformer-residual
```

## 動手實作

### 步驟 1：遮罩邏輯

請看 `code/main.py`。函式 `create_mlm_batch` 接收一串詞元 ID、詞彙表大小與遮罩機率。回傳輸入 ID（已套用遮罩）與標籤（只在被遮位置有值，其餘為 -100 —— PyTorch 的忽略索引慣例）。

```python
def create_mlm_batch(tokens, vocab_size, mask_prob=0.15, rng=None):
    input_ids = list(tokens)
    labels = [-100] * len(tokens)
    for i, t in enumerate(tokens):
        if rng.random() < mask_prob:
            labels[i] = t
            r = rng.random()
            if r < 0.8:
                input_ids[i] = MASK_ID
            elif r < 0.9:
                input_ids[i] = rng.randrange(vocab_size)
            # else: keep original
    return input_ids, labels
```

### 步驟 2：在一個極小語料上跑遮罩語言建模預測

在一個 20 個詞的詞彙表、200 個句子上訓練一個 2 層編碼器 + 遮罩語言建模輸出頭。不算梯度 —— 我們只做前向傳播的健全性檢查。完整訓練需要 PyTorch。

### 步驟 3：比較各種遮罩型態

示範這條三分規則如何讓模型在沒有 `[MASK]` 的情況下依然可用。分別對一個沒遮罩的句子與一個有遮罩的句子做預測。兩者都應該產生合理的詞元分布，因為模型在訓練時兩種樣態都見過。

### 步驟 4：微調輸出頭

在一個玩具情感資料集上，把遮罩語言建模的輸出頭換成分類頭。只訓練輸出頭；編碼器保持凍結。每一個 BERT 應用都照著這個模式走。

## 框架應用

```python
from transformers import AutoModel, AutoTokenizer

tok = AutoTokenizer.from_pretrained("answerdotai/ModernBERT-base")
model = AutoModel.from_pretrained("answerdotai/ModernBERT-base")

text = "Attention is all you need."
inputs = tok(text, return_tensors="pt")
out = model(**inputs).last_hidden_state   # (1, N, 768)
```

**嵌入模型就是微調過的 BERT。** `sentence-transformers` 裡像 `all-MiniLM-L6-v2` 這類模型，是用對比損失訓練出來的 BERT。編碼器一模一樣。變的是損失函式。

**交叉編碼器重排器也是微調過的 BERT。** 在 `[CLS] query [SEP] doc [SEP]` 上做配對分類。查詢與文件之間的雙向注意力，正是交叉編碼器在品質上勝過雙編碼器的原因。

**2026 年什麼時候不該選 BERT。** 任何生成類的任務。編碼器沒有合理的方式自迴歸地產出詞元。此外：任何 1B 參數以下的場景，小型解碼器能達到相同品質又更靈活（Phi-3-Mini、Qwen2-1.5B）。

## 產出交付

請看 `outputs/skill-bert-finetuner.md`。這項技能會為一個新的分類或抽取任務界定 BERT 微調的範圍（骨幹選擇、輸出頭規格、資料、評估、停止條件）。

## 練習

1. **簡單。** 執行 `code/main.py`，印出 10,000 個詞元的遮罩分布。確認約 15% 被選中，而其中約 80% 變成 `[MASK]`。
2. **中等。** 實作整詞遮罩：若一個詞被切成多個子詞，就把所有子詞一起遮住，或一個都不遮。在一個 500 句的語料上量測這是否提升遮罩語言建模的準確率。
3. **困難。** 在某個公開資料集的 10,000 個句子上訓練一個極小的（2 層、d=64）BERT。針對 SST-2 情感任務微調 `[CLS]` 詞元。在參數量相當的條件下與只有解碼器的基準比較 —— 誰贏？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| MLM | 「遮罩語言建模」 | 訓練訊號：隨機把 15% 的詞元換成 `[MASK]`，再預測原本的詞元。 |
| 雙向 | 「兩邊都看」 | 編碼器的注意力沒有因果遮罩 —— 每個位置都看得到其他每個位置。 |
| `[CLS]` | 「那個池化用的詞元」 | 加在每個序列最前面的特殊詞元；它最終的嵌入會被當成句子層級的表示。 |
| `[SEP]` | 「片段分隔符」 | 分隔成對的序列（例如查詢／文件、句子 A／B）。 |
| NSP | 「下一句預測」 | BERT 的第二個預訓練任務；RoBERTa 證明它沒用，2019 年後被拿掉。 |
| 微調 | 「適配到某個任務」 | 編碼器大致凍結；在上面訓練一個小的輸出頭來做下游任務。 |
| 交叉編碼器 | 「一種重排器」 | 把查詢與文件一起當輸入的 BERT，輸出一個相關性分數。 |
| ModernBERT | 「2024 年的翻新版」 | 用 RoPE、RMSNorm、GeGLU、交替的局部／全域注意力與 8K 脈絡重建的編碼器。 |

## 延伸閱讀

- [Devlin et al. (2018). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding](https://arxiv.org/abs/1810.04805) —— 原始論文。
- [Liu et al. (2019). RoBERTa: A Robustly Optimized BERT Pretraining Approach](https://arxiv.org/abs/1907.11692) —— 怎麼把 BERT 訓練對；順手殺掉 NSP。
- [Clark et al. (2020). ELECTRA: Pre-training Text Encoders as Discriminators Rather Than Generators](https://arxiv.org/abs/2003.10555) —— 在相同運算量下，替換詞元偵測勝過遮罩語言建模。
- [Warner et al. (2024). Smarter, Better, Faster, Longer: A Modern Bidirectional Encoder](https://arxiv.org/abs/2412.13663) —— ModernBERT 論文。
- [HuggingFace `modeling_bert.py`](https://github.com/huggingface/transformers/blob/main/src/transformers/models/bert/modeling_bert.py) —— 典範的編碼器參考實作。
