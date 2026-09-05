# 打造 MCP 伺服器：無狀態的 Python 與 TypeScript

> 現代 MCP 伺服器不記得任何握手。它在每一則請求上驗證中繼資料，跑一個處理器，回傳一個帶型別的結果。

**類型：** 實作
**程式語言：** Python、TypeScript
**先修單元：** 階段 13，單元 06
**時間：** 約 85 分鐘

## 學習目標

- 為 MCP `2026-07-28` 實作必備的 `server/discover`。
- 在每一則請求上驗證協定版本與客戶端能力。
- 以確定性的清單排序暴露工具、資源與提示詞。
- 在正確的結果上回傳 `resultType`、伺服器身分與快取提示。
- 在 Python 與 TypeScript 上，透過換行分隔的 stdio 提供同一份無狀態契約。

## 問題所在

一台在收到第一則訊息後就把客戶端能力存起來的伺服器，寫起來容易，運維起來麻煩。同一個行程可能先後服務不同客戶端。一則遠端請求可能落在另一個 worker 上。一份過期的能力宣告，可能讓行為跨越授權邊界外洩。

MCP `2026-07-28` 讓每一則請求都自我描述，藉此解決這個問題的協定部分。你的應用仍然可以保有持久的筆記、工作或明確的狀態把手。它不能保有的，是那種會改變後續請求如何被解碼的隱藏協定狀態。

這一課會把一台筆記伺服器寫兩次。Python 與 TypeScript 版本的協定核心都只用各自的標準函式庫。兩者暴露相同的方法，也執行相同的線路契約。

## 核心概念

### 現代分派迴圈

```text
read one JSON-RPC line
parse the envelope
if it is a notification, do not respond
validate params._meta for this request
route by method
wrap success with resultType and serverInfo
write one JSON-RPC response line
forget request-scoped metadata
```

三條 stdio 規則依然重要：

- 只把 JSON-RPC 訊息寫到 stdout。診斷訊息送到 stderr。
- 用換行分隔訊息，並在每則回應後 flush。
- stdin 收到 EOF 時要立刻結束。

行程的生命期是傳輸的生命期。它不是現代 MCP 的工作階段。

### 請求驗證

每一則請求都必須有：

```json
{
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
      "io.modelcontextprotocol/clientInfo": {
        "name": "notes-client",
        "version": "1.0.0"
      }
    }
  }
}
```

前兩個欄位是必填。`clientInfo` 是建議填寫。若身分存在就驗證它的形狀，但不要把它當成認證。

如果版本不受支援，回傳錯誤碼 `-32022`，附上 `requested` 與 `supported`。缺少請求中繼資料屬於 invalid params，錯誤碼 `-32602`。絕不要用前一次呼叫的值去補上缺漏的欄位。

### 必備的發現

現代伺服器必須實作 `server/discover`。一份完整的發現結果會包含受支援的現代版本、能力、選用的使用說明、快取提示，以及結果 `_meta` 裡的伺服器身分：

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "tools": {"listChanged": false},
    "resources": {"listChanged": false, "subscribe": false},
    "prompts": {"listChanged": false}
  },
  "ttlMs": 3600000,
  "cacheScope": "public",
  "_meta": {
    "io.modelcontextprotocol/serverInfo": {
      "name": "notes-server",
      "version": "2.0.0"
    }
  }
}
```

發現並不會解鎖伺服器。客戶端可以不呼叫發現就直接呼叫 `tools/list`，因為 `tools/list` 本身已經帶著同一份請求中繼資料。

### 工具

`tools/list` 回傳一份確定性的工具描述清單。穩定的排序改善了回應快取，也讓模型脈絡保持穩定。這個結果同樣需要 `ttlMs` 與 `cacheScope`。

`tools/call` 回傳內容區塊與 `isError`。當協定信封或方法參數無效時，用 JSON-RPC 錯誤。當一次有效的工具調用真的跑起來、但工具本身失敗時，用 `isError: true`。

工具註記仍然只是提示，不是強制：

- `readOnlyHint`
- `destructiveHint`
- `idempotentHint`
- `openWorldHint`

宿主應該拿它們來做確認與呈現。伺服器仍然必須執行真正的授權。

### 資源

`resources/list` 回傳穩定的 URI 描述。`resources/read` 回傳帶型別的內容。在 `2026-07-28` 裡兩者都可快取，所以兩者都要帶 `ttlMs` 與 `cacheScope`。

使用者專屬的筆記資料請用 `cacheScope: "private"`。共用快取不得跨授權脈絡重用一則 private 回應。

現代的變更推送不使用 `resources/subscribe`。客戶端開啟 `subscriptions/listen`，並請求 `resourceSubscriptions` 或清單變更類別。單元 10 會建構那條流程。

### 提示詞

`prompts/list` 可快取且具確定性。`prompts/get` 會用參數算繪一個具名提示詞。算繪出來的提示詞結果是 complete，但它不屬於那些需要快取提示的可快取清單或讀取結果。

### 每一個成功的結果都帶型別

範例對每一次成功都套用同一個包裝器：

```python
def complete(payload):
    return {
        "resultType": "complete",
        **payload,
        "_meta": {SERVER_INFO_KEY: SERVER_INFO},
    }
