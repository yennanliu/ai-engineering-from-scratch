# 技能與代理 SDK —— Anthropic Skills、AGENTS.md、OpenAI Apps SDK

> MCP 說的是「有哪些工具」。技能說的是「一項任務該怎麼做」。2026 年的堆疊把兩者疊在一起。Anthropic 的 Agent Skills（開放標準，2025 年 12 月）以帶漸進揭露的 SKILL.md 出貨。OpenAI 的 Apps SDK 則是 MCP 加上 widget 中繼資料。AGENTS.md（如今已在 60,000 個以上的儲存庫裡）坐在儲存庫根目錄，作為專案層級的代理上下文。這一課會指出各自涵蓋什麼，並做一個能跨代理攜帶的最小 SKILL.md + AGENTS.md 套組。

**類型：** 學習
**程式語言：** Python (stdlib, SKILL.md parser and loader)
**先修單元：** 階段 13 · 07（MCP 伺服器）
**時間：** 約 45 分鐘

## 學習目標

- 分辨這三層：AGENTS.md（專案上下文）、SKILL.md（可重用的知道怎麼做）、MCP（工具）。
- 寫一份帶 YAML frontmatter 與漸進揭露的 SKILL.md。
- 以檔案系統的方式把技能載入代理執行環境。
- 把一項技能與一台 MCP 伺服器、一份 AGENTS.md 組合起來，讓同一個套件在 Claude Code、Cursor 與 Codex 中都能運作。

## 問題所在

一位工程師把撰寫發布說明的工作流程，蒸餾成一段多步驟提示詞：「讀取最近合併的 PR。依領域分組。逐一摘要。依團隊風格寫一則變更日誌條目。發到 Slack 草稿。」他把它放進團隊的一份 Notion 文件裡。

現在他想從 Claude Code、Cursor 與 Codex CLI 使用這套工作流程。每個代理載入指示的方式都不同：Claude Code 用斜線指令、Cursor 用 rules、Codex 用 `.codex.md`。這位工程師把工作流程抄了三份，然後維護三份。

AGENTS.md 與 SKILL.md 合起來修掉了這件事：

- **AGENTS.md** 坐在儲存庫根目錄。每個相容的代理在工作階段開始時都會讀它。「這個專案怎麼運作？慣例是什麼？跑測試用哪個指令？」
- **SKILL.md** 是一個可攜的套組：YAML frontmatter（name、description）+ markdown 本體 + 選配的資源。支援技能的代理會依名稱按需載入它們。
- **MCP**（階段 13 · 06-14）則負責這項技能需要呼叫的那些工具。

三層，一個可攜的產物。

## 核心概念

### AGENTS.md（agents.md）

2025 年底推出，到 2026 年 4 月已被 60,000 個以上的儲存庫採用。儲存庫根目錄下的單一個檔案。格式是：

```markdown
# Project: my-service

## Conventions
- TypeScript with strict mode.
- Use Pydantic for models on the Python side.
- Tests run with `pnpm test`.

## Build and run
- `pnpm dev` for local dev server.
- `pnpm build` for production bundle.
```

代理在工作階段開始時讀取它，並據此為那個專案校準自己的行為。2026 年的每個寫程式代理都支援 AGENTS.md：Claude Code、Cursor、Codex、Copilot Workspace、opencode、Windsurf、Zed。

### SKILL.md 格式

Anthropic 的 Agent Skills（2025 年 12 月以開放標準釋出）：

