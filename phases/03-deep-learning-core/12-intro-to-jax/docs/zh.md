# JAX 入門

> PyTorch 就地改動張量。TensorFlow 建圖。JAX 編譯純函式。最後這一項會改變你思考深度學習的方式。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 03 · 01-10、基礎 NumPy
**時間：** 約 90 分鐘

## 學習目標

- 用 JAX 的函式式 API（jax.numpy、jax.grad、jax.jit、jax.vmap）寫出純函式風格的神經網路程式碼
- 說清楚 PyTorch 的即時就地改動模型，與 JAX 的函式式編譯模型之間關鍵的設計差異
- 套用 jit 即時編譯與 vmap 自動向量化，讓訓練迴圈比天真的 Python 寫法快上一截
- 在 JAX 裡訓練一個簡單的網路，並把顯式的狀態管理拿來跟 PyTorch 的物件導向做法對照

## 問題所在

你會用 PyTorch 打造神經網路。你定義一個 `nn.Module`、呼叫 `.backward()`、讓最佳化器走一步。它能用，幾百萬人都在用。

但 PyTorch 的骨子裡烙著一個限制：它以即時模式一次追蹤一個運算，而且是在 Python 裡做。每一次 `tensor + tensor` 都是一次獨立的核心啟動。每一個訓練步驟都要重新解譯同一份 Python 程式碼。在你需要跨 2,048 顆 TPU 訓練一個 5,400 億參數的模型之前，這都沒問題。到了那個規模，這些額外開銷就會壓死你。

Google DeepMind 用 JAX 訓練 Gemini。Anthropic 用 JAX 訓練了 Claude。這些不是小工程 —— 它們是地球上規模最大的神經網路訓練任務。他們選 JAX，是因為 JAX 把你的訓練迴圈當成一支可編譯的程式，而不是一連串 Python 呼叫。

JAX 就是 NumPy 加上三項超能力：自動微分、即時編譯成 XLA，以及自動向量化。你寫一個處理單筆樣本的函式，JAX 就回你一個能處理整個批次、算出梯度、編譯成機器碼、並跨多個裝置執行的函式 —— 而原本那個函式一行都不用改。

## 核心概念

### JAX 的哲學

JAX 是一套函式式框架。沒有類別、沒有可變狀態、沒有 `.backward()` 方法。取而代之的是：

| PyTorch | JAX |
|---------|-----|
| 帶狀態的 `nn.Module` 類別 | 純函式：`f(params, x) -> y` |
| `loss.backward()` | `jax.grad(loss_fn)(params, x, y)` |
| 即時執行 | 透過 XLA 做即時編譯 |
| `for x in batch:` 手寫迴圈 | `jax.vmap(f)` 自動向量化 |
| `DataParallel` / `FSDP` | `jax.pmap(f)` 自動平行化 |
| 可變的 `model.parameters()` | 不可變的陣列 pytree |

這不是風格偏好，這是編譯器的要求。即時編譯需要純函式 —— 相同輸入永遠產生相同輸出，沒有副作用。正是這道限制，讓百倍的加速成為可能。

### jax.numpy：熟悉的表層

JAX 在加速器上重新實作了 NumPy 的 API：

```python
import jax.numpy as jnp

a = jnp.array([1.0, 2.0, 3.0])
b = jnp.array([4.0, 5.0, 6.0])
c = jnp.dot(a, b)
```

一樣的函式名稱、一樣的廣播規則、一樣的切片語意。但陣列住在 GPU／TPU 上，而且每一個運算都能被編譯器追蹤。

有一個關鍵差異：JAX 的陣列是不可變的。不能寫 `a[0] = 5`，要寫 `a = a.at[0].set(5)`。頭一個星期會覺得彆扭，然後你就懂了 —— 不可變正是 `grad`、`jit`、`vmap` 這些函式轉換能互相組合的原因。

### jax.grad：函式式自動微分

PyTorch 把梯度掛在張量上（`.grad`）。JAX 把梯度掛在函式上。

