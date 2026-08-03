# Whisper —— 架構與微調

> Whisper 是一個 30 秒視窗的 transformer 編碼器解碼器，用 68 萬小時的多語言弱監督音訊-文字配對訓練而成。一套架構、多種任務，在 99 種語言上都很穩健。2026 年的 ASR 參考標準。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 6 · 04（ASR）、階段 5 · 10（注意力機制）、階段 7 · 05（完整的 Transformer）
**時間：** 約 75 分鐘

## 問題所在

Whisper 由 OpenAI 在 2022 年 9 月釋出，是第一個以日用品形式交付的 ASR 模型：貼上音訊、拿到文字、99 種語言、對噪音穩健、筆電就能跑。到 2024 年 OpenAI 已經推出 Large-v3 與 Turbo 版本；到 2026 年，從 podcast 轉錄、語音助理到 YouTube 字幕，Whisper 都是預設的基準線。

但 Whisper 不是一條可以永遠當黑盒子的管線。領域偏移會把它打爆 —— 技術術語、說話者口音、專有名詞、短片段、靜音。你得知道：

1. 它內部到底是什麼。
2. 怎麼正確地餵它分塊、串流或長音檔的音訊。
3. 什麼時候該微調，以及怎麼微調。

## 核心概念

![Whisper 編碼器解碼器、任務、分塊推論、微調](../assets/whisper.svg)

**架構。** 標準的 transformer 編碼器解碼器。

- 輸入：30 秒的對數梅爾頻譜圖，80 個梅爾頻帶，10 ms hop → 3000 幀。更短的片段補零，更長的片段分塊。
- 編碼器：卷積降採樣（stride 2）+ `N` 個 transformer 區塊。以 Large-v3 為例：32 層、1280 維、20 個注意力頭。
- 解碼器：`N` 個 transformer 區塊，含因果自注意力 + 對編碼器輸出的交叉注意力。大小跟編碼器相同。
- 輸出：涵蓋 51,865 個詞元詞彙表的 BPE 詞元。

Large-v3 有 15.5 億參數。Turbo 用 4 層解碼器（原本 32 層），延遲砍掉 8 倍，WER 只掉不到 1%。

**提示詞格式。** Whisper 是一個由解碼器提示詞中的特殊詞元操控的多任務訓練模型：

```
<|startoftranscript|><|en|><|transcribe|><|notimestamps|> Hello world.<|endoftext|>
```

- `<|en|>` —— 語言標籤；強制決定是翻譯還是轉錄的行為。
- `<|transcribe|>` 或 `<|translate|>` —— 把任何語言的輸入翻成英文輸出，或是逐字轉錄。
- `<|notimestamps|>` —— 跳過詞層級的時間戳（更快）。

提示詞正是讓一個模型能做很多任務的關鍵。把 `<|en|>` 換成 `<|fr|>`，它就轉錄法文。

**30 秒視窗。** 一切都被釘在 30 秒上。更長的片段要分塊；更短的片段要補零。視窗天生不支援串流 —— 這就是 WhisperX、Whisper-Streaming 與 faster-whisper 存在的理由。

**對數梅爾正規化。** `(log_mel - mean) / std`，其中統計量來自 Whisper 自己的訓練語料。你*必須*用 Whisper 的前處理（`whisper.audio.log_mel_spectrogram`），不能用 `librosa.feature.melspectrogram`。

### 2026 年的各種版本

| 版本 | 參數量 | 延遲（A100） | WER（LibriSpeech-clean） |
|---------|--------|----------------|------------------------|
| Tiny | 39M | 1× 即時 | 5.4% |
| Base | 74M | 1× | 4.1% |
| Small | 244M | 1× | 3.0% |
| Medium | 769M | 1× | 2.7% |
| Large-v3 | 1.55B | 2× | 1.8% |
| Large-v3-turbo | 809M | 8× | 1.58% |
| Whisper-Streaming（2024） | 1.55B | 串流 | 2.0% |

### 微調

2026 年的標準流程：

1. 蒐集 10–100 小時目標領域的音訊，附上對齊好的轉錄稿。
2. 用 `transformers.Seq2SeqTrainer` 搭配 `generate_with_loss` callback 來跑。
3. 參數高效的做法：在注意力層的 `q_proj`、`k_proj`、`v_proj` 上掛 LoRA，可以把 GPU 記憶體降到 1/4，WER 代價不到 0.3。
4. 如果你只有不到 10 小時的資料，就把編碼器凍結。只調解碼器。
5. 用 Whisper 自己的分詞器與提示詞格式；絕對不要換分詞器。

社群的結果：拿 20 小時的醫療口述資料微調 Medium，在醫療詞彙上的 WER 從 12% 掉到 4.5%。拿 4 小時的冰島語微調 Turbo，WER 從 18% 掉到 6%。

```figure
sp-asr-attention
```

## 動手實作

### 步驟 1：直接開箱跑 Whisper

```python
import whisper
model = whisper.load_model("large-v3-turbo")
result = model.transcribe(
    "clip.wav",
    language="en",
    task="transcribe",
    temperature=0.0,
    condition_on_previous_text=False,  # prevents runaway repetition
)
print(result["text"])
for seg in result["segments"]:
    print(f"[{seg['start']:.2f}–{seg['end']:.2f}] {seg['text']}")
```

幾個你永遠該覆寫掉的預設值：`temperature=0.0`（採樣預設是 0.0 → 0.2 → 0.4 … 的回退鏈）、`condition_on_previous_text=False`（避免幻覺連鎖擴散的問題），以及 `no_speech_threshold=0.6`（靜音偵測）。

### 步驟 2：分塊處理長音檔

