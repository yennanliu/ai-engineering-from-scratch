# 明確的範圍界定與無狀態 Elicitation

> Roots 在 MCP 2026-07-28 裡被棄用，而且它從來就不是安全沙箱。把範圍放進看得見的工具參數或資源 URI，在伺服器上做授權，並在工具真的需要使用者輸入時使用 MRTR。使用者看得到那個決定，模型看得到那個把手，而任何一個伺服器實例都能處理那次重試。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 11（無狀態 MRTR）
**時間：** 約 60 分鐘

## 學習目標

- 用明確的工作區參數、資源 URI 或伺服器組態，取代已棄用的 Roots。
- 把範圍提示跟授權、路徑封閉性與作業系統沙箱區分開來。
- 透過 MRTR 的 `input_required` 結果，送出 form 模式的 `elicitation/create`。
- 在每請求的客戶端能力中公告 elicitation 支援，並拒絕不受支援的模式。
- 把 `accept`、`decline` 與 `cancel` 當成三個不同的結果來驗證。
- 把破壞性操作的確認，綁定到已認證的主體、原始參數、候選集合與到期時間上。

## 兩個看起來很像的問題

一個筆記工具收到這樣的請求：「刪掉那份舊的 TPS 報告。」

伺服器必須回答兩個不同的問題。

1. 這個操作可以碰哪個工作區？
2. 三則相符的筆記裡，使用者指的是哪一則？

第一個是範圍與授權。第二個是互動式的消歧。把兩者混在一起會導致危險的設計，例如把客戶端提供的資料夾，當成「呼叫者有權刪掉裡面所有東西」的證明。

## Roots 是一個待遷移的介面

較早的 MCP 修訂版讓客戶端可以公告 Roots，並在清單改變時通知伺服器。Roots 只是提供資訊的指引。它們不會限制伺服器行程能讀什麼，不會授權呼叫者，也不會建立作業系統沙箱。

MCP 2026-07-28 對新設計棄用了 `roots/list` 與 `notifications/roots/list_changed`。請優先採用以下這些明確的替代方案：

- 當範圍會因呼叫而異時，用 `workspaceUri` 或 `directory` 工具參數。
- 當操作本來就針對某個資源時，用資源 URI。
- 當一次部署對應一個固定工作區時，用伺服器組態。
- 當程式碼必須在技術上就逃不出去時，用行程沙箱或受監禁的檔案系統。

如果既有的 2026-07-28 整合在棄用緩衝期內仍然需要 `roots/list`，伺服器就把它嵌進 MRTR 的 `inputRequests`。它不得送出即時的反向請求。那是一層遷移轉接層；新的處理器應該改為接受明確的範圍。

模型看得見、也能重複那個明確的把手。藏在傳輸工作階段裡的範圍，比較難檢視、難重播、難稽核，也難路由。

### 三層規則

一個明確的 URI 仍然不會自己授權自己。三層都要執行：

1. **授權：** 這個已認證的主體，被允許使用這個工作區嗎？
2. **封閉性：** 正規化後的目標 URI，有沒有留在被授權的工作區邊界內？
3. **沙箱：** 就算伺服器被攻陷了，作業系統能不能還是把它擋住？

那支可執行的伺服器維護一份被授權工作區 URI 的允許清單、把百分比編碼的路徑正規化、做真正的路徑元件邊界檢查，並在刪除之前立刻再檢查一次封閉性。

天真的字串前綴檢查是錯的：

```text
allowed:   file:///work/notes
attacker:  file:///work/notes-evil/secret.md
traversal: file:///work/notes/%2e%2e/private.md
```

這兩條惡意路徑開頭都是一段會誤導人的字串。先正規化，再比對路徑元件。正式環境的檔案系統伺服器，還必須防禦符號連結競態與各平台特有的路徑語意。

## Elicitation 還在，但送法變了

Elicitation 是目前用來在 `tools/call`、`prompts/get` 或 `resources/read` 過程中蒐集使用者輸入的客戶端功能。方法名稱仍然是 `elicitation/create`。改變的是線路流向。

2026-07-28 的伺服器不會送出反向的 JSON-RPC 請求。它回傳一個 `InputRequiredResult`：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "resultType": "input_required",
    "inputRequests": {
      "delete_choice": {
        "method": "elicitation/create",
        "params": {
          "mode": "form",
          "message": "Choose one matching note and confirm deletion.",
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
    },
    "requestState": "integrity-protected-delete-state"
  }
}
```

宿主算繪那張表單。使用者可以接受、明確拒絕，或直接關掉它。客戶端接著用一個新的 id 重試原本的 `tools/call`：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "notes_delete",
    "arguments": {
      "workspaceUri": "file:///Users/alice/Documents/Notes",
      "title": "TPS report"
    },
    "inputResponses": {
      "delete_choice": {
        "action": "accept",
        "content": {"note_id": "note-14", "confirm": true}
      }
    },
    "requestState": "integrity-protected-delete-state",
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "elicitation": {"form": {}}
      }
    }
  }
}
```