```python
import jax

def f(x):
    return x ** 2

df = jax.grad(f)
df(3.0)
```

`jax.grad` 吃進一個函式，回傳一個會算梯度的新函式。不用呼叫 `.backward()`，也不用在張量上存計算圖。梯度只是另一個函式，你可以呼叫它、組合它，或把它即時編譯掉。

這種組合可以無限疊下去：

```python
d2f = jax.grad(jax.grad(f))
d2f(3.0)
```

二階導數、三階導數、Jacobian、Hessian，全都靠組合 `grad` 得到。PyTorch 也做得到（`torch.autograd.functional.hessian`），但那是外掛上去的。在 JAX 裡，這是地基。

限制是：`grad` 只對純函式有效。裡面不能有 print（它們會在追蹤時執行，而不是在真正執行時），不能改動外部狀態，也不能在沒有顯式管理金鑰的情況下產生隨機數。

### jit：編譯成 XLA

```python
@jax.jit
def train_step(params, x, y):
    loss = loss_fn(params, x, y)
    return loss

fast_step = jax.jit(train_step)
```

第一次呼叫時，JAX 會追蹤這個函式 —— 它記下有哪些運算發生，但不真的執行它們。接著把這份追蹤結果交給 XLA（Accelerated Linear Algebra），也就是 Google 為 TPU 與 GPU 打造的編譯器。XLA 會把運算融合起來、消掉多餘的記憶體複製，並產生最佳化過的機器碼。

之後的呼叫完全繞過 Python。編譯後的程式碼以 C++ 的速度在加速器上跑。

jit 幫得上忙的時候：
- 訓練步驟（同一份計算重複幾千次）
- 推論（同一個模型，不同輸入）
- 任何會被呼叫超過一次、且輸入形狀相近的函式

jit 反而礙事的時候：
- 帶有依賴數值的 Python 控制流程的函式（例如 `if x > 0`，而 x 是被追蹤的陣列）
- 只跑一次的計算（編譯開銷比執行時間還久）
- 除錯（追蹤把真正的執行過程藏起來了）

控制流程的限制是真的。`jax.lax.cond` 取代 `if/else`，`jax.lax.scan` 取代 `for` 迴圈。這些不是可選項 —— 它們就是換取編譯所付的代價。

### vmap：自動向量化

你寫一個處理單筆樣本的函式：

```python
def predict(params, x):
    return jnp.dot(params['w'], x) + params['b']
```

`vmap` 把它拉抬成能處理整個批次：

```python
batch_predict = jax.vmap(predict, in_axes=(None, 0))
```

`in_axes=(None, 0)` 的意思是：不要在 `params` 上做批次（它是共用的），而是沿著 `x` 的第 0 軸做批次。不用手寫 `for` 迴圈，不用 reshape，也不用一路把批次維度穿進去。JAX 自己弄清楚批次維度，並把整段計算向量化。

這不是語法糖。`vmap` 產生的是融合過的向量化程式碼，比 Python 迴圈快 10 到 100 倍。而且它跟 `jit` 與 `grad` 都能組合：

```python
per_example_grads = jax.vmap(jax.grad(loss_fn), in_axes=(None, 0, 0))
```

逐樣本梯度，一行搞定。在 PyTorch 裡，不動用歪招幾乎做不到。

### pmap：跨裝置的資料平行

```python
parallel_step = jax.pmap(train_step, axis_name='devices')
```

`pmap` 把函式複製到所有可用的裝置（GPU／TPU）上，並把批次切開。在函式內部，`jax.lax.pmean` 與 `jax.lax.psum` 負責跨裝置同步梯度。

Google 就是用 `pmap`（以及它的後繼者 `shard_map`）跨數千顆 TPU v5e 晶片訓練 Gemini。這套程式設計模型是：先寫單一裝置的版本，再用 `pmap` 包起來，收工。

### Pytree：通用的資料結構

JAX 操作的對象是「pytree」—— 由 list、tuple、dict 與陣列嵌套組合出來的東西。你的模型參數就是一棵 pytree：

