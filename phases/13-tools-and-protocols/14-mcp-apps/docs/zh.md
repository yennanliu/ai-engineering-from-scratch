# MCP Apps —— 透過 `ui://` 的互動式 UI 資源

> 純文字的工具輸出，限住了代理能展示的東西。MCP Apps（SEP-1724，2026 年 1 月 26 日正式發布）讓工具能回傳沙箱化的互動式 HTML，並在 Claude Desktop、ChatGPT、Cursor、Goose 與 VS Code 中就地渲染。儀表板、表單、地圖、3D 場景，全都靠這一個擴充。這一課會走過 `ui://` 資源 scheme、`text/html;profile=mcp-app` 這個 MIME、iframe 沙箱的 postMessage 協定，以及讓伺服器渲染 HTML 所帶來的那片安全表面。

**類型：** 實作
**程式語言：** Python (stdlib, UI resource emitter), HTML (sample app)
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 10（資源）
**時間：** 約 75 分鐘

## 學習目標

- 從一次工具呼叫中回傳一個 `ui://` 資源，並設好正確的 MIME 與中繼資料。
- 用 `_meta.ui.resourceUri`、`_meta.ui.csp` 與 `_meta.ui.permissions` 宣告一個工具所關聯的 UI。
- 實作供 UI 對宿主溝通用的 iframe 沙箱 postMessage JSON-RPC。
- 套用 CSP 與 permissions-policy 的預設值，以防禦源自 UI 的攻擊。

## 問題所在

一個 2025 年代的 `visualize_timeline` 工具，能回傳「以下是依時間排序的 14 則筆記：……」。那是一個段落。但使用者真正想要的是那條互動式時間軸。在 MCP Apps 之前，選項只有：客戶端專屬的 widget API（Claude 的 artifacts、OpenAI 的 Custom GPT HTML），或者完全沒有 UI。

MCP Apps（SEP-1724，2026 年 1 月 26 日出貨）把這份契約標準化了。工具結果中包含一個 `resource`，其 URI 是 `ui://...`，MIME 是 `text/html;profile=mcp-app`。宿主把它渲染在一個沙箱化的 iframe 中，帶著受限的 CSP，且除非明確授權否則沒有網路存取。iframe 內的 UI 則透過一套小巧的 postMessage JSON-RPC 方言，向宿主發送訊息。

每個相容的客戶端（Claude Desktop、ChatGPT、Goose、VS Code）都以同樣的方式渲染同一份 `ui://` 資源。一台伺服器、一份 HTML 套件，通用的 UI。

## 核心概念

### `ui://` 資源 scheme

工具回傳：

```json
{
  "content": [
    {"type": "text", "text": "Here is your notes timeline:"},
    {"type": "ui_resource", "uri": "ui://notes/timeline"}
  ],
  "_meta": {
    "ui": {
      "resourceUri": "ui://notes/timeline",
      "csp": {
        "defaultSrc": "'self'",
        "scriptSrc": "'self' 'unsafe-inline'",
        "connectSrc": "'self'"
      },
      "permissions": []
    }
  }
}
```

宿主接著對 `ui://notes/timeline` 這個 URI 呼叫 `resources/read`，拿回：

```json
{
  "contents": [{
    "uri": "ui://notes/timeline",
    "mimeType": "text/html;profile=mcp-app",
    "text": "<!doctype html>..."
  }]
}
```

### Iframe 沙箱

宿主把那份 HTML 渲染在一個沙箱化的 `<iframe>` 中，並帶著：

- `sandbox="allow-scripts allow-same-origin"`（或依伺服器宣告更嚴格）
- 透過回應標頭套用伺服器宣告的 CSP。
- 沒有 cookie，也拿不到宿主來源的 localStorage。
- 網路存取限縮在 CSP 的 `connectSrc` 之內。

### postMessage 協定

iframe 透過 `window.postMessage` 與宿主溝通。用的是一套小巧的 JSON-RPC 2.0 方言：