這兩次呼叫之間沒有協定工作階段。伺服器驗證回送的狀態、拿回應去對預期的 schema 做驗證、檢查選中的筆記確實在已簽章的候選集合裡、重新授權工作區、重新檢查封閉性，然後才刪除。

## 能力協商是每請求進行的

支援 form 模式 elicitation 的客戶端會宣告：

```json
{
  "io.modelcontextprotocol/clientCapabilities": {
    "elicitation": {"form": {}}
  }
}
```

為了相容性，空的 elicitation 能力 `"elicitation": {}` 仍然等同於「只支援 form」。明確寫出 `"elicitation": {"form": {}}` 同樣代表支援 form 模式。只宣告 URL 的 `"elicitation": {"url": {}}` 則不算。伺服器不得內嵌當前這則請求的能力裡沒有的模式，即使先前某則請求曾經公告過也一樣。

每一則請求同時帶著 `io.modelcontextprotocol/protocolVersion`。版本缺漏或不是字串回傳 `-32602`。字串不受支援回傳 `-32022`，並附上精確的 `supported` 與 `requested` 資料。缺少 elicitation 支援、或只支援 URL，回傳 `-32021`，並把 `data.requiredCapabilities` 設為 `{"elicitation":{"form":{}}}`。

沒有 JSON-RPC `id` 的信封是通知。處理它，但不要發出 JSON-RPC 的成功或錯誤回應。在 Streamable HTTP 上，被接受的通知會收到 `202 Accepted` 且沒有主體。

`clientInfo` 應該為了診斷而附上，但它是自行宣告的，無法用來為授權辨識使用者。

伺服器實作 `server/discover`，回傳 `supportedVersions`、能力、`ttlMs` 與 `cacheScope`，並帶 `resultType: "complete"`。這個現代設計不會公告 Roots。因為它公告了工具，所以也實作必備的 `tools/list`。那個結果會回傳確定性的 `notes_delete` 描述、一份有效的物件型 `inputSchema`、伺服器身分中繼資料，以及公開的快取提示。

## Form 模式

Form 模式使用一份受限的 JSON Schema，是為了做出好用的對話框而設計的。根節點是物件，它的屬性是扁平的原始型別欄位或受支援的列舉陣列。層層巢狀的物件與通用文件 schema，不該出現在確認對話框裡。

在這些情況使用 form 模式：

- 從幾個候選中挑一個；
- 確認一次破壞性操作；
- 蒐集非敏感的偏好設定；
- 蒐集少數幾個必須由使用者、而非模型決定的值。

不要用 form 模式蒐集密碼、API 金鑰、存取權杖或付款憑證。那些機密會經過 MCP 客戶端，可能流進日誌或模型脈絡。

伺服器會再驗證一次回傳的內容。客戶端的表單驗證改善的是 UX，但不會產生信任。

## URL 模式

URL 模式送出一個安全的網頁 URL，用於帶外互動：

```json
{
  "method": "elicitation/create",
  "params": {
    "mode": "url",
    "message": "Connect the report service to continue.",
    "url": "https://mcp.example.com/connect/report-service"
  }
}
```

當敏感資訊必須直接送進由伺服器控制的網頁流程時（例如第三方授權），就用它。客戶端會顯示完整的目的地，並在開啟之前取得同意。它不得預先抓取那個 URL。

`accept` 回應代表使用者同意開啟那個 URL。它並不證明外部流程已經完成。重試時，伺服器檢查自己的狀態，然後要嘛完成、要嘛再回傳一個 `input_required` 結果。

URL elicitation 不能取代 MCP 客戶端與 MCP 伺服器之間的授權。它是給 MCP 伺服器代表使用者去執行的外部互動用的。伺服器必須把瀏覽器裡的那個使用者，綁定到啟動這次 MCP 操作的同一個已認證主體。

## 回應分支

把這些動作當成產品決策，不是彼此的別名：

| 動作 | 意義 | 安全的伺服器行為 |
|--------|---------|----------------------|
| `accept` | 使用者送出了這次互動 | 驗證內容並繼續 |
| `decline` | 使用者明確拒絕 | 回傳一個完整、非錯誤的拒絕結果 |
| `cancel` | 使用者關掉了，或沒能完成 | 安全停下，並允許之後重試 |

絕不要把「缺少內容」解讀成同意。也絕不要把拒絕轉成不斷重問的迴圈。

## 保護破壞性的 MRTR 狀態

候選清單不能只活在提示詞裡，或一個沒簽章的 Base64 值裡。客戶端能控制它送回來的一切。

這一課會簽章一份狀態負載，內含：

- 已認證的主體；
- 發起的方法；
- `workspaceUri` 與 `title` 的摘要值；
- 表單上顯示過的、被允許的筆記 id；
- 操作階段；
- 一個短的到期時間。

在變更之前，伺服器還會檢查即時的筆記紀錄。這能抓到刪除競態，以及表單顯示後目標被移出工作區的情況。

對於一次性的金流或不可逆的動作，光靠 HMAC 並不能防止一個有效的狀態在到期前被重播。要在所有處理器實例共用的重播儲存區裡，把一個 nonce 存下來並且只消耗一次。這一課注入了一個有界限、會依 TTL 修剪的儲存區，並在執行記憶體內刪除的同時持有它那個原子性的宣告。正式環境的資料庫應該把 nonce 宣告與變更耦合在同一個交易，或等價的條件式寫入邊界裡。