```

清單、讀取與發現的處理器會再加上 `ttlMs` 與 `cacheScope`。把這個包裝器集中管理，可以避免某個處理器悄悄漏掉現代結果欄位。

### 沒有伺服器發起的請求

現代伺服器可以送出與某則客戶端請求相關的通知，或送出在客戶端開啟的 `subscriptions/listen` 串流上的通知。它不得送出自己的 JSON-RPC 請求。

當處理器需要 sampling、elicitation 或 roots 的輸入時，它回傳一個 `input_required` 結果。客戶端滿足內嵌的輸入請求，再用一個新的請求 id 重試原本的方法。單元 11 會講那個 Multi Round-Trip Request 模式。

### 明確的舊版相容

跨時代的伺服器也可以在一條明確分離的舊版分支上實作 `2025-11-25` 的握手。當必填的現代 `_meta` 欄位存在時它選擇現代行為，收到 `initialize` 時則選擇舊版行為。

不要把一則 `2026-07-28` 的請求送進舊版握手路徑。也不要把現代的 `resultType` 欄位蓋到舊版初始化結果上。這一課的程式碼刻意只支援現代版，好讓它的不變式保持可見。

```figure
t3-dispatch-loop
```

## 框架應用

執行 Python 伺服器的有限次示範與測試：

```bash
cd code
python3 main.py --demo
python3 -m unittest discover tests -v
```

用 TypeScript 執行器跑 TypeScript 移植版：

```bash
npx tsx main.ts --demo
```

這份示範會送出 `server/discover`、列出每一種原語、調用工具，並展示一則不支援版本的錯誤。每一則現代請求都重複帶上中繼資料。每一次成功都包含伺服器身分。

## 產出交付

這一課交付 `outputs/skill-mcp-server-scaffolder.md`。它會產出一份現代伺服器規劃，內含發現契約、每請求驗證、確定性的可快取清單，以及一個選用的、被隔離的舊版轉接層。

## 練習

1. 從某一則請求裡拿掉能力，證明伺服器沒有沿用前一則請求的宣告。
2. 把 `TOOLS`、`PROMPTS` 與筆記的插入順序反轉。確認所有清單結果仍然穩定。
3. 加一個具破壞性的 `notes_delete` 工具，並在執行器內部要求一道授權檢查。`destructiveHint` 只當成 UX 提示。
4. 加上 `resources/templates/list`，附帶 `ttlMs`、`cacheScope` 與確定性排序。
5. 為 `2025-11-25` 另外做一個舊版轉接層。加上測試，證明現代請求永遠不會進到它裡面。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| 無狀態伺服器 | 只依當則請求自身的中繼資料處理它，不保有協定工作階段記憶 |
| `server/discover` | 必備的現代方法，公告版本與能力 |
| 完整結果 | 帶有 `resultType: "complete"` 的成功現代結果 |
| 可快取結果 | 帶有 `ttlMs` 與 `cacheScope` 的發現、清單或資源讀取結果 |
| 確定性清單 | 同一份邏輯登錄表產生同樣的項目順序 |
| 伺服器身分 | 建議放在結果 `_meta` 裡的 `io.modelcontextprotocol/serverInfo` |
| 工具錯誤 | 有效的工具呼叫，回傳帶 `isError: true` 的內容 |
| 協定錯誤 | 無效的 JSON-RPC 或 MCP 請求，透過 `error` 回傳 |

## 延伸閱讀

- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/)
- [MCP Server Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- [MCP Prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
- [MCP stdio Transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
