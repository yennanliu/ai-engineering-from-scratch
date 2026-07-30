# 子詞分詞 —— BPE、WordPiece、Unigram、SentencePiece

> 詞層級分詞器一碰到沒見過的詞就卡住。字元層級分詞器讓序列長度爆掉。子詞分詞器取兩者的折衷。現代每一個 LLM 都建立在某一種子詞分詞器上。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 5 · 01（文字處理）、階段 5 · 04（GloVe／FastText／子詞）
**時間：** 約 60 分鐘

## 問題所在

你的詞彙表有 50,000 個詞。使用者輸入了 "untokenizable"。你的分詞器回傳 `[UNK]`。模型現在對這個詞完全沒有任何訊號。更糟的是：語料中第 90 百分位的文件有 40 個罕見詞，也就是每份文件被丟掉 40 處資訊。

子詞分詞解掉了這一題。高頻詞維持成單一詞元，罕見詞則被拆成有意義的部件：`untokenizable` → `un`、`token`、`izable`。訓練資料能涵蓋一切，因為任何字串最終都是一串位元組。

2026 年的每一個前沿 LLM 都建立在三種演算法（BPE、Unigram、WordPiece）之一上，並包在三種函式庫（tiktoken、SentencePiece、HF Tokenizers）之一裡面。不挑一種，你就沒辦法把語言模型交付出去。

## 核心概念

![BPE vs Unigram vs WordPiece, character-by-character](../assets/subword-tokenization.svg)

**BPE（位元組對編碼）。** 從字元層級的詞彙表開始。統計每一個相鄰的配對。把出現頻率最高的配對合併成一個新詞元。重複下去，直到達到目標詞彙表大小。這是目前的主流演算法：GPT-2/3/4、Llama、Gemma、Qwen2、Mistral 都用它。

**位元組層級 BPE。** 演算法一樣，只是跑在原始位元組（256 個基底詞元）上，而不是 Unicode 字元上。保證產生零個 `[UNK]` 詞元 —— 任何位元組序列都編得出來，等於徹底的未知詞消除。GPT-2 用 50,257 個詞元（256 個位元組 + 50,000 條合併規則 + 1 個特殊詞元）。

**Unigram。** 從一份極大的詞彙表開始。給每個詞元一個 unigram 機率。反覆剪掉那些「移除後對語料對數似然損害最小」的詞元。在推論時是機率式分詞：可以對分詞結果取樣（透過子詞正則化來做資料增強時很有用）。T5、mBART、ALBERT、XLNet、Gemma 用它。

**WordPiece。** 合併的依據是「哪個配對最能提升訓練語料的似然」，而不是原始頻率。BERT、DistilBERT、ELECTRA 用它。

**SentencePiece 與 tiktoken 的差別。** SentencePiece 是*訓練*詞彙表的函式庫（BPE 或 Unigram），直接跑在原始 Unicode 文字上，並把空白編碼成 `▁`。tiktoken 是 OpenAI 針對既有詞彙表的高速*編碼器*；它不做訓練。

經驗法則：

- **要訓練一份新的詞彙表：** SentencePiece（多語、不需要前置分詞）或 HF Tokenizers。
- **要對 GPT 詞彙表做高速推論：** tiktoken（cl100k_base、o200k_base）。
- **兩者都要：** HF Tokenizers —— 一個函式庫同時涵蓋訓練與服務。

```figure
bpe-merge
```

## 動手實作

### 步驟 1：從零打造 BPE

見 `code/main.py`。主迴圈：

```python
def train_bpe(corpus, num_merges):
    vocab = {tuple(word) + ("</w>",): count for word, count in corpus.items()}
    merges = []
    for _ in range(num_merges):
        pairs = Counter()
        for symbols, freq in vocab.items():
            for a, b in zip(symbols, symbols[1:]):
                pairs[(a, b)] += freq
        if not pairs:
            break
        best = pairs.most_common(1)[0][0]
        merges.append(best)
        vocab = apply_merge(vocab, best)
    return merges
```

這段演算法編碼了三件事。`</w>` 標記詞的結尾，好讓 "low"（當字尾時）與 "lower"（當字首時）保持區分。頻率加權讓高頻配對能在早期就勝出。合併規則清單是有序的 —— 推論時要照訓練時的順序套用。

### 步驟 2：用學到的合併規則做編碼

```python
def encode_bpe(word, merges):
    symbols = list(word) + ["</w>"]
    for a, b in merges:
        i = 0
        while i < len(symbols) - 1:
            if symbols[i] == a and symbols[i + 1] == b:
                symbols = symbols[:i] + [a + b] + symbols[i + 2:]
            else:
                i += 1
    return symbols
```

這是樸素的 O(n·|merges|) 做法。生產級實作（tiktoken、HF Tokenizers）改用合併排名查表搭配優先佇列，可以跑到接近線性時間。

### 步驟 3：實務上的 SentencePiece

```python
import sentencepiece as spm

spm.SentencePieceTrainer.train(
    input="corpus.txt",
    model_prefix="my_tokenizer",
    vocab_size=8000,
    model_type="bpe",          # or "unigram"
    character_coverage=0.9995, # lower for CJK (e.g. 0.9995 for English, 0.995 for Japanese)
    normalization_rule_name="nmt_nfkc",
)

sp = spm.SentencePieceProcessor(model_file="my_tokenizer.model")
print(sp.encode("untokenizable", out_type=str))
# ['▁un', 'token', 'izable']
```

注意幾點：不需要前置分詞、空白被編碼成 `▁`、`character_coverage` 控制罕見字元要被保留得多積極，還是直接對應到 `<unk>`。

### 步驟 4：用 tiktoken 處理 OpenAI 相容的詞彙表

