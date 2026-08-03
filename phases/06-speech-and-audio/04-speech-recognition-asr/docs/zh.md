# 語音辨識（ASR）—— CTC、RNN-T 與注意力機制

> 語音辨識就是在每個時間步上做音訊分類，再由一個懂英文與靜音的序列模型把它們黏起來。CTC、RNN-T 與注意力機制是三種做法。挑一種，並搞懂為什麼。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 6 · 02（頻譜圖與梅爾）、階段 5 · 08（用於文字的 CNN 與 RNN）、階段 5 · 10（注意力機制）
**時間：** 約 45 分鐘

## 問題所在

你有一段 10 秒、16 kHz 的片段。你想要一個字串：「turn on the kitchen lights」。這個挑戰是結構性的：音訊幀跟字元並不是一對一對齊。「okay」這個詞可能佔 200 ms，也可能佔 1200 ms。靜音會把語句斷開。有些音素比別的長。輸出詞元的數量事先並不知道。

有三種公式化方式能解這件事：

1. **CTC（Connectionist Temporal Classification）。** 輸出每一幀在各詞元上的機率，其中包含一個特殊的*空白*（blank）。解碼時把重複與空白摺疊掉。非自迴歸、快。wav2vec 2.0 與 MMS 都用它。
2. **RNN-T（Recurrent Neural Network Transducer）。** 由聯合網路根據編碼器的幀與先前的詞元，預測下一個詞元。可串流。Google 的裝置端 ASR、NVIDIA Parakeet 都用它。
3. **注意力編碼器-解碼器。** 編碼器把音訊壓成隱藏狀態，解碼器對它做交叉注意力，自迴歸地生成詞元。Whisper 與 SeamlessM4T 都用它。

2026 年在 LibriSpeech test-clean 上的 SOTA WER 是 1.4%（Parakeet-TDT-1.1B，NVIDIA）與 1.58%（Whisper-Large-v3-turbo）。品質差距很小；部署上的差距則很大。

## 核心概念

![三種 ASR 公式化方式：CTC、RNN-T、注意力編碼器-解碼器](../assets/asr-formulations.svg)

**CTC 的直覺。** 讓編碼器輸出 `T` 個幀層級的分布，每個分布涵蓋 `V+1` 個詞元（V 個字元加空白）。對於長度 `U < T` 的目標字串 `y`，任何摺疊後等於 `y` 的幀對齊都算。CTC 損失會把所有這類對齊加總起來。推論時：每幀取 argmax、摺疊重複、去掉空白。

優點：非自迴歸、可串流、不需要往前看。缺點：*條件獨立假設* —— 每一幀的預測都跟其他幀無關，所以模型內部沒有語言模型。解法是透過束搜尋或淺層融合接一個外部 LM。

**RNN-T 的直覺。** 它加了一個*預測器*網路來嵌入詞元歷史，以及一個*結合器*把預測器狀態與編碼器的幀合起來，變成一個涵蓋 `V+1` 的聯合分布（那個 `+1` 是空輸出／不輸出）。它明確建模了 CTC 忽略掉的條件依賴關係。之所以可串流，是因為每一步只依賴過去的幀與過去的詞元。

優點：可串流 + 內建語言模型。缺點：訓練更複雜、更吃記憶體（3D 的損失格），而 RNN-T 損失的計算核心本身就自成一個函式庫類別。

**注意力編碼器-解碼器。** 編碼器（6 到 32 層 transformer）吃對數梅爾幀。解碼器（6 到 32 層 transformer）對編碼器輸出做交叉注意力，自迴歸地生成詞元。沒有對齊限制 —— 注意力可以看音訊裡的任何地方。除非你限制注意力範圍（分塊的 Whisper-Streaming，2024），否則無法串流。

優點：離線 ASR 的品質最高，用標準 seq2seq 工具就容易訓練。缺點：自迴歸的延遲跟輸出長度成正比；沒有額外工程就無法串流。

### WER：唯一那個數字

**字錯誤率** = `(S + D + I) / N`，其中 S=替換、D=刪除、I=插入、N=參考答案的詞數。它等於在詞層級上的 Levenshtein 編輯距離。越低越好。WER 高於 20% 基本上不能用；低於 5% 在朗讀語音上已達人類水準。2026 年在標準基準測試上的數字：

| 模型 | LibriSpeech test-clean | LibriSpeech test-other | 大小 |
|-------|------------------------|------------------------|------|
| Parakeet-TDT-1.1B | 1.40% | 2.78% | 11 億參數 |
| Whisper-Large-v3-turbo | 1.58% | 3.03% | 809M |
| Canary-1B Flash | 1.48% | 2.87% | 1B |
| Seamless M4T v2 | 1.7% | 3.5% | 2.3B |

這些全都是基於編碼器-解碼器或 RNN-T。純 CTC 系統（wav2vec 2.0）在 test-clean 上大約落在 1.8–2.1%。

```figure
ctc-collapse
```

## 動手實作

### 步驟 1：貪婪 CTC 解碼

```python
def ctc_greedy(frame_logits, blank=0, vocab=None):
    # frame_logits: list of per-frame probability vectors
    preds = [max(range(len(p)), key=lambda i: p[i]) for p in frame_logits]
    out = []
    prev = -1
    for p in preds:
        if p != prev and p != blank:
            out.append(p)
        prev = p
    return "".join(vocab[i] for i in out) if vocab else out
```

