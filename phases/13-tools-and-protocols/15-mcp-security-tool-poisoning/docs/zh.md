# MCP 安全：被下毒的中繼資料、路由與 MRTR 狀態

> 無狀態不等於不需要信任。它的意思是：每一則請求都攤出伺服器與閘道獨立驗證這次呼叫所需的證據。

**類型：** 學習
**程式語言：** Python
**先修單元：** 階段 13 · 07（MCP 伺服器）、階段 13 · 08（MCP 客戶端）
**時間：** 約 60 分鐘

## 學習目標

- 把工具描述、註記、客戶端資訊與伺服器資訊，全部視為不可信的資料。
- 偵測中繼資料下毒、描述變更，以及跨伺服器的名稱衝突。
- 驗證 2026-07-28 的請求中繼資料與 Streamable HTTP 路由標頭。
- 保護 MRTR 的 `requestState` 不被竄改，並把確認綁到確切的參數上。
- 把授權與速率限制套用在主體上，而不是那個已被移除的協定工作階段。

## 問題所在

模型讀工具描述來決定要呼叫什麼。路由器讀工具名稱來決定要把請求送去哪裡。使用者讀標籤來決定要核准什麼。一份惡意的描述可以同時針對這三者。

MCP 官方的安全指引講得很直接：除非描述與註記來自受信任的伺服器，否則都應當視為不可信。而且就算來自受信任的伺服器，部署上的信任也可能改變。一次伺服器更新、一個被攻陷的套件、一個登錄檔的失誤，或一次閘道合併，都可能改掉模型看到的東西。

現行協定也改變了安全邊界。在 2026-07-28 裡沒有核心握手，也沒有傳輸工作階段。一份把核准、速率限制或稽核歷史「只」以 `Mcp-Session-Id` 為鍵的安全設計，不是一份現行的設計。

## 核心概念

### 值得檢查的七個攻擊面

用一份具體清單，取代「小心一點」這種含糊的指示。

1. **中繼資料下毒。** 描述裡含有與宣告的工具行為無關的指令。
2. **描述抽地毯（rug pull）。** 先前已核准的名稱、描述、schema 或註記被改掉了。
3. **跨伺服器遮蔽。** 兩個後端暴露同一個未限定的工具名稱，而路由悄悄選了其中一個。
4. **標頭與主體混淆。** `Mcp-Method` 或 `Mcp-Name` 跟 JSON-RPC 請求不一致。
5. **能力提權。** 對端宣稱擁有某個擴充或客戶端功能，而伺服器把那份宣告誤當成授權。
6. **MRTR 狀態竄改。** 客戶端改動 `requestState`、回答了不同的問題，或帶著不同的參數重用確認。
7. **供應鏈身分混淆。** 把一個眼熟的顯示名稱，當成發布者或伺服器身分的證明。

這些面向會互相重疊。雜湊固定有助於偵測描述變更，但不能證明第一份描述本來就是安全的。靜態掃描能抓到明顯的詞句，抓不到隱晦的指令。命名空間能防止一類撞名，防不了一台惡意的、有命名空間的伺服器。把這些控制疊起來用。

### 現行的請求信封是證據，不是身分

每一則 2026-07-28 的請求都包含：

```json
{
  "_meta": {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {
      "elicitation": {"form": {}}
    },
    "io.modelcontextprotocol/clientInfo": {
      "name": "security-lab",
      "version": "1.0.0"
    }
  }
}
```

在每一則請求上驗證版本與能力形狀。用能力來挑選相容的回應形狀。不要把 `clientInfo` 當成已認證的主體。它是自行宣告的。

同樣的警告也適用於結果中繼資料裡的 `io.modelcontextprotocol/serverInfo`。它對日誌與除錯很有用。它不是憑證、不是登錄檔證明，也不是授權決策。

### 先驗路由，再談政策

對 `tools/call` 而言，Streamable HTTP 會帶上：

```text
MCP-Protocol-Version: 2026-07-28
Mcp-Method: tools/call
Mcp-Name: notes.export
```

標頭裡的方法必須等於主體裡的方法。標頭裡的名稱必須等於 `params.name`。在挑選後端、套用 RBAC 或消耗速率限制配額之前，就先用 `-32020` 拒絕不一致的情況。

