# Roots 與 Elicitation —— 範圍界定與流程中途的使用者輸入

> 使用者一打開不同的專案，寫死的路徑就崩了。使用者交代得不夠清楚時，預先填好的工具參數也崩了。Roots 把伺服器的範圍限縮到一組由使用者掌控的 URI；Elicitation 則在工具呼叫中途暫停，透過表單或 URL 向使用者索取結構化輸入。兩個客戶端原語，修掉兩種常見的 MCP 失敗模式。SEP-1036（URL 模式的 elicitation，2025-11-25）一路到 2026 年上半年都還是實驗性的 —— 依賴它之前先確認 SDK 版本。

**類型：** 實作
**程式語言：** Python (stdlib, roots + elicitation demo)
**先修單元：** 階段 13 · 07（MCP 伺服器）
**時間：** 約 45 分鐘

## 學習目標

- 宣告 `roots` 並回應 `notifications/roots/list_changed`。
- 把伺服器的檔案操作限制在已宣告的 root 集合之內的 URI。
- 用 `elicitation/create` 在工具呼叫中途向使用者索取一次確認或結構化輸入。
- 在表單模式與 URL 模式的 elicitation 之間做選擇（後者是實驗性的；已註明漂移風險）。

## 問題所在

一台筆記 MCP 伺服器在生產環境會撞上的兩個具體失敗。

**路徑假設錯了。** 伺服器是照著 `~/notes` 寫的。某位使用者在另一台機器上，筆記放在 `~/Documents/Notes`，於是工具呼叫要嘛靜默失敗（找不到檔案），要嘛更糟 —— 寫到了錯的地方。

**缺了一個使用者才知道的參數。** 使用者說「刪掉那則舊的 TPS 報告筆記」。模型呼叫 `notes_delete(title: "TPS report")`，但 2023、2024 與 2025 年各有一則符合。工具猜不出來。回一個「有歧義」很惱人；三則全跑則是災難。

Roots 修掉第一個：客戶端在 `initialize` 時宣告伺服器可以碰觸的那組 URI。Elicitation 修掉第二個：伺服器暫停那次工具呼叫，送出 `elicitation/create` 請使用者挑一個。

## 核心概念

### Roots

客戶端在 `initialize` 時宣告一份 root 清單：

```json
{
  "capabilities": {"roots": {"listChanged": true}}
}
```

伺服器接著就能呼叫 `roots/list`：

```json
{"roots": [{"uri": "file:///Users/alice/Documents/Notes", "name": "Notes"}]}
```

伺服器「必須」把 roots 當成邊界：任何在 root 集合之外的檔案讀寫都要拒絕。這件事不是由客戶端強制的（伺服器終究是使用者信任過的程式碼），但合規的伺服器會遵守。

當使用者新增或移除一個 root 時，客戶端送出 `notifications/roots/list_changed`。伺服器重新呼叫 `roots/list` 並更新它的邊界。

### Roots 為什麼是客戶端原語

Roots 由客戶端宣告，是因為它代表的是使用者的同意模型。是使用者告訴 Claude Desktop「讓這台筆記伺服器存取這兩個目錄」。伺服器不能自行擴大那個範圍。

### Elicitation：預設的表單模式

`elicitation/create` 接收一份表單 schema 加上一段自然語言提示：

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Delete 'TPS report'? Multiple notes match; pick one.",
    "requestedSchema": {
      "type": "object",
      "properties": {
        "note_id": {
          "type": "string",
          "enum": ["note-3", "note-7", "note-14"]
        },
        "confirm": {"type": "boolean"}
      },
      "required": ["note_id", "confirm"]
    }
  }
}
```

客戶端渲染一張表單，蒐集使用者的答案，然後回傳：

```json
{
  "action": "accept",
  "content": {"note_id": "note-14", "confirm": true}
}
```

有三種可能的 action：`accept`（使用者填好了）、`decline`（使用者把它關掉了）、`cancel`（使用者中止了整次工具呼叫）。

表單 schema 是扁平的 —— v1 不支援巢狀物件。SDK 通常會拒絕任何比單層更複雜的東西。

### Elicitation：URL 模式（SEP-1036，實驗性）

2025-11-25 新增。伺服器送的不是 schema，而是一個 URL：

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Sign in to GitHub",
    "url": "https://github.com/login/oauth/authorize?client_id=..."
  }
}
```

客戶端在瀏覽器中開啟該 URL、等待完成，並在使用者回來後回傳。這在 OAuth 流程、付款授權與文件簽署等表單不敷使用的場合很有用。

漂移風險提醒：SEP-1036 的回應形狀仍在定型；有些 SDK 回傳回呼 URL，有些回傳一個完成用的 token。在生產環境使用 URL 模式之前，先讀你那套 SDK 的發布說明。

