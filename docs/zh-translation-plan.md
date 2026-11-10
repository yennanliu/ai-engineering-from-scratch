# 繁體中文 (zh-Hant) translation plan

Fork-only. How to close the gaps in `docs/zh-translation-gap.md`, one pull request at a time, and how
to review and validate each one. The gap doc says *what* is missing; this doc says *how* to fix it.

House style lives in `TRANSLATION-STYLE.md`. The agent workflow is `/translate-zh`
(`.claude/commands/translate-zh.md`), which follows this plan's per-lesson steps.

## Definition of done

| Measure | Today (2026-11-08) | Done when | Command |
|---|---|---|---|
| Lessons translated | 511 / 542 | 542 / 542 | `python3 scripts/i18n_status.py` |
| Quizzes translated | 361 / 392 | 392 / 392 | `python3 scripts/check_quiz_translations.py` |
| Lessons behind their English (wording) | 198 | 0 | `python3 scripts/zh_drift.py --kind content` |
| Lessons behind their English (math only) | 34 | 0 | `python3 scripts/zh_drift.py --kind math` |
| Pages without the zh dictionary | ~1,050 | 0, or excluded on purpose | `grep -L 'i18n.zh-Hant.js' site/*.html` (+ generated dirs) |
| Error-tier terms, non-standard headings | 0 | stays 0 | `python3 scripts/zh_terms.py --strict` |