```python
params = {
    'layer1': {'w': jnp.zeros((784, 256)), 'b': jnp.zeros(256)},
    'layer2': {'w': jnp.zeros((256, 128)), 'b': jnp.zeros(128)},
    'layer3': {'w': jnp.zeros((128, 10)),  'b': jnp.zeros(10)},
}
```

每一種 JAX 的函式轉換 —— `grad`、`jit`、`vmap` —— 都知道怎麼走過 pytree。`jax.tree.map(f, tree)` 會把 `f` 套到每一片葉子上。最佳化器就是這樣一次更新完所有參數：

```python
params = jax.tree.map(lambda p, g: p - lr * g, params, grads)
```

沒有 `.parameters()` 方法，也不用註冊參數。樹的結構本身就是模型。

### 函式式風格與物件導向

PyTorch 把狀態存在物件裡：

```python
class Model(nn.Module):
    def __init__(self):
        self.linear = nn.Linear(784, 10)

    def forward(self, x):
        return self.linear(x)
```

JAX 用純函式搭配顯式的狀態：

```python
def predict(params, x):
    return jnp.dot(x, params['w']) + params['b']
```

params 是傳進來的。什麼都不存，什麼都不改。這讓每個函式都可測試、可組合、可編譯。代價是參數得你自己管 —— 或者改用 Flax、Equinox 這類函式庫。

### JAX 生態系

JAX 給你基本元件，函式庫給你手感：

| 函式庫 | 角色 | 風格 |
|---------|------|-------|
| **Flax**（Google） | 神經網路層 | 帶顯式狀態的 `nn.Module` |
| **Equinox**（Patrick Kidger） | 神經網路層 | 以 pytree 為核心，很 Pythonic |
| **Optax**（DeepMind） | 最佳化器 + 學習率排程 | 可組合的梯度轉換 |
| **Orbax**（Google） | 檢查點 | 存檔／還原 pytree |
| **CLU**（Google） | 指標 + 記錄 | 訓練迴圈工具 |

Optax 是標準的最佳化器函式庫。它把梯度轉換（Adam、SGD、裁剪）跟參數更新拆開，組合起來因此輕而易舉：

```python
optimizer = optax.chain(
    optax.clip_by_global_norm(1.0),
    optax.adam(learning_rate=1e-3),
)
```

### 什麼時候該用 JAX，什麼時候該用 PyTorch

| 面向 | JAX | PyTorch |
|--------|-----|---------|
| TPU 支援 | 一等公民（兩者都是 Google 做的） | 社群維護（torch_xla） |
| GPU 支援 | 不錯（透過 XLA 用 CUDA） | 業界最強（原生 CUDA） |
| 除錯 | 難（追蹤加編譯） | 容易（即時執行，一行一行看） |
| 生態系 | 偏研究（Flax、Equinox） | 極大（HuggingFace、torchvision 等） |
| 求職 | 小眾（Google／DeepMind／Anthropic） | 主流（到處都要） |
| 大規模訓練 | 更強（XLA、pmap、mesh） | 不錯（FSDP、DeepSpeed） |
| 原型開發速度 | 較慢（函式式的額外成本） | 較快（改了就跑） |
| 生產環境推論 | TensorFlow Serving、Vertex AI | TorchServe、Triton、ONNX |
| 誰在用 | DeepMind（Gemini）、Anthropic（Claude） | Meta（Llama）、OpenAI（GPT）、Stability AI |

老實的答案是：除非你有明確理由要用 JAX，否則就用 PyTorch。那些理由是 —— 你有 TPU 可用、需要逐樣本梯度、要在極大規模下做多裝置訓練，或者你在 Google／DeepMind／Anthropic 工作。

### JAX 裡的隨機數

JAX 沒有全域的隨機狀態。每一個隨機運算都需要一把顯式的 PRNG 金鑰：

```python
key = jax.random.PRNGKey(42)
key1, key2 = jax.random.split(key)
w = jax.random.normal(key1, shape=(784, 256))
```

