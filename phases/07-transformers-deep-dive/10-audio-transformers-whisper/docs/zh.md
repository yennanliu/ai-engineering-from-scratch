# 音訊 Transformer —— Whisper 架構

> 音訊就是一張「頻率對時間」的影像。Whisper 是一個吃梅爾頻譜圖、然後把話說回來的 ViT。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 7 · 05（完整的 Transformer）、階段 7 · 08（編碼器解碼器）、階段 7 · 09（ViT）
**時間：** 約 45 分鐘

## 問題所在

在 Whisper（OpenAI，Radford et al. 2022）之前，最先進的自動語音辨識（ASR）指的是 wav2vec 2.0 與 HuBERT ——自監督特徵抽取器加上一個微調過的輸出頭。品質很好，但資料管線昂貴，而且換個領域就脆掉。多語言語音辨識得替每個語系各準備一個模型。

Whisper 押了三個賭注：

1. **什麼都拿來訓練。** 從網路上蒐集 68 萬小時的弱標註音訊，橫跨 97 種語言。沒有乾淨的學術語料。沒有音素標註。
2. **單一模型多任務。** 一個解碼器，透過任務詞元同時在轉錄、翻譯、語音活動偵測、語言辨識與時間戳這些任務上做多任務訓練。
3. **標準的編碼器解碼器 transformer。** 編碼器吃對數梅爾頻譜圖。解碼器自迴歸地產生文字詞元。沒有 vocoder，沒有 CTC，沒有 HMM。

結果就是：Whisper large-v3 面對各種口音、噪音，以及完全沒有乾淨標註資料的語言都很穩健。在 2026 年，它是每一個開源語音助理、以及大多數商業語音助理的預設語音前端。

## 核心概念

![Whisper 管線：音訊 → 梅爾 → 編碼器 → 解碼器 → 文字](../assets/whisper.svg)

### 步驟 1 —— 重新取樣 + 開視窗

音訊取 16 kHz。裁切或補零到 30 秒。計算對數梅爾頻譜圖：80 個梅爾頻帶、10 ms 位移 → 約 3,000 幀 × 80 個特徵。這就是 Whisper 看到的那張「輸入影像」。

### 步驟 2 —— 卷積前段

兩層卷積核 3、stride 2 的 Conv1D，把 3,000 幀縮到 1,500。序列長度砍半，而且沒加上多少參數。

### 步驟 3 —— 編碼器

一個 24 層（large 版）的 transformer 編碼器，跑在 1,500 個時間步上。正弦式位置編碼、自注意力、GELU 的 FFN。產出 1,500 × 1,280 的隱藏狀態。

### 步驟 4 —— 解碼器

一個 24 層的 transformer 解碼器。它自迴歸地從一個 BPE 詞彙表產生詞元，那個詞彙表是 GPT-2 詞彙表的超集，多加了幾個音訊專屬的特殊詞元。

### 步驟 5 —— 任務詞元

解碼器提示詞的開頭是一串控制詞元，告訴模型該做什麼：

```
<|startoftranscript|>  <|en|>  <|transcribe|>  <|0.00|>
```

或是

```
<|startoftranscript|>  <|fr|>  <|translate|>   <|0.00|>
```

模型就是照這個慣例訓練出來的。任務由前綴決定。這相當於 2026 年的指令微調，只是套用在語音上。

### 步驟 6 —— 輸出

Beam search（寬度 5）搭配一個對數機率門檻。當 `<|notimestamps|>` 詞元不存在時，模型每 0.02 秒的音訊就預測一次時間戳。

### Whisper 的各種尺寸

| 模型 | 參數量 | 層數 | d_model | 注意力頭 | VRAM（fp16） |
|-------|--------|--------|---------|-------|-------------|
| Tiny | 39M | 4 | 384 | 6 | 約 1 GB |
| Base | 74M | 6 | 512 | 8 | 約 1 GB |
| Small | 244M | 12 | 768 | 12 | 約 2 GB |
| Medium | 769M | 24 | 1024 | 16 | 約 5 GB |
| Large | 1550M | 32 | 1280 | 20 | 約 10 GB |
| Large-v3 | 1550M | 32 | 1280 | 20 | 約 10 GB |
| Large-v3-turbo | 809M | 32 | 1280 | 20 | 約 6 GB（4 層解碼器） |