```python
import tiktoken
enc = tiktoken.get_encoding("o200k_base")
print(enc.encode("untokenizable"))        # [127340, 101028]
print(len(enc.encode("Hello, world!")))   # 4
```

只做編碼。速度快（Rust 後端）。要算位元組數、估成本、規劃上下文視窗預算時，它跟 GPT-4/5 的分詞結果完全一致。

## 到了 2026 年還是常被交付出去的陷阱

- **分詞器漂移。** 用詞彙表 A 訓練，部署時卻對著詞彙表 B。詞元 ID 對不上，模型輸出就是亂碼。在 CI 裡檢查 `tokenizer.json` 的雜湊值。
- **空白的歧義。** BPE 對 "hello" 與 " hello" 會產生不同的詞元。永遠把 `add_special_tokens` 與 `add_prefix_space`（前置空白）明確寫出來。
- **多語訓練不足。** 以英文為主的語料所產生的詞彙表，會把非拉丁文字切成 5 到 10 倍多的詞元。同一段提示詞在 GPT-3.5 上用日文／阿拉伯文寫，成本就貴 5 到 10 倍。o200k_base 部分改善了這件事。
- **表情符號被切開。** 單一個表情符號可能吃掉 5 個詞元。在規劃上下文預算時，記得把表情符號的處理方式檢查一遍。

## 框架應用

2026 年的技術選擇：

| 情境 | 選擇 |
|-----------|------|
| 從零訓練單語模型 | HF Tokenizers（BPE） |
| 訓練多語模型 | SentencePiece（Unigram，`character_coverage=0.9995`） |
| 提供 OpenAI 相容的 API 服務 | tiktoken（GPT-4 以上用 `o200k_base`） |
| 領域專用詞彙表（程式碼、數學、蛋白質） | 在領域語料上訓練自己的 BPE，再與基礎詞彙表合併 |
| 邊緣推論、小模型 | Unigram（較小的詞彙表表現更好） |

詞彙表大小是一個規模決策，不是常數。粗略的經驗法則：參數量 <1B 用 32k，1-10B 用 50-100k，多語／前沿模型則 200k 以上。

## 產出交付

存成 `outputs/skill-bpe-vs-wordpiece.md`：

```markdown
---
name: tokenizer-picker
description: Pick tokenizer algorithm, vocab size, library for a given corpus and deployment target.
version: 1.0.0
phase: 5
lesson: 19
tags: [nlp, tokenization]
---

Given a corpus (size, languages, domain) and deployment target (training from scratch / fine-tuning / API-compatible inference), output:

1. Algorithm. BPE, Unigram, or WordPiece. One-sentence reason.
2. Library. SentencePiece, HF Tokenizers, or tiktoken. Reason.
3. Vocab size. Rounded to nearest 1k. Reason tied to model size and language coverage.
4. Coverage settings. `character_coverage`, `byte_fallback`, special-token list.
5. Validation plan. Average tokens-per-word on held-out set, OOV rate, compression ratio, round-trip decode equality.

Refuse to train a character-coverage <0.995 tokenizer on corpora with rare-script content. Refuse to ship a vocab without a frozen `tokenizer.json` hash check in CI. Flag any monolingual tokenizer under 16k vocab as likely under-spec.
```

## 練習

1. **簡單。** 在 `code/main.py` 的小語料上訓練一個 500 次合併的 BPE。對三個保留在外的詞做編碼。其中有幾個剛好產生 1 個詞元，幾個產生超過 1 個？
2. **中等。** 拿 100 句英文維基百科的句子，比較 `cl100k_base`、`o200k_base`，以及你自己用 vocab=32k 訓練的 SentencePiece BPE 三者的詞元數。報告各自的壓縮率。
3. **困難。** 用同一份語料分別訓練 BPE、Unigram 與 WordPiece。把三者各自套到一個小型情感分類器上，量測下游準確率。這個選擇能讓 F1 動超過 1 個百分點嗎？

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| BPE | 「位元組對編碼」 | 貪婪分詞的訓練面：反覆合併出現頻率最高的字元配對，直到達到目標詞彙表大小。 |
| 位元組層級 BPE | 「永遠不會有未知詞元」 | 跑在原始 256 個位元組上的 BPE；GPT-2／Llama 用這個。 |
| Unigram | 「機率式分詞器」 | 用對數似然從一大堆候選詞元中剪枝而成；T5、Gemma 用它。 |
| SentencePiece | 「處理空白的那個」 | 直接在原始文字上訓練 BPE／Unigram 的函式庫；空白編碼成 `▁`。 |
| tiktoken | 「快的那個」 | OpenAI 以 Rust 實作的 BPE 編碼器，用於既有詞彙表。不做訓練。 |
| 合併清單 | 「那些魔術數字」 | `(a, b) → ab` 這類合併規則的有序清單；推論時照順序套用。 |
| 字元覆蓋率 | 「多罕見才算太罕見？」 | 分詞器必須涵蓋的訓練語料字元比例；典型值約 0.9995。 |

## 延伸閱讀

- [Sennrich, Haddow, Birch (2015). Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909) —— BPE 論文。
- [Kudo (2018). Subword Regularization with Unigram Language Model](https://arxiv.org/abs/1804.10959) —— Unigram 論文。
- [Kudo, Richardson (2018). SentencePiece: A simple and language independent subword tokenizer](https://arxiv.org/abs/1808.06226) —— 那個函式庫。
- [Hugging Face — Summary of the tokenizers](https://huggingface.co/docs/transformers/tokenizer_summary) —— 精簡的參考資料。
- [OpenAI tiktoken repo](https://github.com/openai/tiktoken) —— 使用手冊與編碼清單。