### 什麼時候 elicitation 是對的工具

- 破壞性動作前的使用者確認（destructive hint + elicitation）。
- 消除歧義（從 N 個符合項中挑一個）。
- 首次執行的設定（API 金鑰、目錄、偏好設定）。
- OAuth 式的流程（URL 模式）。

### 什麼時候 elicitation 是錯的

- 用來補齊那些模型本來可以用散文詢問的必填工具參數。請用一般的重新提問，而不是 elicitation 對話框。
- 高頻率的呼叫。Elicitation 會打斷對話；不要在迴圈裡觸發它。
- 任何伺服器事後就能驗證的東西。驗證、回傳錯誤，讓模型用文字去問使用者。

### 人在迴圈中的橋樑

Elicitation 加上 sampling，共同構成了 MCP 的「人在迴圈中」模型。一台伺服器的代理迴圈可以為了使用者輸入（elicitation）或模型推理（sampling）而暫停。階段 13 · 11 談了 sampling；這一課談 elicitation。把兩者放在一起，就能對迴圈中途做完整的控制。

```figure
t3-roots-boundary
```

## 框架應用

`code/main.py` 為那台筆記伺服器擴充了：

- 一個 `roots/list` 回應，伺服器會在收到 root 清單變更通知後重新查詢。
- 一個 `notes_delete` 工具，在多則筆記符合時用 `elicitation/create` 消除歧義。
- 一個 `notes_setup` 工具，用 URL 模式的 elicitation 開啟首次執行的設定頁（模擬的）。
- 一個邊界檢查，拒絕對已宣告 roots 之外的 URI 進行操作。

這個示範跑三種情境：順利路徑（一則符合）、消除歧義（三則符合，觸發 elicitation）、寫到 root 之外（被拒絕）。

## 產出交付

這一課產出 `outputs/skill-elicitation-form-designer.md`。給定一個可能需要使用者確認或消除歧義的工具，這項技能會設計出 elicitation 的表單 schema 與訊息模板。

## 練習

1. 跑一次 `code/main.py`。觸發消除歧義那條路徑；確認模擬的使用者答案有被路由回那個工具。

2. 加上一個新工具 `notes_archive`，每次都要求 elicitation 確認（destructive hint）。檢視一下 UX：這和模型用文字再問一次相比如何？

3. 為首次執行的 OAuth 流程實作 URL 模式的 elicitation。註明漂移風險，並加上一道 SDK 版本的防護。

4. 擴充 `roots/list` 的處理：當通知抵達時，伺服器應該原子性地重讀，並重新掃描那些現在可能已經超出範圍的開啟檔案控制代碼。

5. 讀 GitHub 上 SEP-1036 的議題討論串。找出一個會影響伺服器該如何處理 URL 模式回呼的未決問題。

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| Root | 「同意邊界」 | 客戶端允許伺服器碰觸的 URI |
| `roots/list` | 「伺服器索取範圍」 | 客戶端回傳當前的 root 集合 |
| `notifications/roots/list_changed` | 「使用者改了範圍」 | 客戶端發訊號表示 root 集合已變動 |
| Elicitation | 「呼叫中途問使用者」 | 由伺服器發起、索取結構化使用者輸入的請求 |
| `elicitation/create` | 「那個方法」 | 用於 elicitation 請求的 JSON-RPC 方法 |
| 表單模式 | 「schema 驅動的表單」 | 在客戶端 UI 中渲染成表單的扁平 JSON Schema |
| URL 模式 | 「瀏覽器轉址」 | SEP-1036 實驗性功能；開啟一個 URL 並等待 |
| `accept`／`decline`／`cancel` | 「使用者回應的三種結果」 | 伺服器要處理的三條分支 |
| 消除歧義 | 「挑一個」 | 當工具有 N 個候選項時，elicitation 最常見的使用情境 |
| 扁平表單 | 「只有頂層屬性」 | Elicitation 的 schema 不能巢狀 |

## 延伸閱讀

- [MCP — Client roots spec](https://modelcontextprotocol.io/specification/draft/client/roots) —— roots 的權威參考
- [MCP — Client elicitation spec](https://modelcontextprotocol.io/specification/draft/client/elicitation) —— elicitation 的權威參考
- [Cisco — What's new in MCP elicitation, structured content, OAuth enhancements](https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements) —— 2025-11-25 新增內容的逐步說明
- [MCP — GitHub SEP-1036](https://github.com/modelcontextprotocol/modelcontextprotocol) —— URL 模式 elicitation 的提案（實驗性，有漂移風險）
- [The New Stack — How elicitation brings human-in-the-loop to AI tools](https://thenewstack.io/how-elicitation-in-mcp-brings-human-in-the-loop-to-ai-tools/) —— UX 的逐步說明
