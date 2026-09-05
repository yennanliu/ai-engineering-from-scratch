# MCP 模型輸入：Sampling 遷移與無狀態 MRTR

> MCP 2026-07-28 對新設計棄用了 Sampling，並移除了伺服器對客戶端的請求通道。如果既有的工作流程仍然需要客戶端的模型，伺服器就回傳一個 `input_required` 結果，客戶端再帶著模型輸出重試原本的請求。推理迴圈因此在協定層變得明確、有界限，而且無狀態。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 10（資源與提示詞）
**時間：** 約 75 分鐘

## 學習目標

- 說明為什麼 MCP 2026-07-28 棄用 Sampling，並為新伺服器選擇「直接整合模型」這個預設。
- 實作一條相容性工作流程，透過 Multi Round-Trip Requests（MRTR）承載 `sampling/createMessage`。
- 把協定修訂版與客戶端能力放進每一則請求的 `_meta` 物件。
- 回傳 `resultType: "input_required"`，並用全新的 JSON-RPC id 重試原本的方法。
- 為 `requestState` 加上完整性保護，並把它綁到主體、方法、參數與到期時間上。
- 用能力檢查、核准、回應驗證與回合上限，替模型輔助迴圈設下界限。

## 協定之前的那個決定

像 `summarize_repo` 這樣的工具，需要兩種工作：

1. 確定性工作：列出檔案、讀取被允許的檔案、驗證路徑，並組裝內容。
2. 模型工作：挑出具代表性的檔案，並綜合出摘要。

現在你有兩種都合理的架構。

### 新伺服器：直接對接模型供應商

這是目前的預設。伺服器自己掌管模型選擇、憑證、預算、重試與可觀測性。它回傳一則普通的 `tools/call` 結果給 MCP 客戶端。

當伺服器本來就是一個託管服務，或當「可預期的模型行為」比「使用宿主的模型」更重要時，就選這條。

### 既有的 Sampling 工作流程：把它遷移到 MRTR

在棄用緩衝期內 Sampling 仍然存在。一台鎖定 2026-07-28 的伺服器，不能即時送一則 `sampling/createMessage` 請求回給客戶端。它改為把那則請求嵌進一個 `InputRequiredResult`。

只有在「使用客戶端的模型與憑證」確實是產品需求時，才選這條相容路徑。同時要記下移除計畫，因為新的實作不該再採用已棄用的 Sampling。

## 無狀態契約

2026 年 7 月的協定沒有 `initialize` 交換、沒有 `notifications/initialized`，也沒有 `Mcp-Session-Id`。每一則請求都帶著以前住在握手裡的那些資訊：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "summarize_repo",
    "arguments": {"audience": "developer"},
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {"sampling": {}},
      "io.modelcontextprotocol/clientInfo": {
        "name": "lesson-client",
        "version": "1.0.0"
      }
    }
  }
}
```

伺服器在每一則請求上驗證修訂版。版本缺漏或不是字串屬於 invalid params，`-32602`。字串合法但不受支援則回傳 `-32022`，並附上精確的資料 `{"supported":["2026-07-28"],"requested":"<client version>"}`。缺少 Sampling 能力回傳 `-32021`，並把 `data.requiredCapabilities` 設為 `{"sampling":{}}`。

沒有 JSON-RPC `id` 的信封是通知。接收方可以處理它，但既不發出成功回應，也不發出錯誤回應。Streamable HTTP 轉接層對被接受的通知回傳 `202 Accepted` 且沒有主體。

伺服器同時實作 `server/discover`，帶著確切的 `supportedVersions` 鍵、能力、`ttlMs` 與 `cacheScope`，讓客戶端能在呼叫工具之前先學會並快取伺服器契約。因為發現公告了 `tools`，伺服器也必須實作必備的 `tools/list`。它那份確定性的 `summarize_repo` 描述包含一份有效的物件型 `inputSchema`、`resultType: "complete"`、伺服器身分中繼資料，以及公開的快取提示。

每一個成功的現代結果都有一個判別欄位：

- `resultType: "complete"` 代表操作已完成。
- `resultType: "input_required"` 代表客戶端必須滿足內嵌的請求並重試。
- 擴充可以定義額外的結果型別。Tasks 擴充在單元 13 裡加上了 `"task"`。

## 一個 MRTR 回合

伺服器在處理請求的過程中無法回頭呼叫客戶端。它改為回傳這樣的結果：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "input_required",
    "inputRequests": {
      "pick_files": {
        "method": "sampling/createMessage",
        "params": {
          "messages": [
            {
              "role": "user",
              "content": {
                "type": "text",
                "text": "Choose three representative files and return a JSON array."
              }
            }
          ],
          "systemPrompt": "Return only the requested value.",
          "modelPreferences": {
            "costPriority": 0.8,
            "intelligencePriority": 0.2
          },
          "maxTokens": 400
        }
      }
    },
    "requestState": "opaque-integrity-protected-value"
  }
}
```