Large-v3-turbo（2024）把解碼器從 32 層砍到 4 層。解碼快 8 倍，WER 退步不到 1 個百分點。正是這個解碼速度的解放，讓 Whisper-turbo 成為 2026 年即時語音代理程式的預設選擇。

### Whisper 不做的事

- 不做語者分段（誰在說話）。那要搭配 pyannote。
- 原生不支援即時串流 —— 30 秒視窗是固定的。現代的包裝層（`faster-whisper`、`WhisperX`）靠 VAD 加重疊硬接上串流。
- 沒有外部分塊的話，脈絡不會超過 30 秒。實務上運作得不錯，因為人類說話很少需要長距離脈絡才能轉錄。

### 2026 年的版圖

| 任務 | 模型 | 備註 |
|------|-------|-------|
| 英文 ASR | Whisper-turbo、Moonshine | Moonshine 在邊緣裝置上快 4 倍 |
| 多語言 ASR | Whisper-large-v3 | 97 種語言 |
| 串流 ASR | faster-whisper + VAD | 150 ms 的延遲目標做得到 |
| TTS | Piper、XTTS-v2、Kokoro | 同樣是編碼器解碼器模式，只是長得像 Whisper |
| 音訊 + 語言 | AudioLM、SeamlessM4T | 文字詞元與音訊詞元共處一個 transformer |

## 動手實作

請看 `code/main.py`。我們不訓練 Whisper —— 我們把對數梅爾頻譜圖管線與任務詞元提示詞的組裝器做出來。那才是你在正式環境真正會碰到的部分。

### 步驟 1：合成音訊

產生一段 1 秒、440 Hz 的正弦波，取樣率 16 kHz。共 16,000 個樣本。

### 步驟 2：對數梅爾頻譜圖（簡化版）

完整的梅爾頻譜圖需要 FFT。我們做一個簡化版的分幀加每幀能量，讓整條管線看得清楚又不必依賴 `librosa`：

```python
def frame_signal(x, frame_size=400, hop=160):
    frames = []
    for start in range(0, len(x) - frame_size + 1, hop):
        frames.append(x[start:start + frame_size])
    return frames
```

幀長 25 ms、位移 10 ms。跟 Whisper 的開視窗方式一致。為了教學，每幀能量在這裡代替梅爾頻帶。

### 步驟 3：補零到 30 秒

Whisper 永遠處理 30 秒的塊。把頻譜圖補零（或裁切）到 3,000 幀。

### 步驟 4：組出提示詞的詞元

```python
def whisper_prompt(lang="en", task="transcribe", timestamps=True):
    tokens = ["<|startoftranscript|>", f"<|{lang}|>", f"<|{task}|>"]
    if not timestamps:
        tokens.append("<|notimestamps|>")
    return tokens
```

整個任務控制面就這樣。一個 4 個詞元的前綴。

## 框架應用

```python
import whisper
model = whisper.load_model("large-v3-turbo")
result = model.transcribe("meeting.wav", language="en", task="transcribe")
print(result["text"])
print(result["segments"][0]["start"], result["segments"][0]["end"])
```

更快、而且介面相容 OpenAI 版的做法：

```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3-turbo", compute_type="int8_float16")
segments, info = model.transcribe("meeting.wav", vad_filter=True)
for s in segments:
    print(f"{s.start:.2f} - {s.end:.2f}: {s.text}")
```

**2026 年什麼時候該選 Whisper：**

- 想用一個模型做多語言 ASR。
- 要穩健地轉錄吵雜、來源雜亂的音訊。
- 研究或原型階段的 ASR —— 起步最快的選擇。

**什麼時候該選別的：**