務必把 `targetOrigin` 釘死在對端的確切來源上，而在接收端，處理任何酬載之前都要先拿 `event.origin` 對白名單驗證。這條通道的任一端都絕不要用 `"*"` —— 它的主體承載的是工具呼叫與資源讀取。

```js
// iframe to host  (pin to host origin)
window.parent.postMessage({
  jsonrpc: "2.0",
  id: 1,
  method: "host.callTool",
  params: { name: "notes_update", arguments: { id: "note-14", title: "..." } }
}, "https://host.example.com");

// host to iframe  (pin to iframe origin)
iframe.contentWindow.postMessage({
  jsonrpc: "2.0",
  id: 1,
  result: { content: [...] }
}, "https://iframe.example.com");

// receiver on both sides
window.addEventListener("message", (event) => {
  if (event.origin !== "https://expected-peer.example.com") return;
  // safe to process event.data
});
```

UI 可以呼叫的宿主端方法有：

- `host.callTool(name, arguments)` —— 呼叫一個伺服器工具。
- `host.readResource(uri)` —— 讀取一項 MCP 資源。
- `host.getPrompt(name, arguments)` —— 取得一份提示詞模板。
- `host.close()` —— 關掉這個 UI。

每一次呼叫仍然走 MCP 協定，並繼承伺服器的權限。

### 權限

`_meta.ui.permissions` 這份清單用來請求額外的能力：

- `camera` —— 存取使用者的相機（用於掃描文件類的 UI）。
- `microphone` —— 語音輸入。
- `geolocation` —— 位置。
- `network:*` —— 比單靠 `connectSrc` 所允許的更寬的網路存取。

每一項權限，都是使用者在 UI 渲染之前會看到的一次詢問。

### 安全風險

iframe 裡的 HTML 終究還是 HTML。這帶來新的攻擊表面：

- **透過 UI 的提示詞注入。** 惡意伺服器的 UI 可以顯示看起來像系統訊息的文字來誆騙使用者。宿主的渲染應該在視覺上把伺服器 UI 與宿主 UI 區分開來。
- **透過 `connectSrc` 外洩。** 如果 CSP 允許 `connect-src: *`，那個 UI 就能把資料送到任何地方。預設值應該從嚴。
- **點擊劫持。** UI 疊在宿主的介面框架上。宿主必須阻止 z-index 操弄並強制不透明度規則。
- **搶走焦點。** UI 奪走鍵盤焦點，攔截下一則訊息。宿主必須攔下這種行為。

階段 13 · 15 會把這些當作 MCP 安全的一部分深入談；這一課只是引介。

### `ui/initialize` 握手

iframe 載入後，會透過 postMessage 送出 `ui/initialize`：

```json
{"jsonrpc": "2.0", "id": 0, "method": "ui/initialize",
 "params": {"theme": "dark", "locale": "en-US", "sessionId": "..."}}
```

宿主以能力集與一個工作階段 token 回應。UI 在之後每一次宿主呼叫上都要用上那個 token。

### AppRenderer／AppFrame 這兩個 SDK 原語

ext-apps SDK 暴露了兩個便利原語：

- `AppRenderer`（伺服器端）—— 包住一個 React／Vue／Solid 元件，並吐出一個帶正確 MIME 與中繼資料的 `ui://` 資源。
- `AppFrame`（客戶端）—— 接收該資源、掛載 iframe，並居中處理 postMessage。

你可以用它們，也可以自己手工寫 HTML 與 JSON-RPC。

### 生態系狀態

MCP Apps 於 2026 年 1 月 26 日出貨。截至 2026 年 4 月的客戶端支援情況：

- **Claude Desktop。** 自 2026 年 1 月起完整支援。
- **ChatGPT。** 透過 Apps SDK 完整支援（底層是同一套 MCP Apps 協定）。
- **Cursor。** Beta；在設定中啟用。
- **VS Code。** 僅 Insider 版本。
- **Goose。** 完整支援。
- **Zed、Windsurf。** 已列入路線圖。

生產環境中的伺服器有：儀表板、地圖視覺化、資料表格、圖表產生器、沙箱 IDE 預覽。