一開始會覺得煩。但它保證了跨裝置、跨編譯的可重現性 —— 這是 PyTorch 的 `torch.manual_seed` 在多 GPU 環境下無法保證的性質。

```figure
batchnorm-effect
```

## 動手實作

### 步驟 1：環境與資料

我們要用 JAX 與 Optax 在 MNIST 上訓練一個 3 層 MLP。784 個輸入、兩層各 256 與 128 個神經元的隱藏層、10 個輸出類別。

```python
import jax
import jax.numpy as jnp
from jax import random
import optax

def get_mnist_data():
    from sklearn.datasets import fetch_openml
    mnist = fetch_openml('mnist_784', version=1, as_frame=False, parser='auto')
    X = mnist.data.astype('float32') / 255.0
    y = mnist.target.astype('int')
    X_train, X_test = X[:60000], X[60000:]
    y_train, y_test = y[:60000], y[60000:]
    return X_train, y_train, X_test, y_test
```

### 步驟 2：初始化參數

沒有類別。只有一個回傳 pytree 的函式：

```python
def init_params(key):
    k1, k2, k3 = random.split(key, 3)
    scale1 = jnp.sqrt(2.0 / 784)
    scale2 = jnp.sqrt(2.0 / 256)
    scale3 = jnp.sqrt(2.0 / 128)
    params = {
        'layer1': {
            'w': scale1 * random.normal(k1, (784, 256)),
            'b': jnp.zeros(256),
        },
        'layer2': {
            'w': scale2 * random.normal(k2, (256, 128)),
            'b': jnp.zeros(128),
        },
        'layer3': {
            'w': scale3 * random.normal(k3, (128, 10)),
            'b': jnp.zeros(10),
        },
    }
    return params
```

He 初始化，手動做完。三把 PRNG 金鑰從同一顆隨機種子分裂出來。每個權重都是嵌套字典裡的一個不可變陣列。

### 步驟 3：前向傳播

```python
def forward(params, x):
    x = jnp.dot(x, params['layer1']['w']) + params['layer1']['b']
    x = jax.nn.relu(x)
    x = jnp.dot(x, params['layer2']['w']) + params['layer2']['b']
    x = jax.nn.relu(x)
    x = jnp.dot(x, params['layer3']['w']) + params['layer3']['b']
    return x

def loss_fn(params, x, y):
    logits = forward(params, x)
    one_hot = jax.nn.one_hot(y, 10)
    return -jnp.mean(jnp.sum(jax.nn.log_softmax(logits) * one_hot, axis=-1))
```

純函式。參數進去，預測出來。沒有 `self`，沒有存起來的狀態。`loss_fn` 從零算出交叉熵 —— softmax、取對數、取負平均。

### 步驟 4：經 JIT 編譯的訓練步驟

```python
@jax.jit
def train_step(params, opt_state, x, y):
    loss, grads = jax.value_and_grad(loss_fn)(params, x, y)
    updates, opt_state = optimizer.update(grads, opt_state, params)
    params = optax.apply_updates(params, updates)
    return params, opt_state, loss

@jax.jit
def accuracy(params, x, y):
    logits = forward(params, x)
    preds = jnp.argmax(logits, axis=-1)
    return jnp.mean(preds == y)
```

`jax.value_and_grad` 一趟就同時回傳損失值與梯度。`@jax.jit` 裝飾器把兩個函式都編譯成 XLA。第一次呼叫之後，每個訓練步驟都不再碰 Python。

### 步驟 5：訓練迴圈