```markdown
---
name: release-notes-writer
description: Write a changelog entry for the latest merged PRs following this project's style.
---

# Release notes writer

When invoked, run these steps:

1. List PRs merged since the last tag. Use `gh pr list --base main --state merged`.
2. Group by label: feature, fix, chore, docs.
3. For each PR in each group, write one line: `- <title> (#<num>)`.
4. Draft the release notes and stage them in CHANGELOG.md.

If the user says "ship", run `git tag vX.Y.Z` and `gh release create`.

## Notes

- Never include commits without a PR.
- Skip "chore" entries from the public changelog.
```

Frontmatter 宣告這項技能的身分。本體則是技能載入時呈現給模型的那段提示詞。

### 漸進揭露

技能可以參照一些子資源，讓代理只在需要時才去抓。例如：

```
skills/
  release-notes-writer/
    SKILL.md
    style-guide.md
    template.md
    scripts/
      generate.sh
```

SKILL.md 寫著「風格規則見 style-guide.md」。代理只有在這項技能正在執行時，才會把 style-guide.md 拉進來。這避免了用模型可能根本用不到的細節把提示詞撐胖。

### 檔案系統探索

代理執行環境會掃描幾個已知目錄，找出 SKILL.md 檔案：

- `~/.anthropic/skills/*/SKILL.md`
- 專案的 `./skills/*/SKILL.md`
- `~/.claude/skills/*/SKILL.md`

載入是依資料夾名稱與 frontmatter 的 `name`。Claude Code、Anthropic Claude Agent SDK 與 SkillKit（跨代理）全都遵循這個模式。

### Anthropic Claude Agent SDK

`@anthropic-ai/claude-agent-sdk`（TypeScript）與 `claude-agent-sdk`（Python）會在工作階段開始時載入技能，並把它們在執行環境中暴露成可呼叫的「代理」。使用者調用某項技能時，代理迴圈就分派過去。

### OpenAI Apps SDK

2025 年 10 月推出；直接建構在 MCP 之上。它把 OpenAI 先前的 Connectors 與 Custom GPT Actions，統一到單一個開發者表面之下。一個 Apps SDK 應用是：

- 一台 MCP 伺服器（工具、資源、提示詞）。
- 加上給 ChatGPT UI 用的 widget 中繼資料。
- 再加上一個選配的 MCP Apps `ui://` 資源，用於互動式表面。

同樣的協定，更豐富的 UX。

### 透過 SkillKit 的跨代理可攜性

SkillKit 這類工具與類似的跨代理散布層，能把單一份 SKILL.md 翻譯成 32 種以上 AI 代理（Claude Code、Cursor、Codex、Gemini CLI、OpenCode 等）各自的原生格式。單一份真值來源；眾多使用者。

### 三層堆疊

| 層 | 檔案 | 何時載入 | 用途 |
|-------|------|-------------|---------|
| AGENTS.md | 儲存庫根目錄 | 工作階段開始 | 專案層級的慣例 |
| SKILL.md | skills 目錄 | 技能被調用時 | 可重用的工作流程 |
| MCP 伺服器 | 外部行程 | 需要工具時 | 可呼叫的動作 |

三者都能組合起來：代理在工作階段開始時讀 AGENTS.md，使用者調用一項技能，該技能的指示中包含 MCP 工具呼叫，代理再透過 MCP 客戶端分派出去。

## 框架應用

`code/main.py` 出貨了一個 stdlib 的 SKILL.md 解析器與載入器。它在 `./skills/` 底下探索技能、解析 YAML frontmatter 與 markdown 本體，並產出一個以技能名稱為鍵的 dict。接著它模擬一個代理迴圈，依名稱調用 `release-notes-writer`。

要看的地方有：

- YAML frontmatter 用一個最小的 stdlib 解析器處理（不依賴 `pyyaml`）。
- 技能本體原封不動地存下來；代理在調用時把它接到系統提示詞前面。
- 漸進揭露以一個 `read_subresource` 函式示範，它會按需拉取被參照的檔案。

## 產出交付

這一課產出 `outputs/skill-agent-bundle.md`。給定一套工作流程，這項技能會產出合併起來的 SKILL.md + AGENTS.md + MCP 伺服器藍圖套組，可跨代理攜帶。

## 練習

1. 跑一次 `code/main.py`。在 `skills/` 底下加上第二項技能，確認載入器有抓到它。

2. 為這門課程的儲存庫寫一份 AGENTS.md。納入測試指令、風格慣例，以及階段 13 的心智模型。

3. 把你團隊內部文件裡的一套多步驟工作流程移植成一份 SKILL.md。驗證它能在 Claude Code 中載入。

4. 用手把那項技能翻譯成 Cursor 與 Codex 的原生規則格式。數一數格式之間的差異 —— 這就是 SkillKit 自動化掉的那片翻譯表面。

5. 讀 Anthropic 的 Agent Skills 部落格文章。找出一項 Claude Agent SDK 中、而本課載入器沒有涵蓋的功能。（提示：代理的子調用。）

## 關鍵術語

| 術語 | 大家怎麼說 | 實際上是什麼 |
|------|----------------|------------------------|
| SKILL.md | 「那個技能檔」 | YAML frontmatter 加 markdown 本體，由代理執行環境載入 |
| AGENTS.md | 「儲存庫根目錄的代理上下文」 | 在工作階段開始時讀取的專案層級慣例檔 |
| 漸進揭露 | 「延遲載入子資源」 | 技能本體參照的檔案，只在需要時才拉進來 |
| Frontmatter | 「頂端的 YAML 區塊」 | 以 `---` 分隔的中繼資料（name、description） |
| Claude Agent SDK | 「Anthropic 的技能執行環境」 | `@anthropic-ai/claude-agent-sdk`，負責載入技能並做路由 |
| OpenAI Apps SDK | 「MCP + widget 中繼資料」 | OpenAI 建構在 MCP 之上、加上 ChatGPT UI 掛鉤的開發者表面 |
| 技能探索 | 「檔案系統掃描」 | 走訪已知目錄找出 SKILL.md，並以名稱為鍵 |
| 跨代理可攜性 | 「一份技能，多個代理」 | 透過 SkillKit 這類工具，把一份 SKILL.md 翻譯給 32 種以上的代理 |
| Agent Skill | 「可攜的做事訣竅」 | MCP 工具概念之外、可重用的任務模板 |
| Apps SDK | 「MCP 加 ChatGPT UI」 | 統一在 MCP 之上的 Connectors 與 Custom GPT |

## 延伸閱讀

- [Anthropic — Agent Skills announcement](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) —— 2025 年 12 月的發布
- [Anthropic — Agent Skills docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) —— SKILL.md 格式的參考
- [OpenAI — Apps SDK](https://developers.openai.com/apps-sdk) —— 建構在 MCP 上、給 ChatGPT 用的開發者平台
- [agents.md](https://agents.md/) —— AGENTS.md 的格式與採用清單
- [Anthropic — anthropics/skills GitHub](https://github.com/anthropics/skills) —— 官方的技能範例
