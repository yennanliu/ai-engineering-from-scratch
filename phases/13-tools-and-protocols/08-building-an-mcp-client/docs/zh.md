# 打造 MCP 客戶端：發現、路由與跨時代退路

> 現代 MCP 客戶端在每一則請求上重複自己的契約。它最難的相容性判斷，是分清楚一台舊伺服器是真的舊，還是一台現代伺服器正在回報一個可修正的錯誤。

**類型：** 實作
**程式語言：** Python
**先修單元：** 階段 13，單元 07
**時間：** 約 85 分鐘

## 學習目標

- 用當前的中繼資料建構每一則 MCP `2026-07-28` 請求。
- 用 `server/discover` 探測 stdio 伺服器，並選出雙方都支援的版本。
- 只對明確列在允許清單上的對端，授權一次有界限的舊版探測。
- 只有在驗證出一則針對受支援修訂版的正向 `initialize` 結果之後，才接受舊版時代。
- 合併確定性的工具清單，而不會悄悄覆蓋掉名稱衝突。
- 把呼叫路由到擁有該工具的對端，過程中不憑空造出協定工作階段。

## 問題所在

代理宿主通常會同時跟不只一台 MCP 伺服器對話。它必須發現每一台伺服器、合併工具目錄、解決重複名稱、路由呼叫，並從傳輸失敗中復原。

`2026-07-28` 修訂版讓穩定狀態變簡單了，因為每一則請求都自成一體。真正變得微妙的是啟動時的相容性。客戶端可能遇上：

- 一台支援偏好版本的現代伺服器；
- 一台回傳可辨識的版本或標頭錯誤的現代伺服器；
- 一台從沒聽過 `server/discover` 的舊版伺服器；
- 一台在收到 `initialize` 之前都保持沉默的舊版伺服器。

把每一個探測錯誤都當成舊版，是危險的。一則格式錯誤的現代請求、一台超載的伺服器、一個已死的行程，以及一台舊伺服器，都可能產生同樣的逾時或連線關閉。那些訊號是模稜兩可的。客戶端必須同時具備明確的維運意圖與正向的協定證據，才能選擇舊版時代。

## 核心概念

### 對端，不是協定工作階段

為每一個伺服器行程或端點保留一筆傳輸對端紀錄：

- 傳輸把手或送出函數；
- 選定的協定時代與版本；
- 最近一次發現到的伺服器能力；
- 最近一次的確定性工具清單；
- 待對應的請求 id；
- 傳輸健康狀態。

這是客戶端自己的帳本。它不是協定工作階段狀態。在現代 MCP 上，伺服器仍然會在每一則請求上收到當前的版本與能力。

### 每一則現代請求都從頭建構

```python
def modern_request(request_id, method, params, version, capabilities):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {
            **params,
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": version,
                "io.modelcontextprotocol/clientCapabilities": capabilities,
                "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            },
        },
    }
```

不要把中繼資料一次性掛在連線物件上，然後假設它有送上線路。要在最終序列化出來的請求上蓋章，並檢查它。

### 現代發現

`server/discover` 回傳受支援的版本、伺服器能力、使用說明、快取提示，以及建議填寫的伺服器身分。客戶端會挑出雙方都支援的最高現代版本。

對純現代的客戶端而言，發現是選用的，但在 stdio 上仍然建議做。有些舊版伺服器會在初始化之前就接受操作，所以先送 `tools/list` 可能得到一個模稜兩可的成功。`server/discover` 能劃出乾淨的時代邊界。

### stdio 相容性探測

跨時代的 stdio 客戶端會在任何其他請求之前，帶著自己偏好的現代中繼資料送出 `server/discover`。結果分成三類：

1. **DiscoverResult。** 對面是現代伺服器。選一個雙方都支援的版本，繼續走每請求中繼資料。
2. **可辨識的現代錯誤。** 對面是現代伺服器。遇到 `-32022` 就從 `data.supported` 裡挑一個，用新的請求 id 重試。遇到標頭或能力錯誤就修正請求。不要送 `initialize`。
3. **模稜兩可的訊號。** 無法辨識的 JSON-RPC 錯誤、逾時、連線關閉或空回應，都不足以判定時代。除非那個確切的對端被設定為允許舊版相容，否則就 fail closed。