**2026-11-10:** W1 and W2 are done (#39–#47). Wording drift is 0 lessons, math-only drift is 1
(03/13, a capitalisation with no Chinese counterpart). Next up: W3, then W4.

Every upstream sync adds new drift, so "done" is a state to return to after each sync, not a one-time
finish line. `docs/fork-sync.md` runs the drift report as part of every sync.

## Work order

Five workstreams. Do them in this order: stale content misleads readers today; missing content only
falls back to English.

| # | Workstream | Size | One PR is |
|---|---|---|---|
| W1 | Port English corrections into stale translations | 198 lessons, 455 passages | One phase (split phase 19 into two) |
| W2 | Copy inline math into stale translations | 34 math-only lessons, plus the math in W1 lessons | Folded into W1, same lessons |
| W3 | Load the zh dictionary on every page | ~1,050 pages | One PR |
| W4 | Translate the 31 missing lessons and their quizzes | ~131,000 words | Up to ~15,000 words |
| W5 | Review warn-tier terms | 1,656 occurrences | One term per PR |

### W1 + W2: stale translations, by phase

Lessons with wording drift per phase, largest first:

| Phase | Lessons | Phase | Lessons | Phase | Lessons |
|---|---|---|---|---|---|
| 19 capstones | 38 | 02 ML fundamentals | 12 | 03 deep learning | 8 |
| 12 multimodal | 17 | 18 safety | 10 | 05 NLP | 8 |
| 17 infrastructure | 15 | 08 generative | 9 | 07 transformers | 8 |
| 04 vision | 14 | 13 tools / protocols | 9 | 11 LLM engineering | 6 |
| 10 LLMs from scratch | 14 | 15 autonomous | 5 | 16 multi-agent | 5 |
| 14 agents | 14 | 09 RL | 3 | 06 speech | 2 |
| | | 01 math | 1 | | |

`python3 scripts/zh_drift.py --phase N` gives the current list. Fix every hunk of a lesson in one
commit, math included, so the lesson leaves the report in one step.

### W3: dictionary on every page

Add a fork-only post-build step to `.github/workflows/pages.yml`, after `pages_aliases.mjs`: a
script (`scripts/pages_i18n.mjs`) that inserts `<script src="i18n.zh-Hant.js">` and
`<script src="i18n.js">` into every built `.html` that lacks them, with the relative path adjusted
for the page's depth. Do not edit upstream's `site/build-*.js` generators; that would conflict on
every sync. Pages that render mostly English body content (interviews, cheat sheets) still gain the
translated header, navigation and language toggle. Test it the way `test_pages_aliases.mjs` tests the
alias step.

### W4: missing lessons, in this order

| Order | Lessons | Words | Why first |
|---|---|---|---|
| 1 | 14 / 43–54 (12) | ~8,800 | Short, and finishes phase 14 |
| 2 | 02 / 19–21 (3) | ~10,600 | Finishes phase 02 |
| 3 | 00 / 13, 17 / 29 | ~12,100 | Finishes phases 00 and 17 |
| 4 | 13 / 32–45 (14) | ~101,000 | The reverse-engineering track. Two lessons per PR |

## Per-lesson steps

### Syncing a stale lesson (W1, W2)

1. **Read the drift.** `python3 scripts/zh_drift.py --diff phases/<phase>/<lesson>` prints the English
   diff since the translation last synced, with the upstream commit subjects. Subjects with `correct …
   source errors` or `lesson claims` change facts.
2. **Apply each hunk to `docs/zh.md`.**
   - Wording hunk: translate the new English sentence and replace the old Chinese one. Leave text
     the diff does not touch alone.
   - Math hunk: copy the `$…$` or ```` ```math ```` from the English exactly.
   - Code or fenced block: copy it byte for byte.
   - Removed English: remove the matching Chinese.
3. **Run the gates** (below). Fix and rerun until clean.
4. **Preview the page** (below) if a heading, table, figure or formula changed.
5. **Commit** one lesson per commit:
   `fix(i18n/phase-NN/MM): sync zh with <what changed>`. The commit becomes the lesson's new drift
   baseline, so the lesson drops out of `zh_drift.py`.

### Translating a missing lesson (W4)

1. **Prepare.** Read the whole `docs/en.md`, and one translated lesson from the same phase for voice
   and term choices. Note terms the phase uses that `TRANSLATION-STYLE.md` does not cover.
2. **Translate section by section** (`##` by `##`), top to bottom, into `docs/zh.md`. Keep every
   heading, fence, table row, link and image in place (see *Structure* in `/translate-zh`).
   Never summarize. For lessons over ~5,000 words, write and check one section at a time.
3. **Translate the quiz** into `quiz.zh.json`: `question`, `options` and `explanation` only.
4. **Run the gates**, then **preview the page**.
5. **Commit** the lesson and its quiz together:
   `feat(i18n/phase-NN/MM): translate <slug> to zh-Hant`.
6. **Record new term decisions** in `TRANSLATION-STYLE.md` in the same PR, so the next lesson uses
   them.

### Commits that touch zh files without syncing them

A sweep across many `zh.md` files (term fixes, heading fixes, a mechanical copy of fences) must end
its commit message with a `Zh-Sync: none` trailer. Without it, `zh_drift.py` treats the commit as a
full sync and hides every English change before it.

## Validation

### Automated gates (every PR; CI runs the first three)

| Command | Catches | Blocking |
|---|---|---|
| `python3 scripts/i18n_status.py --verify` | Missing or extra headings, fences, figures, links, images; code that differs from English | Yes (CI) |
| `python3 scripts/check_quiz_translations.py --lang zh` | Quiz schema drift, a moved `correct` index, Simplified glyphs | Yes (CI) |
| `python3 scripts/zh_terms.py --strict` | Mainland-only terms, non-standard section headings and type labels | Yes (CI) |
| `python3 scripts/zh_drift.py --diff <lesson>` | English changes not yet ported | Run locally; must print `(no drift)` once committed |
| `python3 scripts/audit_lessons.py` | Lesson contract (English side) | Yes (CI) |

None of these can tell whether a sentence is translated correctly. That is what review is for.

### Local preview

On `localhost`, `site/content-source.js` reads lesson files from the working tree, so an unpushed
`docs/zh.md` renders as it will after merge:

```bash
node site/build.js                       # writes build-meta.js; then: git checkout -- site/data.js
python3 -m http.server 8000              # from the repo root
# open http://localhost:8000/site/lesson.html?path=phases/<phase>/<lesson>&lang=zh
```

Check on the page:
- The prose is Chinese, and section anchors are still English (`#build-it`, `#the-problem`): the
  sidebar table of contents links work.
- Formulas render as math, not as `code`, and the count matches the English page (`&lang=en`).
- Every `figure` widget mounts, and the quiz shows Chinese questions.
- Tables have the same rows as the English page.

### After merge

The `pages` workflow deploys on merge. Spot-check one lesson from the PR on the live site
(`…/lesson?path=phases/<phase>/<lesson>&lang=zh`), and rerun `zh_drift.py` and `i18n_status.py` on
`main` to confirm the numbers moved.

## Review

Every translation PR gets a review by someone (or a separate agent session) other than the
translator. Machine-translated or agent-translated text is reviewed the same way as human text.

### What the reviewer reads

| PR type | Read in full | Spot-check |
|---|---|---|
| Sync (W1, W2) | Every changed passage, side by side with the English diff | The surrounding paragraph, for flow |
| New lesson (W4) | Opening hook, *The Problem*, *The Concept*, *Key Terms* table, exercises, the whole quiz | One `Build It` step in three |
| Dictionary (W3) | The script and its test | Five pages at different depths, in a browser |
| Term review (W5) | Every changed line (`git diff --word-diff`) | |

### Checklist

1. **Accuracy.** Same claim, same numbers, same units, same negations as the English. Numbers and
   comparisons ("2–4× lower", "at most") are the most common slips.
2. **Completeness.** No sentence dropped or added. Compare paragraph counts in a long section.
3. **Corrections landed.** For a sync, the corrected fact from the upstream commit appears in the
   Chinese, and the old claim is gone.
4. **Terminology.** Matches `TRANSLATION-STYLE.md` and the rest of the phase. A new term is recorded
   in the style guide.
5. **Verbatim parts.** Code, figure names, URLs, paper titles, CLI flags and product names unchanged.
6. **Quiz.** Each explanation supports the option marked `correct`. Read it as a quiz-taker would.
7. **Readability.** Natural Taiwan technical Chinese, not word-for-word. Full-width punctuation,
   `「」` quotes, a space between Chinese and Latin text.
8. **Rendering.** The preview checks above, for any lesson whose structure or math changed.

The reviewer leaves comments on the PR with the line, the problem and the suggested Chinese; the
translator applies them in a new commit on the same branch.

## Pull requests

- Branch in the fork: `i18n/zh-<workstream>-phase-NN` (for example `i18n/zh-sync-phase-19a`,
  `i18n/zh-new-phase-14`). Open the PR against this fork's `main`, never upstream.
- One lesson per commit. Keep a PR under ~100 files so automated reviewers run, and under ~15,000
  translated words so a person can review it.
- The PR description lists each lesson with its drift or word count, and the gate output.
- At the end of each PR, update the numbers in `docs/zh-translation-gap.md`.

## Using agents

`/translate-zh` runs one lesson per pass. For a batch, give each agent about 600 changed lines (sync)
or one lesson (new). Give every agent the same brief: this plan, `TRANSLATION-STYLE.md`, and two
voice-reference lessons. Run the gates on the combined result before review. This batch size and
brief worked for the 2026-11 sync (`docs/fork-sync.md`). An agent's output still needs the review
above before merge.