```python
optimizer = optax.adam(learning_rate=1e-3)

X_train, y_train, X_test, y_test = get_mnist_data()
X_train, X_test = jnp.array(X_train), jnp.array(X_test)
y_train, y_test = jnp.array(y_train), jnp.array(y_test)

key = random.PRNGKey(0)
params = init_params(key)
opt_state = optimizer.init(params)

batch_size = 128
n_epochs = 10

for epoch in range(n_epochs):
    key, subkey = random.split(key)
    perm = random.permutation(subkey, len(X_train))
    X_shuffled = X_train[perm]
    y_shuffled = y_train[perm]

    epoch_loss = 0.0
    n_batches = len(X_train) // batch_size
    for i in range(n_batches):
        start = i * batch_size
        xb = X_shuffled[start:start + batch_size]
        yb = y_shuffled[start:start + batch_size]
        params, opt_state, loss = train_step(params, opt_state, xb, yb)
        epoch_loss += loss

    train_acc = accuracy(params, X_train[:5000], y_train[:5000])
    test_acc = accuracy(params, X_test, y_test)
    print(f"Epoch {epoch + 1:2d} | Loss: {epoch_loss / n_batches:.4f} | "
          f"Train Acc: {train_acc:.4f} | Test Acc: {test_acc:.4f}")
```

10 個 epoch，約 97% 的測試準確率。第一個 epoch 很慢（在做即時編譯），第 2 到 10 個 epoch 就很快。

注意有哪些東西不見了：沒有 `.zero_grad()`、沒有 `.backward()`、沒有 `.step()`。整個更新就是一次組合起來的函式呼叫。梯度被算出來、被 Adam 轉換、再套用到參數上 —— 全都發生在 `train_step` 裡面。

## 框架應用

### Flax：Google 的標準

Flax 是最常見的 JAX 神經網路函式庫。它把 `nn.Module` 加回來，但搭配顯式的狀態管理：

```python
import flax.linen as nn

class MLP(nn.Module):
    @nn.compact
    def __call__(self, x):
        x = nn.Dense(256)(x)
        x = nn.relu(x)
        x = nn.Dense(128)(x)
        x = nn.relu(x)
        x = nn.Dense(10)(x)
        return x

model = MLP()
params = model.init(jax.random.PRNGKey(0), jnp.ones((1, 784)))
logits = model.apply(params, x_batch)
```

結構跟 PyTorch 一樣，但 `params` 跟模型是分開的。`model.init()` 建出參數，`model.apply(params, x)` 跑前向傳播。模型物件本身沒有狀態。

### Equinox：更 Pythonic 的選擇

Equinox（作者 Patrick Kidger）把模型表示成 pytree：

```python
import equinox as eqx

model = eqx.nn.MLP(
    in_size=784, out_size=10, width_size=256, depth=2,
    activation=jax.nn.relu, key=jax.random.PRNGKey(0)
)
logits = model(x)
```

模型本身就是一棵 pytree，不需要 `.apply()`。參數就是這棵樹的葉子。這更貼近 JAX 的思考方式。

### Optax：可組合的最佳化器

Optax 把梯度轉換跟更新解耦：

```python
schedule = optax.warmup_cosine_decay_schedule(
    init_value=0.0, peak_value=1e-3,
    warmup_steps=1000, decay_steps=50000
)

optimizer = optax.chain(
    optax.clip_by_global_norm(1.0),
    optax.adamw(learning_rate=schedule, weight_decay=0.01),
)
```

梯度裁剪、學習率暖身、權重衰減 —— 全部組合成一串轉換。每個轉換看到梯度、改動它，再交給下一個。沒有一個包山包海的最佳化器類別。

## 產出交付

**安裝：**

```bash
pip install jax jaxlib optax flax
```

要支援 GPU：

```bash
pip install jax[cuda12]
```

要用 TPU（Google Cloud）：

```bash
pip install jax[tpu] -f https://storage.googleapis.com/jax-releases/libtpu_releases.html
```

**效能上的地雷：**

- 第一次 JIT 呼叫很慢（要編譯）。做基準測試前先暖機。
- 避免在 JIT 內部用 Python 迴圈跑 JAX 陣列。改用 `jax.lax.scan` 或 `jax.lax.fori_loop`。
- `jax.debug.print()` 在 JIT 裡面能用，一般的 `print()` 不行。
- 用 `jax.profiler` 或 TensorBoard 做剖析。XLA 編譯可能把瓶頸藏起來。
- JAX 預設會預先配置 75% 的 GPU 記憶體。設定 `XLA_PYTHON_CLIENT_PREALLOCATE=false` 可以關掉。