可辨識的現代協定錯誤包括：

- `-32020` HeaderMismatch
- `-32021` MissingRequiredClientCapability
- `-32022` UnsupportedProtocolVersion

即使對端在舊版允許清單上，可辨識的現代錯誤仍然算現代。一旦伺服器證明它聽得懂現代錯誤詞彙，再送 `initialize` 就是一次降級。

不要把 `-32601` 當成正向的舊版證據。它只是讓一個明確列在允許清單上的對端，取得一次舊版探測的資格。逾時、連線關閉或空回應也適用同一條規則。

### 允許清單是維運意圖，不是證據

舊版相容必須是某一筆固定對端設定上的明確屬性：

```python
client.add_server("archive", archive_transport, allow_legacy=True)
```

把那個選擇綁在設定好的指令或端點上。不要用萬用字元讓任意伺服器自行選入較弱的語意。沒有 `allow_legacy=True` 的對端，在發現結果模稜兩可之後就失敗，而且永遠不會收到 `initialize`。

允許清單給的是探測的許可。它不決定時代。客戶端在傳輸層強制的期限內送出一次 `initialize`，然後要求以下全部成立：

- 一則 JSON-RPC `2.0` 回應，請求 id 相符；
- 恰好一個 `result`，而且沒有 `error`；
- `protocolVersion` 落在客戶端設定的舊版修訂集合內；
- `capabilities` 欄位的值是物件；
- 一個 `serverInfo` 物件，其中 `name` 與 `version` 是非空字串。

逾時、連線關閉、錯誤回應、格式錯誤的結果、id 不符，或不受支援的修訂版，一律 fail closed。只有結構有效的正向結果，才會選定舊版時代。程式碼會把 `legacy_probe_timeout_ms` 傳給傳輸轉接層；真正的 stdio 或 HTTP 轉接層必須執行那個期限，而不是只把它記下來。

把選定的時代快取在該傳輸對端上。不要在每次呼叫前都重新探測一遍。

### 舊版是一條相容分支

一旦有界限的探測回傳了有效的正向舊版證據，客戶端就完全照那個修訂版的定義，使用選定的舊版版本：

1. 驗證回應信封與對應 id。
2. 驗證協商出來的修訂版在設定的舊版集合內。
3. 記錄驗證過的能力與伺服器身分。
4. 所有檢查都通過之後，才送出 `notifications/initialized`。
5. 在那段傳輸生命期內使用舊版請求形狀。

這條分支的存在，是為了跟已知對端互通。它不是新伺服器或新請求的預設設計。如果傳輸重啟或端點改變，就丟掉對端時代快取，重新協商。

### 發現與快取工具

對每一個活躍的對端呼叫 `tools/list`。現代結果會包含 `resultType`、`ttlMs` 與 `cacheScope`。在正確的授權脈絡內遵守那個新鮮度提示。過期之後、或收到已訂閱的清單變更事件之後，重新抓取。

客戶端必須把舊版伺服器缺漏的 `resultType` 當成 `"complete"`。不要對協商到較早時代的回應要求現代快取欄位。

伺服器應該回傳確定性排序。客戶端在合併之前也應該自己排序一次，讓本地登錄表的順序不至於取決於行程啟動的時機。

### 不會撞名的命名空間合併

兩台伺服器可能都暴露 `search`。挑一條明訂的政策：

1. **撞名就加前綴。** 保留第一個標準名稱，後續撞名者以 `<server>/<tool>` 形式暴露。
2. **撞名就拒絕。** 不載入重複者，並拋出清楚的設定錯誤。
3. **無聲覆蓋。** 永遠不要用這個。它會遮蔽掉「模型選中的動作到底送去哪一台伺服器」。

同時保存標準名稱與本地名稱。模型看到的是標準名稱。送出去的 `tools/call` 用的是擁有它的伺服器所宣告的本地名稱。

### 路由一次呼叫

路由就是一次純粹的查表：

```text
canonical tool name
  -> peer name + local tool name
  -> new JSON-RPC request id
  -> modern request metadata or explicit legacy shape
  -> matching response id
```