先驗證互動，再宣告 nonce。格式錯誤的回應或 `cancel` 不會做任何變更，並讓狀態在到期前仍可重試。明確的 `decline` 是終局的，所以這一課會消耗掉 nonce 但什麼都不刪。

```figure
t3-roots-boundary
```

## 動手實作

`code/main.py` 示範了一個現代的 `notes_delete` 工具：

- `tools/list` 回傳一份確定性、可快取的描述，附帶必填的工作區與標題 schema。
- 範圍是一個明確的 `workspaceUri` 參數。
- 伺服器組態為這一課的主體授權該工作區。
- URI 正規化會拒絕前綴混淆與編碼過的路徑穿越。
- 每一次破壞性刪除都需要 form 模式的 elicitation。
- 那則 elicitation 走在 `resultType: "input_required"` 裡面。
- 已簽章的 `requestState` 綁定了確切的候選清單與原始參數。
- 注入的重播儲存區，會跨伺服器實例拒絕同一個已接受或已拒絕的狀態。
- 重試使用全新的請求 id，並回傳 `resultType: "complete"`。

資料存放在記憶體，好讓協定行為容易檢視。換成資料庫之後，安全規則完全一樣。

## 框架應用

從版本庫根目錄：

```bash
cd phases/13-tools-and-protocols/12-mcp-roots-and-elicitation/code
python3 main.py
python3 -m unittest discover tests -v
```

預期的檢查點：

- 發現公告了工具，但沒有 Roots。
- 工具發現回傳 `notes_delete`，附帶 `resultType`、伺服器身分與快取提示。
- 請求 id `1` 在 `inputRequests.delete_choice` 裡回傳那張表單。
- 請求 id `2` 回送已簽章的狀態，並完成刪除。
- 一條前綴路徑與一條編碼過的穿越路徑，兩者都通不過封閉性檢查。
- 改過的標題無法重用原本的確認狀態。
- 一次拒絕不會改動那則筆記。
- 兩個共用筆記與重播狀態的伺服器物件，無法同時執行同一次確認。
- 空的與明確的 form 宣告都可行，而只支援 URL 的宣告會回傳精確的 `-32021` form 需求。
- 版本不支援的失敗，使用精確的 `-32022` 資料形狀。
- 沒有 id 的通知不會產生任何 JSON-RPC 回應。

## 產出交付

`outputs/skill-elicitation-form-designer.md` 會設計出明確的範圍、授權檢查、MRTR 表單、回應分支與狀態綁定。它拒絕把已棄用的 Roots 當成沙箱，也拒絕用 form 模式蒐集機密。

## 練習

1. 把記憶體重播儲存區換成 SQLite。用同一個交易來宣告 nonce 並刪除筆記，然後證明兩個行程無法同時提交。
2. 加上 `url` 能力協商與一條帶外設定流程。把第三方憑證留在 `inputResponses` 之外。
3. 把記憶體筆記映射換成一個暫時的 SQLite 資料庫。在變更交易內部重新檢查授權與封閉性。
4. 為真實檔案系統實作加上符號連結政策。說明為什麼光靠 URI 的字面封閉性，擋不住符號連結逃逸。
5. 設計一個 2025-11-25 轉接層，把現代 MRTR 處理器的輸出，映射成舊版由伺服器發起的 elicitation。讓它跟現行處理器保持隔離。

## 關鍵術語

| 術語 | 在 2026-07-28 裡的意義 |
|------|------------------------|
| Roots | 已棄用的資訊性工作區提示，不是授權，也不是沙箱 |
| 明確範圍 | 出現在請求參數裡、看得見的工作區、目錄或資源把手 |
| 封閉性（Containment） | 正規化後的路徑元件檢查，讓目標留在邊界之內 |
| Elicitation | 在 MCP 操作過程中取得使用者輸入的客戶端功能 |
| Form 模式 | 使用受限扁平 schema 的帶內結構化使用者輸入 |
| URL 模式 | 用於敏感或外部工作流程的帶外互動 |
| MRTR | 無狀態的 input-required 結果，之後接一次全新的重試 |
| `requestState` | 由客戶端原樣回送、由伺服器做完整性檢查的不透明狀態 |
| Decline | 使用者明確拒絕 |
| Cancel | 關閉或未完成的互動，未取得核准 |

## 舊版相容

對於固定在 2025-11-25 的對端，`roots/list`、`notifications/roots/list_changed`，以及即時由伺服器發起的 `elicitation/create` 可能仍然存在。把那層轉接層標記為舊版。不要讓舊版的 Root 清單繞過伺服器授權，也不要把協定工作階段的假設帶進現代處理器。

## 延伸閱讀

- [MCP 2026-07-28 Elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- [MCP 2026-07-28 Multi Round-Trip Requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 2026-07-28 Roots deprecation](https://modelcontextprotocol.io/specification/2026-07-28/client/roots)
- [MCP 2026-07-28 server discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