這個順序關掉了一個常見的歧義：某個元件對主體做授權，另一個元件卻依標頭做路由。

線路驗證遵循一個確切的順序。先驗證 JSON-RPC 與中繼資料的型別，再把標頭值跟主體比對，然後才檢查那個已取得一致的版本是否受支援。標頭不一致回傳 HTTP 400 與 `-32020`。如果標頭與主體對一個不受支援的版本取得一致，回傳 HTTP 400 與 `-32022`，`data` 精確為 `{"supported":["2026-07-28"],"requested":"<actual>"}`。未知的方法回傳 HTTP 404 與 `-32601`。

當契約需要結構化的復原資訊時，每個錯誤物件都可以帶上選用的 `data`。通知沒有 `id`，所以它永遠不會收到 JSON-RPC 的成功或錯誤回應。被接受的 HTTP 通知回傳 202 與空主體。

### 把整份描述固定住

只固定描述的雜湊，會漏掉 schema 與註記的變更。把使用者核准過的那些描述欄位正規化並雜湊：

```python
normalized = json.dumps(tool, sort_keys=True, separators=(",", ":"))
digest = hashlib.sha256(normalized.encode()).hexdigest()
```

把摘要值存在像 `notes.export` 這種限定過的鍵底下，在這個玩具範例之外還要一併存上發布者證據與核准時間。

每一次重新整理時：

- 未知的鍵：隔離待審。
- 同一個鍵但摘要值不同：當成抽地毯隔離，直到重新核准。
- 重複的未限定名稱：要求確定性的命名空間。
- 掃描命中：封鎖，並審查完整的描述。

雜湊相等證明的是穩定性，不是安全性。一份被下毒的描述，就算固定得完美無缺，它還是被下毒的。

### 靜態掃描是一條絆線

簡單的樣式可以標記角色標籤、指令覆寫、隱匿行為、機密存取，以及被混淆的網路目的地。它們夠便宜，可以放在安裝時與 CI 裡跑。

它們不是語意上的證明。一份安全的描述，可能在一段正當的警告文字裡含有被標記的詞句。一份惡意的描述，也可能避開每一個詞句。把掃描結果當成審查證據，不是自動的清白分數。

### 合併之前先加命名空間

假設兩台伺服器都暴露 `search`。絕不要讓發現的順序來決定誰贏。

```text
notes.search
issues.search
```

限定過的名稱是對外的閘道名稱。後端映射另外記錄。穩定的名稱讓核准、稽核、雜湊固定與 `Mcp-Name` 路由，指的都是同一個物件。

### 能力是相容性宣告

每請求的 `clientCapabilities` 告訴伺服器：客戶端能處理哪些協定功能。它不授予客戶端對工具、資料或動作的存取權。

授權仍然來自已認證的主體與資源政策。順序是：

1. 認證傳輸憑證。
2. 驗證版本、標頭與請求形狀。
3. 檢查能力相容性。
4. 對主體、工具、資源與參數做授權。
5. 執行，或請求使用者輸入。

### 保護無狀態的 MRTR 確認

重大的工具可能需要使用者確認。現行 MCP 使用 Multi Round-Trip Requests，而不是伺服器對客戶端的回呼。

第一個回應：

```json
{
  "resultType": "input_required",
  "inputRequests": {
    "confirm": {
      "method": "elicitation/create",
      "params": {
        "mode": "form",
        "message": "Export notes to archive?",
        "requestedSchema": {
          "type": "object",
          "properties": {
            "confirm": {"type": "boolean"}
          },
          "required": ["confirm"]
        }
      }
    }
  },
  "requestState": "opaque-integrity-protected-value"
}
```