- 邊緣裝置上的超低延遲串流 —— 同等品質下 Moonshine 勝過 Whisper。
- 需要低於 200 ms 的即時對話式 AI —— 用專門的串流 ASR。
- 語者分段 —— Whisper 不做這件事；外接 pyannote。

## 產出交付

請看 `outputs/skill-asr-configurator.md`。這項技能會替一個新的語音應用挑選 ASR 模型、解碼參數與前處理管線。

## 練習

1. **簡單。** 執行 `code/main.py`。確認一段 1 秒、16 kHz、位移 10 ms 的訊號幀數約為 100 幀。30 秒則約 3,000 幀。
2. **中等。** 用 `numpy.fft` 建出完整的對數梅爾頻譜圖。驗證 80 個梅爾頻帶與 `librosa.feature.melspectrogram(n_mels=80)` 在數值誤差內一致。
3. **困難。** 實作串流推論：把音訊切成 10 秒的視窗、重疊 2 秒，對每一塊跑 Whisper，再把轉錄稿合併起來。在一段 5 分鐘的 podcast 樣本上，量測它與單次通過相比的詞錯誤率。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 梅爾頻譜圖 | 「音訊影像」 | 二維表示：一軸是頻率頻帶，另一軸是時間幀；每一格是取過對數的能量。 |
| 對數梅爾 | 「Whisper 看到的東西」 | 梅爾頻譜圖再取對數；近似人耳對音量的感受。 |
| 幀 | 「一個時間切片」 | 一個 25 ms 的樣本視窗；以 10 ms 位移互相重疊。 |
| 任務詞元 | 「語音的提示詞前綴」 | 解碼器提示詞裡像 `<\|transcribe\|>`／`<\|translate\|>` 這樣的特殊詞元。 |
| 語音活動偵測（VAD） | 「找出人聲」 | 在 ASR 之前把靜音濾掉的把關機制；成本省下一大截。 |
| CTC | 「Connectionist Temporal Classification」 | 經典的 ASR 損失函式，可在不做對齊的情況下訓練；Whisper 並*不*使用它。 |
| Whisper-turbo | 「小解碼器、完整編碼器」 | large-v3 的編碼器加 4 層解碼器；解碼快 8 倍。 |
| Faster-whisper | 「正式環境的包裝層」 | 以 CTranslate2 重新實作；支援 int8 量化；比 OpenAI 的參考實作快 4 倍。 |

## 延伸閱讀

- [Radford et al. (2022). Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356) —— Whisper 論文。
- [OpenAI Whisper repo](https://github.com/openai/whisper) —— 參考程式碼與模型權重。讀 `whisper/model.py`，約 400 行就能從頭到尾看完 Conv1D 前段 + 編碼器 + 解碼器。
- [OpenAI Whisper — `whisper/decoding.py`](https://github.com/openai/whisper/blob/main/whisper/decoding.py) —— 步驟 5 到 6 描述的 beam search 加任務詞元邏輯就在這裡；500 行，完全讀得懂。
- [Baevski et al. (2020). wav2vec 2.0: A Framework for Self-Supervised Learning of Speech Representations](https://arxiv.org/abs/2006.11477) —— 前身；在某些場景下特徵仍是 SOTA。
- [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) —— 正式環境的包裝層，比參考實作快 4 倍。
- [Jia et al. (2024). Moonshine: Speech Recognition for Live Transcription and Voice Commands](https://arxiv.org/abs/2410.15608) —— 2024 年對邊緣裝置友善的 ASR，形狀像 Whisper 但更小。
- [HuggingFace blog — "Fine-Tune Whisper For Multilingual ASR with 🤗 Transformers"](https://huggingface.co/blog/fine-tune-whisper) —— 標準的微調配方，含梅爾頻譜圖前處理器與詞元時間戳的處理。
- [HuggingFace `modeling_whisper.py`](https://github.com/huggingface/transformers/blob/main/src/transformers/models/whisper/modeling_whisper.py) —— 完整實作（編碼器、解碼器、交叉注意力、生成），與本單元的架構圖一一對應。