```python
# whisperx is the 2026 reference for long-form with word-level timestamps
import whisperx
model = whisperx.load_model("large-v3-turbo", device="cuda", compute_type="float16")
segments = model.transcribe("1hour.mp3", batch_size=16, chunk_size=30)
```

WhisperX 加了 (1) Silero VAD 把關、(2) 透過 wav2vec 2.0 做詞層級對齊、(3) 用 `pyannote.audio` 做語者分段。2026 年正式環境轉錄的主力。

### 步驟 3：用 LoRA 微調

```python
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from peft import LoraConfig, get_peft_model

model = WhisperForConditionalGeneration.from_pretrained("openai/whisper-large-v3-turbo")
lora = LoraConfig(
    r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"],
    lora_dropout=0.1, bias="none", task_type="SEQ_2_SEQ_LM",
)
model = get_peft_model(model, lora)
# model.print_trainable_parameters()  -> ~3M trainable / 809M total
```

接著就是標準的 Trainer 迴圈。每 1000 步存一次檢查點。用保留集上的 WER 做評估。

### 步驟 4：檢視每一層學到了什麼

```python
# Grab cross-attention weights during decode to see what the decoder attends to.
with torch.inference_mode():
    out = model.generate(
        input_features=features,
        return_dict_in_generate=True,
        output_attentions=True,
    )
# out.cross_attentions: layer × head × step × src_len
```

用熱圖畫出來 —— 你會看到解碼器逐步掃過編碼器的幀時形成的對角線對齊。那條對角線就是 Whisper 對詞層級時間戳的概念。

## 框架應用

2026 年的那一套：

| 情境 | 選什麼 |
|-----------|------|
| 一般英文、離線 | 透過 `whisperx` 用 Large-v3-turbo |
| 行動端／邊緣裝置 | 量化後（int8）的 Whisper-Tiny 或 Moonshine |
| 多語言長音檔 | 透過 `whisperx` 用 Large-v3 + 語者分段 |
| 低資源語言 | 用 LoRA 微調 Medium 或 Turbo |
| 串流（2 秒延遲） | Whisper-Streaming 或 Parakeet-TDT |
| 詞層級時間戳 | WhisperX（透過 wav2vec 2.0 做強制對齊） |

`faster-whisper`（CTranslate2 後端）是 2026 年在 CPU+GPU 上最快的推論執行環境 —— 輸出完全相同，速度是原版的 4 倍。

## 到了 2026 年還是常被交付出去的陷阱

- **靜音上的幻覺文字。** Whisper 用字幕訓練，裡面包含「Thanks for watching!」、「Subscribe!」、歌詞。呼叫之前一定要用 VAD 把關。
- **`condition_on_previous_text` 的連鎖效應。** 一次幻覺就會污染後續的視窗。除非你需要跨塊的流暢度，否則設成 `False`。
- **短片段補零。** 一段 2 秒的片段被補到 30 秒，可能會在尾端的靜音裡產生幻覺。用 `pad=False` 或以 VAD 把關。
- **梅爾統計量用錯。** 用 librosa 的梅爾而不是 Whisper 的，輸出會接近隨機。要用 `whisper.audio.log_mel_spectrogram`。

## 產出交付

存成 `outputs/skill-whisper-tuner.md`。針對指定領域，設計一條 Whisper 的微調或推論管線。

## 練習

1. **簡單。** 跑 `code/main.py`。它會對一段 Whisper 風格的提示詞做分詞、計算解碼後的形狀預算，並印出一段 10 分鐘片段的分塊排程。
2. **中等。** 安裝 `faster-whisper`，轉錄一段 10 分鐘的 podcast，跟人工轉錄稿比對 WER。試試 `language="auto"` 對上強制指定 `language="en"`。
3. **困難。** 用 HF 的 `datasets`，挑一個 Whisper 表現不好的語言（例如烏爾都語），用 LoRA 在 2 小時的資料上微調 Medium 兩個 epoch，並回報 WER 的變化量。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|-----------------|-----------------------|
| 30 秒視窗 | Whisper 的上限 | 硬性的輸入上限；更長的音訊要分塊。 |
| SOT | 轉錄稿的開頭 | `<\|startoftranscript\|>` 啟動解碼器的提示詞。 |
| 時間戳詞元 | 時間上的對齊 | 每個 0.02 秒的偏移量在 51k 詞彙表裡都是一個特殊詞元。 |
| Turbo | 那個快的版本 | 4 層解碼器，快 8 倍，WER 退步不到 1%。 |
| WhisperX | 長音檔的包裝層 | VAD + Whisper + wav2vec 對齊 + 語者分段。 |
| LoRA 微調 | 高效的調整方式 | 在注意力上加低秩適配器；只訓練約 0.3% 的參數。 |
| 幻覺 | 那種無聲的失敗 | Whisper 從噪音／靜音裡生出流暢的英文。 |

## 延伸閱讀

- [Radford et al. (2022). Whisper paper](https://arxiv.org/abs/2212.04356) —— 最初的架構與訓練配方。
- [OpenAI (2024). Whisper Large-v3-turbo release](https://github.com/openai/whisper/discussions/2363) —— 4 層解碼器，加速 8 倍。
- [Bain et al. (2023). WhisperX](https://arxiv.org/abs/2303.00747) —— 長音檔、詞層級對齊、語者分段。
- [Systran — faster-whisper repo](https://github.com/SYSTRAN/faster-whisper) —— CTranslate2 後端，快 4 倍。
- [HuggingFace — Whisper fine-tune tutorial](https://huggingface.co/blog/fine-tune-whisper) —— 標準的 LoRA／全參數微調走訪。