兩條規則：摺疊連續的重複，丟掉空白。例如：`a a _ _ a b b _ c` → `a a b c`。

### 步驟 2：束搜尋 CTC

```python
def ctc_beam(frame_logits, beam=8, blank=0):
    import math
    beams = [([], 0.0)]  # (tokens, log_prob)
    for p in frame_logits:
        log_p = [math.log(max(pi, 1e-10)) for pi in p]
        candidates = []
        for seq, lp in beams:
            for t, lpt in enumerate(log_p):
                new = seq[:] if t == blank else (seq + [t] if not seq or seq[-1] != t else seq)
                candidates.append((new, lp + lpt))
        candidates.sort(key=lambda x: -x[1])
        beams = candidates[:beam]
    return beams[0][0]
```

正式環境用的是搭配 LM 融合的前綴樹束搜尋；這裡只是概念骨架。

### 步驟 3：WER

```python
def wer(ref, hyp):
    r, h = ref.split(), hyp.split()
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[len(r)][len(h)] / max(1, len(r))
```

### 步驟 4：拿 Whisper 來做推論

```python
import whisper
model = whisper.load_model("large-v3-turbo")
result = model.transcribe("clip.wav")
print(result["text"])
```

一行就用上 2026 年最強的通用 ASR。在一張 24 GB 的 GPU 上跑，速度約為即時的 20 倍。

### 步驟 5：用 Parakeet 或 wav2vec 2.0 做串流

```python
from transformers import pipeline
asr = pipeline("automatic-speech-recognition", model="nvidia/parakeet-tdt-1.1b")
for chunk in streaming_audio():
    print(asr(chunk, return_timestamps=True))
```

串流 ASR 需要分塊的編碼器注意力與跨塊延續的狀態；用支援這些的函式庫（Parakeet 用 NeMo，或是搭配 `chunk_length_s` 的 `transformers` pipeline）。

## 框架應用

2026 年的那一套：

| 情境 | 選什麼 |
|-----------|------|
| 英文、離線、品質最高 | Whisper-large-v3-turbo |
| 多語言、穩健 | SeamlessM4T v2 |
| 串流、低延遲 | Parakeet-TDT-1.1B 或 Riva |
| 邊緣裝置、行動端、延遲 <500 ms | 量化後的 Whisper-Tiny 或 Moonshine（2024） |
| 長音檔 | Whisper 搭配基於 VAD 的分塊（WhisperX） |
| 特定領域（醫療、法律） | 微調 wav2vec 2.0 + 領域 LM 融合 |

## 到了 2026 年還是常被交付出去的陷阱

- **沒有 VAD。** 拿 Whisper 去跑靜音會產生幻覺（「Thanks for watching!」）。一定要用 VAD 把關。
- **字元、詞、子詞層級的 WER 搞混。** 報告詞層級的 WER，而且要在正規化*之後*（轉小寫、去標點）。
- **語言識別漂移。** Whisper 的自動 LID 會把吵雜的片段誤判成日文或威爾斯文；知道語言時就強制指定 `language="en"`。
- **長片段沒有分塊。** Whisper 的窗只有 30 秒。超過就用 `chunk_length_s=30, stride=5`。

## 產出交付

存成 `outputs/skill-asr-picker.md`。針對指定的部署目標，挑選模型、解碼策略、分塊方式與 LM 融合。

## 練習

1. **簡單。** 跑 `code/main.py`。它會對一組手工打造的 CTC 輸出做貪婪解碼，並對照參考答案算 WER。
2. **中等。** 把步驟 2 的前綴樹束搜尋正確實作出來（要處理空白的合併規則）。在一個 10 個範例的合成資料集上跟貪婪解碼比較。
3. **困難。** 在 [LibriSpeech test-clean](https://www.openslr.org/12) 上使用 `whisper-large-v3-turbo`。算出前 100 句語句的 WER。跟已發表的數字比較。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| CTC | 那個有空白詞元的損失 | 對所有幀到詞元的對齊做邊際化；非自迴歸。 |
| RNN-T | 那個能串流的損失 | CTC + 下一詞元預測器；能處理詞序。 |
| 注意力編-解碼器 | Whisper 那一派 | 編碼器 + 做交叉注意力的解碼器；離線品質最好。 |
| WER | 你要報告的那個數字 | 詞層級的 `(S+D+I)/N`。 |
| 空白（Blank） | 那個「什麼都沒有」 | CTC 裡表示「這一幀不輸出」的特殊詞元。 |
| LM 融合 | 外部語言模型 | 在束搜尋時加上加權後的 LM 對數機率。 |
| VAD | 靜音的那道閘門 | 語音活動偵測器；把非語音的部分剪掉。 |

## 延伸閱讀

- [Graves et al. (2006). Connectionist Temporal Classification](https://www.cs.toronto.edu/~graves/icml_2006.pdf) —— CTC 那篇論文。
- [Graves (2012). Sequence Transduction with RNNs](https://arxiv.org/abs/1211.3711) —— RNN-T 那篇論文。
- [Radford et al. / OpenAI (2022). Whisper: Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356) —— 2022 年的經典論文；v3-turbo 是 2024 年的延伸。
- [NVIDIA NeMo — Parakeet-TDT card](https://huggingface.co/nvidia/parakeet-tdt-1.1b) —— 2026 年 Open ASR Leaderboard 的領先者。
- [Hugging Face — Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard) —— 涵蓋 25 個以上模型的即時基準測試。