```figure
t3-ui-sandbox
```

## 框架應用

`code/main.py` 為那台筆記伺服器擴充了一個 `visualize_timeline` 工具，它會回傳一個 `ui://notes/timeline` 資源；另外還有一個針對該 URI 的 `resources/read` 處理器，會回傳一份小巧但完整、帶 SVG 時間軸的 HTML 套件。那份 HTML 是用 stdlib 套模板產生的 —— 沒有建置系統。postMessage 則以 JS 註解的形式勾勒出來，因為 stdlib 驅動不了瀏覽器。

要看的地方有：

- 工具回應上的 `_meta.ui` 承載了 resourceUri、CSP 與 permissions。
- 那份 HTML 不需網路存取就能渲染；所有資料都內嵌其中。
- JS 透過 `window.parent.postMessage` 呼叫 `host.callTool`（在這個 stdlib 示範中有文件但不會實際運作）。

## 產出交付

這一課產出 `outputs/skill-mcp-apps-spec.md`。給定一個會因互動式 UI 而受惠的工具，這項技能會產出完整的 MCP Apps 契約：`ui://` URI、CSP、權限、postMessage 進入點，以及一份安全檢查清單。

## 練習

1. 跑一次 `code/main.py`，檢視吐出來的 HTML。直接在瀏覽器中開啟那份 HTML，確認 SVG 有渲染出來。接著勾勒出 UI 用來呼叫 `host.callTool("notes_update", ...)` 的那份 postMessage 契約。

2. 把 CSP 收緊：拿掉 `'unsafe-inline'`，改用以 nonce 為基礎的 script 政策。HTML 產生的程式碼要改什麼？

3. 加上第二個 UI 資源 `ui://notes/editor`，帶一張就地編輯筆記的表單。使用者送出時，iframe 呼叫 `host.callTool("notes_update", ...)`。

4. 稽核這個 UI 的攻擊表面。惡意伺服器可以在哪裡注入內容？iframe 沙箱防得住什麼，又防不住什麼？

5. 讀 SEP-1724 規格，找出一項 MCP Apps SDK 中、而這份玩具實作沒有用到的能力。（提示：元件層級的狀態同步。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| MCP Apps | 「互動式 UI 資源」 | 2026-01-26 出貨的 SEP-1724 擴充 |
| `ui://` | 「App 的 URI scheme」 | 給 UI 套件用的資源 scheme |
| `text/html;profile=mcp-app` | 「那個 MIME」 | MCP App HTML 的 content-type |
| Iframe 沙箱 | 「渲染容器」 | 瀏覽器對該 UI 施加的沙箱化，配上 CSP 與權限 |
| postMessage JSON-RPC | 「UI 對宿主的線路」 | 跑在 postMessage 上、供宿主呼叫用的小型 JSON-RPC 方言 |
| `_meta.ui` | 「工具與 UI 的繫結」 | 把工具結果連到某個 UI 資源的中繼資料 |
| CSP | 「Content-Security-Policy」 | 宣告 script、網路與樣式的允許來源 |
| AppRenderer | 「伺服器端 SDK 原語」 | 把一個框架元件轉換成 `ui://` 資源 |
| AppFrame | 「客戶端 SDK 原語」 | 掛載 iframe 並居中處理 postMessage 的輔助工具 |
| `ui/initialize` | 「握手」 | UI 送給宿主的第一則 postMessage |

## 延伸閱讀

- [MCP ext-apps — GitHub](https://github.com/modelcontextprotocol/ext-apps) —— 參考實作與 SDK
- [MCP Apps specification 2026-01-26](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx) —— 正式的規格文件
- [MCP — Apps extension overview](https://modelcontextprotocol.io/extensions/apps/overview) —— 高階文件
- [MCP blog — MCP Apps launch](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) —— 2026 年 1 月的發布文
- [MCP Apps API reference](https://apps.extensions.modelcontextprotocol.io/api/) —— JSDoc 風格的 SDK 參考