**檢查點：**

```python
import orbax.checkpoint as ocp
checkpointer = ocp.PyTreeCheckpointer()
checkpointer.save('/tmp/model', params)
restored = checkpointer.restore('/tmp/model')
```

**本單元會產出：**
- `outputs/prompt-jax-optimizer.md` —— 一段提示詞，用來挑選合適的 JAX 最佳化器設定
- `outputs/skill-jax-patterns.md` —— 一項技能，涵蓋 JAX 裡的函式式寫法

## 練習

1. 為這個 MLP 加上 dropout。在 JAX 裡，dropout 需要一把 PRNG 金鑰 —— 把金鑰一路穿過前向傳播，並為每一層 dropout 分裂出一把。比較有 dropout 與沒有 dropout 的測試準確率。

2. 用 `jax.vmap` 為一個 32 張 MNIST 圖片的批次算出逐樣本梯度。算出每筆樣本的梯度範數。哪些樣本的梯度最大，為什麼？

3. 把手寫的 forward 函式換成一個通用的 `mlp_forward(params, x)`，讓它對任意層數都能用。用 `jax.tree.leaves` 自動判斷深度。

4. 為訓練步驟做基準測試，比較有 `@jax.jit` 與沒有的差別。各跑 100 步計時。在你的硬體上加速多少倍？第一次呼叫的編譯開銷是多少？

5. 用 `optax.chain(optax.clip_by_global_norm(1.0), optax.adam(1e-3))` 組合出梯度裁剪。分別在有裁剪與沒裁剪的情況下訓練。把訓練過程中的梯度範數畫出來，看看效果。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|----------------------|
| XLA | 「讓 JAX 變快的那個東西」 | Accelerated Linear Algebra —— 一個會融合運算、並從計算圖產生最佳化 GPU／TPU 核心的編譯器 |
| JIT | 「即時編譯」 | JAX 在第一次呼叫時追蹤函式、編譯成 XLA，之後的呼叫都跑編譯過的版本 |
| 純函式 | 「沒有副作用」 | 輸出只取決於輸入的函式 —— 沒有全域狀態、沒有就地改動、沒有不帶顯式金鑰的隨機性 |
| vmap | 「自動批次」 | 把處理單筆樣本的函式轉換成處理整個批次的函式，不必重寫 |
| pmap | 「自動平行化」 | 把函式複製到多個裝置上，並把輸入批次切開 |
| Pytree | 「嵌套的陣列字典」 | 任何由 list、tuple、dict 與陣列組成的嵌套結構，JAX 都能走過並轉換它 |
| 追蹤 | 「把計算記錄下來」 | JAX 用抽象值執行函式來建出計算圖，過程中不算出真正的結果 |
| 函式式自動微分 | 「函式的 grad」 | 靠轉換函式來算導數，而不是在張量上掛梯度儲存空間 |
| Optax | 「JAX 的最佳化器函式庫」 | 一套可組合的梯度轉換函式庫 —— Adam、SGD、裁剪、排程 —— 能串接起來 |
| Flax | 「JAX 的 nn.Module」 | Google 為 JAX 打造的神經網路函式庫，加上層的抽象，同時保持狀態顯式 |

## 延伸閱讀

- JAX documentation: https://jax.readthedocs.io/ —— 官方文件，關於 grad、jit 與 vmap 的教學寫得很好
- "JAX: composable transformations of Python+NumPy programs" (Bradbury et al., 2018) —— 闡述設計哲學的原始論文
- Flax documentation: https://flax.readthedocs.io/ —— Google 為 JAX 打造的神經網路函式庫
- Patrick Kidger, "Equinox: neural networks in JAX via callable PyTrees and filtered transformations" (2021) —— Flax 之外更 Pythonic 的選擇
- DeepMind, "Optax: composable gradient transformation and optimisation" —— 標準的最佳化器函式庫
- "You Don't Know JAX" (Colin Raffel, 2020) —— 一份關於 JAX 地雷與寫法的實務指南，作者是 T5 論文的作者之一
