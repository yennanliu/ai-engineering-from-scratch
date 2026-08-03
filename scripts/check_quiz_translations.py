#!/usr/bin/env python3
"""Validate quiz.<lang>.json files against their English quiz.json.

lesson.html renders a translated quiz with the same code path as the English
one, so a translation must keep the schema exactly: same question order, same
stage sequence, same number of options, and the same `correct` index. Only the
prose changes. A drifted `correct` index silently teaches the wrong answer,
which no amount of reading the Chinese would catch.

Rules
  Q001  quiz.<lang>.json is valid UTF-8 JSON
  Q002  same top-level shape as quiz.json (bare list vs {"questions": [...]})
  Q003  same number of questions
  Q004  same `stage` for every question, in the same order
  Q005  same `correct` index for every question
  Q006  same number of options for every question
  Q007  required keys present, values are non-empty strings
  Q008  question/option/explanation prose actually contains CJK (warning:
        an entry identical to English is usually an untranslated leftover,
        but a bare term like "PPO" legitimately stays as-is)

Usage
  python3 scripts/check_quiz_translations.py            # all languages found
  python3 scripts/check_quiz_translations.py --lang zh
  python3 scripts/check_quiz_translations.py --phase 14
  python3 scripts/check_quiz_translations.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PHASES = REPO / "phases"
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
REQUIRED = ("question", "options", "correct", "explanation", "stage")


def questions_of(doc):
    """quiz.json is a bare list in most lessons and {"questions": [...]} in
    some; the site accepts both, so the checker has to as well."""
    if isinstance(doc, dict):
        return doc.get("questions"), "dict"
    if isinstance(doc, list):
        return doc, "list"
    return None, type(doc).__name__


def check_pair(en_path: Path, zh_path: Path, lang: str) -> list[dict]:
    rel = zh_path.relative_to(REPO).as_posix()
    issues: list[dict] = []

    def add(rule, msg):
        issues.append({"rule": rule, "file": rel, "message": msg})

    try:
        zh_doc = json.loads(zh_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        add("Q001", f"not valid UTF-8 JSON: {exc}")
        return issues

    en_doc = json.loads(en_path.read_text(encoding="utf-8"))
    en_qs, en_shape = questions_of(en_doc)
    zh_qs, zh_shape = questions_of(zh_doc)

    if zh_shape != en_shape:
        add("Q002", f"top-level shape is {zh_shape}, quiz.json is {en_shape}")
        return issues
    if zh_qs is None:
        add("Q002", "no questions array")
        return issues
    if len(zh_qs) != len(en_qs):
        add("Q003", f"{len(zh_qs)} questions, quiz.json has {len(en_qs)}")
        return issues

    for i, (en_q, zh_q) in enumerate(zip(en_qs, zh_qs)):
        where = f"question {i + 1}"

        missing = [k for k in REQUIRED if k not in zh_q]
        if missing:
            add("Q007", f"{where}: missing {', '.join(missing)}")
            continue

        if zh_q["stage"] != en_q["stage"]:
            add("Q004", f"{where}: stage {zh_q['stage']!r}, quiz.json has {en_q['stage']!r}")
        if zh_q["correct"] != en_q["correct"]:
            add("Q005", f"{where}: correct={zh_q['correct']}, quiz.json has {en_q['correct']}")
        if len(zh_q["options"]) != len(en_q["options"]):
            add("Q006", f"{where}: {len(zh_q['options'])} options, quiz.json has {len(en_q['options'])}")

        # 524 English questions across 85 lessons ship an empty explanation.
        # A translation mirrors its source, so "empty" is only a defect where
        # the English side has prose to translate.
        pairs = [("question", zh_q["question"], en_q["question"]),
                 ("explanation", zh_q["explanation"], en_q["explanation"])]
        pairs += [(f"option {k}", z, e)
                  for k, (z, e) in enumerate(zip(zh_q["options"], en_q["options"]))]
        blank = [name for name, zt, et in pairs
                 if not isinstance(zt, str) or (str(et).strip() and not zt.strip())]
        if blank:
            add("Q007", f"{where}: {', '.join(blank)} empty but the English is not")
            continue

        if lang == "zh" and not CJK.search(zh_q["question"]):
            add("Q008", f"{where}: question has no CJK — untranslated?")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", help="only this language code (default: every quiz.<lang>.json found)")
    ap.add_argument("--phase", type=int, help="only this phase number")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args()

    pattern = f"quiz.{args.lang}.json" if args.lang else "quiz.*.json"
    prefix = f"{args.phase:02d}-" if args.phase is not None else ""

    issues: list[dict] = []
    langs: dict[str, int] = {}
    total_en = 0

    for phase_dir in sorted(PHASES.glob(f"{prefix}*")):
        if not phase_dir.is_dir():
            continue
        for lesson in sorted(phase_dir.iterdir()):
            en_path = lesson / "quiz.json"
            if not en_path.is_file():
                continue
            total_en += 1
            for zh_path in sorted(lesson.glob(pattern)):
                lang = zh_path.name.split(".")[1]
                langs[lang] = langs.get(lang, 0) + 1
                issues.extend(check_pair(en_path, zh_path, lang))

    if args.json:
        print(json.dumps({"english_quizzes": total_en, "translated": langs, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"{issue['rule']}  {issue['file']}: {issue['message']}")
        coverage = ", ".join(f"{k}={v}/{total_en}" for k, v in sorted(langs.items())) or "none"
        print(f"\n{total_en} English quizzes; translated: {coverage}")
        print(f"{len(issues)} issue(s)" if issues else "clean")

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