當某個呼叫所屬的傳輸不可用時，就不要送出它。重新連線或重啟傳輸，然後重跑發現與 `tools/list`。在傳輸斷掉時遺失的現代在途請求，只要該操作的安全政策允許，就可以用一個新的 JSON-RPC id 重試。

### 通知與訂閱

現代的清單與資源變更，只會在客戶端開啟的 `subscriptions/listen` 串流上抵達。客戶端送出通知過濾條件，等待 `notifications/subscriptions/acknowledged`，再用通知中繼資料裡的 listen 請求 id 來對應事件。

斷線時，開一個新的 listen 請求，並重新抓取相關的清單或資源。現代串流不使用 `Last-Event-ID` 續傳。

### 沒有伺服器發起的請求

現代伺服器不會為了 sampling、elicitation 或 roots，用獨立的 JSON-RPC 請求去呼叫客戶端。它們回傳 `input_required`，客戶端滿足內嵌的輸入請求之後再重試原本的請求。

滿足輸入的過程中，不要卡住對端的回應讀取器。維持對應關係，並為重試建立一個新的 JSON-RPC id。

```figure
tp-client-merge
```

## 框架應用

`code/main.py` 使用行程內的對端函數，好讓協定決策保持可見。它連上兩個現代對端與一個刻意列入允許清單的舊版對端，然後合併並路由它們的工具。傳輸可呼叫物會收到一份逾時預算，讓相容分支藏不住一次沒有界限的探測。

```bash
cd code
python3 main.py
python3 -m unittest discover tests -v
```

這些測試證明的是一般示範會漏掉的邊界：

- 現代請求會重複帶上中繼資料；
- `-32022` 會重試現代發現，而不做初始化；
- 可辨識的現代錯誤永遠不降級，即使對端在允許清單上也一樣；
- 逾時、連線關閉、空回應與無法辨識的錯誤，在沒有允許清單時不會觸發 `initialize`；
- 允許清單上的對端，只有在拿到有效且受支援的 `initialize` 結果之後才變成舊版；
- 格式錯誤或不受支援的舊版結果，會讓對端維持不可用；
- 成功選定的時代會在該傳輸生命期內被快取。

## 產出交付

這一課交付 `outputs/skill-mcp-client-harness.md`。它會搭出現代請求蓋章、stdio 時代協商、確定性命名空間合併、路由，以及一條 fail-closed 的舊版相容分支。

## 練習

1. 讓一台假伺服器回傳 `-32022`，且沒有任何雙方都支援的版本。確認客戶端會失敗，而不是送出 `initialize`。
2. 把一台假舊版伺服器列入允許清單，讓它那次有界限的 `initialize` 探測逾時，並證明該對端維持在 `unknown` 且不可用。
3. 為兩個授權脈絡各加上 `cacheScope: "private"` 的工具清單。確認客戶端絕不把其中一個脈絡的快取結果分享給另一個。
4. 把撞名政策改成拒絕，並讓啟動失敗時的錯誤訊息同時帶上兩個對端名稱。
5. 加一個有限次的 `subscriptions/listen` 模擬器。串流遺失時，用新的請求 id 重新 listen 並重抓工具。

## 關鍵術語

| 術語 | 意義 |
|------|---------|
| 對端（Peer） | 客戶端這一側，對應一條伺服器傳輸及其發現資料的紀錄 |
| 協定時代 | 現代的每請求中繼資料，或舊版的初始化語意 |
| 發現探測 | 用來判定 stdio 時代的初次 `server/discover` |
| 可辨識的現代錯誤 | 證明對方是現代行為、因而禁止退回舊版的錯誤 |
| 舊版允許清單 | 維運設定，允許對某個固定對端做一次有界限的相容探測 |
| 正向舊版證據 | 針對明確受支援之舊版修訂、有效且已對應的 `initialize` 結果 |
| 合併命名空間 | 橫跨所有活躍對端的標準工具名稱 |
| 撞名政策 | 針對重複工具名稱的加前綴或拒絕規則 |
| 時代快取 | 為單一傳輸對端保存的現代或舊版行為選擇 |
| 傳輸復原 | 重啟或重連、重新發現、重新列清單，並用新 id 安全重試 |

## 延伸閱讀

- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/)
- [MCP Server Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [MCP stdio Transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
- [MCP Versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [MCP Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