客戶端確認自己支援 Sampling，套用它的核准與模型政策，取得模型回應。然後用一個不同的 JSON-RPC id 送出新的請求：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "summarize_repo",
    "arguments": {"audience": "developer"},
    "inputResponses": {
      "pick_files": {
        "role": "assistant",
        "content": {
          "type": "text",
          "text": "[\"README.md\", \"server.py\", \"docs/intro.md\"]"
        },
        "model": "host-model",
        "stopReason": "endTurn"
      }
    },
    "requestState": "opaque-integrity-protected-value",
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {"sampling": {}}
    }
  }
}
```

這次重試不是某個協定工作階段的續行。它是一則新的請求：重複原本的方法與參數，只加上當前這一回合的 `inputResponses`，並把 `requestState` 逐位元組原樣回送。

MRTR 只允許用在 `tools/call`、`prompts/get` 與 `resources/read` 上。伺服器不得從其他不相關的方法回傳 `input_required`。

## 多回合狀態

這一課需要兩次模型呼叫：

1. `pick_files` 回傳一個 JSON 陣列。
2. `summary` 回傳最終的散文。

每次重試只帶著那一回合的回應。因此伺服器要把階段與已驗證的中間資料，放進下一個 `requestState`。

把那個值當成由攻擊者控制的東西。只簽一個原始的階段名稱是不夠的。要把狀態綁到：

- 已認證的主體，不是自行宣告的 `clientInfo`；
- 發起的方法；
- 原始參數的摘要值；
- 一個短的到期時間；
- 當前階段與已驗證的中間值。

當不需要機密性時用 HMAC。當客戶端不該讀到狀態內容時用認證加密。簽章錯誤、值已過期、主體改變或參數改變，一律以 `-32602` 拒絕。

客戶端不得解析或修改 `requestState`。它唯一的工作就是在重試時原樣回送那個字串。

## 模型偏好只是提示

`costPriority`、`speedPriority` 與 `intelligencePriority` 是各自獨立的偏好。它們不是機率分布，也不需要加起來等於一。客戶端可以忽略它們，因為模型政策歸客戶端所有。

如果你維護的是舊版 Sampling 流程，就把 `includeContext` 維持在 `"none"`。其他脈絡模式會提高外洩風險，而且它們本身也已被棄用。在請求裡傳入最少量的明確脈絡。

## 安全不變式

對內嵌的 Sampling 請求而言，客戶端就是信任邊界。

- 當政策要求核准時，向使用者顯示伺服器正要求模型做什麼。
- 為 MRTR 回合設上限。否則惡意伺服器就能造出一個燒模型預算的迴圈。
- 在把任何 sampling 回應拿來當檔名、URL 或工具輸入之前，先驗證它。
- 限制每一回合的位元組數與 token 數。
- 拒絕未出現在當前客戶端能力宣告中的輸入請求。
- 別讓模型輸出進入授權決策。
- 記錄發起的方法與輸入請求的鍵，但不要記錄敏感的提示詞內容。

`clientInfo` 與 `serverInfo` 是顯示與診斷用的中繼資料。絕不要把任何一個當成已認證的身分。

```figure
t3-sampling-flip
```

## 動手實作

`code/main.py` 不用任何第三方套件就實作了完整的兩回合流程：

- `server/discover` 回傳 `supportedVersions`、公告工具支援，並回傳快取提示。
- `tools/list` 回傳一份確定性、可快取的 `summarize_repo` 描述，附帶物件型輸入 schema。
- `tools/call` 驗證每請求的中繼資料。
- 第一個結果內嵌用於檔案挑選的 `sampling/createMessage`。
- 第一次重試驗證模型結果，並內嵌第二則請求。
- 受 HMAC 保護的 `requestState` 在彼此獨立的請求之間承載階段。
- 最終結果使用 `resultType: "complete"`。

那個假的宿主模型讓範例保持確定性。接上真實宿主時只要換掉 `fake_host_model`。伺服器端的狀態機應該維持確定性與可測試性。

## 框架應用

從版本庫根目錄：

```bash
cd phases/13-tools-and-protocols/11-mcp-sampling/code
python3 main.py
python3 -m unittest discover tests -v
```

預期的檢查點：

- 發現回傳一個帶 `ttlMs` 與 `cacheScope` 的完整結果。
- 工具發現回傳同一份排序過的描述，附帶 `resultType`、伺服器身分與快取提示。
- 缺少能力與不支援的版本，使用精確的 `-32021` 與 `-32022` 錯誤資料。
- 沒有 id 的通知不會產生任何 JSON-RPC 回應。
- 請求 id 依序是 `[1, 2, 3]`，證明每一個 MRTR 回合都各自獨立。
- 前兩個結果是 `input_required`。
- 最終結果是 `complete`，內含選中的檔案與摘要。
- 在重試時改動原始參數，會讓 request-state 檢查失敗。

## 產出交付

`outputs/skill-sampling-loop-designer.md` 現在是一份遷移規劃工具。它會先判斷是否該移除 Sampling、改採直接整合模型。若確實需要相容性，它會產出 MRTR 回合、狀態綁定、能力關卡、預算、驗證，以及移除計畫。

## 練習

1. 把檔案挑選的回應改成無效的 JSON。確認伺服器回傳 `-32602`，而不是信任模型輸出。
2. 在第一次呼叫與重試之間改動 `audience`。說明為什麼封印過的狀態能阻擋跨請求重用。
3. 加上第三回合，請宿主評論那份摘要。把先前的摘要放進已簽章的狀態裡承載，並把整條流程限制在三回合以內。
4. 把假的宿主回呼換成伺服器自有的模型轉接層，藉此移除 Sampling。列出哪些核准、計費與可觀測性責任因此轉移到伺服器。
5. 用一個超過期限一秒的狀態值，加一項到期測試。

## 關鍵術語

| 術語 | 在 2026-07-28 裡的意義 |
|------|------------------------|
| Sampling | 已棄用的功能，向客戶端的模型索取一次補完 |
| MRTR | 無狀態的重試模式，用於請求過程中需要客戶端輸入的情況 |
| `InputRequiredResult` | 帶有 `resultType: "input_required"` 的結果 |
| `inputRequests` | 由伺服器指定鍵名的映射，內含內嵌的 elicitation、sampling 或 roots 請求 |
| `inputResponses` | 當前回合的客戶端結果，鍵名與 `inputRequests` 相同 |
| `requestState` | 不透明的伺服器狀態，由客戶端原樣回送、由伺服器驗證 |
| `resultType` | 現代 MCP 結果上的必填判別欄位 |
| 直接整合模型 | 對需要模型推論的新伺服器所建議的替代做法 |
| 能力關卡 | 防止送出客戶端未曾公告之內嵌請求的規則 |
| 迴圈預算 | 該操作被允許的最大回合數、token、位元組、時間與花費 |

## 舊版相容

固定在 2025-11-25 的客戶端，仍然可以在一條活的連線上使用較舊的、由伺服器發起的 `sampling/createMessage` 流程。把那個行為只留在特定版本的轉接層裡。不要把有工作階段的那條路徑，當成 2026-07-28 伺服器的架構。

官方 SDK 可以為較舊的對端翻譯現代的 `input_required` 處理器。那層墊片是一道相容邊界，不是可以新增依賴工作階段之邏輯的許可證。

## 延伸閱讀

- [MCP 2026-07-28 Multi Round-Trip Requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- [MCP Sampling deprecation](https://modelcontextprotocol.io/seps/2577-deprecate-roots-sampling-and-logging)
- [MCP 2026-07-28 server discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