客戶端取得輸入之後，用一個新的 JSON-RPC id 重試原本的方法：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "notes.export",
    "arguments": {"query": "private", "destination": "archive"},
    "requestState": "opaque-integrity-protected-value",
    "inputResponses": {
      "confirm": {
        "action": "accept",
        "content": {"confirm": true}
      }
    },
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {
        "elicitation": {"form": {}}
      }
    }
  }
}
```

`inputRequests` 的每一個值，都是一則帶著 `method` 與 `params` 的完整內嵌請求。它的鍵必須跟 `inputResponses` 裡對應的項目一致。form elicitation 使用根節點為物件的 `requestedSchema`，而且客戶端必須在伺服器提出請求之前，就已經宣告過 form elicitation 能力。

現行能力有兩種有效的 form 宣告。`{"elicitation":{}}` 隱含支援 form elicitation，`{"elicitation":{"form":{}}}` 則是明確寫出來。像 `{"elicitation":{"url":{}}}` 這種只宣告 URL 的，不支援 form 請求。伺服器回傳 HTTP 400 與 `-32021`，`data.requiredCapabilities` 等於 `{"elicitation":{"form":{}}}`。

把 `requestState` 當成敵意輸入。簽章或加密它、驗證它，並在重播有影響時，把它綁到方法、工具、確切參數、用途、到期時間、主體與一個一次性 nonce 上。這一課的程式碼用 HMAC 與精確參數比對，讓這道邊界看得見。

nonce 帳本不能只活在單一個閘道物件裡。那份可執行的模型注入了一個有界限、依 TTL 修剪、可由多個閘道實例共用的重播儲存區。它那個原子性的宣告就是執行邊界：只有經過驗證的接受，或明確的終局拒絕，才會消耗狀態。格式錯誤的回應或 `cancel` 什麼都不執行，並在到期前維持可重試。正式環境的機群，需要在共用的持久儲存區裡做同樣的條件式宣告。

不要把隱藏的確認脈絡存在協定工作階段裡。任何一個伺服器實例都應該有辦法驗證那次重試。

### 高風險呼叫的「二選一」規則

沿三個軸線把一次呼叫分類：

- 它消耗不可信的輸入。
- 它可以存取敏感資料。
- 它造成重大的外部動作。

單一個自動步驟不該同時集齊這三項。把它拆開、降低權限，或透過 MRTR 請求明確的使用者輸入。這是一條設計啟發法，不是協定能力。

### 在執行之前先縮小權限

光靠無狀態並不等於安全。它移除的是隱藏的協定歷史，但一則自成一體的請求，仍然可能要求一個權力過大的處理器去外洩資料或做出不可逆的改動。安全來自在每一道邊界上縮小權限：

1. **帶型別的動詞。** 暴露一個有界限的操作，例如 `archive_note`，而不是一個能表達無關權力的通用 `run` 或 `request` 工具。
2. **已驗證的參數。** 可行時使用封閉 schema、拒絕未知欄位、把識別碼正規化一次、限制大小，並在政策評估之前驗證目的地、租戶與資源擁有權。
3. **當前授權。** 把已認證的主體，綁到確切的動詞、資源、環境與正規化後的參數上。工具註記與客戶端能力不授予這份權限。
4. **綁定動作的核准。** 對於重大的呼叫，把核准綁到「帶型別動詞 + 正規化參數」的摘要值上，再加上主體、到期時間與一次性政策。任何欄位改了，就需要一次新的決定。
5. **一等公民的拒絕。** 把政策否決、核准過期、使用者拒絕與不安全的目的地，都建模成不產生任何副作用的一般結果。不要把拒絕翻譯成一個較弱的備援工具。
6. **經過遮蔽的稽核證據。** 記下是誰要求的、用了哪個被准入的描述與政策版本、被授權的正規化目標是什麼、決策為何允許或拒絕，以及執行是否已經開始。存摘要值或遮蔽過的值，不要存機密。

每一步都在收窄下一個元件能做的事。最終的處理器應該收到一個已經驗證好的領域命令，而不是原始模型文字加上一大把憑證。在 MRTR 重試、任務更新，或閘道轉發的呼叫上，把整條鏈重跑一遍。先前的核准不會把後續請求變成受信任的工作階段流量。

### 現行與舊版的互動路徑

對新的 2026-07-28 實作而言，Roots、Sampling 與 Logging 都已棄用。閘道可以保留較舊的請求通道程式碼，但只能當成一條有版本關卡的相容路徑。

不要圍繞一個「每工作階段」的 sampling 限流器來建構新的防禦。把配額套用在已認證的主體、簽發者、資源、工具與時間窗上。至於現行的互動式工作，請檢視 MRTR 的輸入請求與回應。

### 無狀態傳輸檢查

- 在單一個 POST 端點接受現代 MCP 訊息。
- 對現代的 GET 與 DELETE 回傳 405。
- 不鑄造、也不依賴 `Mcp-Session-Id`。
- 不要把舊版的工作階段與重播標頭當成權限輸入。
- 對那次 POST 回傳 JSON，或請求範圍的 SSE。
- 只把 `subscriptions/listen` 用在選擇性訂閱、長時間存活的變更通知上。

```figure
tp-tool-poisoning
```

## 動手實作

`code/main.py` 實作了一個小小的行程內安全閘道模型。它把完整的工具描述正規化並固定住、回報中繼資料下毒與遮蔽、驗證現代請求信封與路由值，並用已簽章的 `requestState` 與一個注入的共用重播儲存區，執行一次兩回合的確認式匯出。

這個模型是在 HTTP 轉接層已經解析完 JSON 主體與路由標頭之後才開始的。它不驗證 `Content-Type` 或 `Accept`。把同一個分派器接到單元 09 那個完整的 Streamable HTTP 轉接層，那裡會要求 `Content-Type: application/json`，以及同時包含 `application/json` 與 `text/event-stream` 的 `Accept` 值。

執行它：

```bash
cd phases/13-tools-and-protocols/15-mcp-security-tool-poisoning
python3 code/main.py
python3 -m unittest discover code/tests -v
```

這份範例刻意改動了一份描述。掃描器與摘要值比對會產出兩份彼此獨立的發現。接著那次匯出會示範 `input_required` 回應與無狀態重試。

## 框架應用

把 `SAFE_TOOLS` 換成你自己那些已核准伺服器的正規化快照。把憑證與機密留在快照之外。在更新摘要值之前，先審查每一份新增或變更的描述。

在閘道上，發現時跑一次同樣的檢查，分派之前再跑一次。快取可以減少發現的工作量，但快取住的核准必須會過期，或在描述改變時失效。

## 產出交付

這一課交付 `outputs/skill-mcp-threat-model.md`。它會產出一份對應現行協定的威脅模型，橫跨中繼資料、路由、能力、授權、MRTR、快取、登錄檔與相容性邊界。

## 練習

1. 把已認證的主體與當前授權決策，綁進封印好的 MRTR 狀態裡，然後拒絕一次來自不同主體的重試。
2. 把記憶體重播儲存區換成持久化的條件式插入，並證明兩個行程無法同時宣告同一個 nonce。
3. 在重播宣告之後、模擬匯出之前注入一次失敗。定義並測試那條讓復原變安全的交易或冪等性規則。
4. 改動某個工具的 `inputSchema`，但不改它的描述。確認整份描述的固定機制抓得到它。
5. 加上一條政策：當 `tools/list` 會因主體而異時，拒絕公開快取。
6. 在閘道後面模擬一台較舊的伺服器。把所有握手與工作階段行為，都放進一條明確的 `2025-11-25` 相容分支裡。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| 中繼資料下毒 | 嵌在工具描述裡的指令或欺騙性宣稱 |
| 抽地毯（Rug pull） | 對先前已核准之描述的改動 |
| 工具遮蔽 | 由重複的未限定名稱造成的路由歧義 |
| 標頭不一致 | 路由標頭與 JSON-RPC 主體不符，錯誤 `-32020` |
| 雜湊固定 | 完整已核准描述的摘要值 |
| MRTR | 針對伺服器索取輸入的無狀態回應與重試模式 |
| `requestState` | 必須被當成不可信輸入的不透明往返值 |
| 能力宣告 | 對協定相容性的陳述，不是授權 |
| 隱含的 form 支援 | 空的 `elicitation` 能力物件，等同於支援 form |
| 限定工具名稱 | 像 `notes.search` 這樣的穩定閘道名稱 |

## 延伸閱讀

- [MCP security and trust guidance](https://modelcontextprotocol.io/specification/2026-07-28#security-and-trust--safety)
- [Multi Round-Trip Requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [Streamable HTTP transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
- [Deprecated features](https://modelcontextprotocol.io/specification/2026-07-28/deprecated)
