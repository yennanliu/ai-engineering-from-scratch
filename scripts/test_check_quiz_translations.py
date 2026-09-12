#!/usr/bin/env python3
"""Regression checks for the translated-quiz validator.

One rule here carries most of the weight: Q005. A `correct` index that drifts
between quiz.json and quiz.<lang>.json teaches the wrong answer to every
reader of that language, and reading the Chinese cannot reveal it — the prose
is still fluent and the option it points at is still plausible. These tests pin
each rule to a fixture that actually violates it, so a rule cannot quietly stop
firing.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import check_quiz_translations as cqt


def question(stage="pre", correct=1, options=("A", "B"), question="What?",
             explanation="Because."):
    return {
        "stage": stage,
        "question": question,
        "options": list(options),
        "correct": correct,
        "explanation": explanation,
    }


def zh_question(stage="pre", correct=1, options=("甲", "乙"), question="這是什麼？",
                explanation="因為如此。"):
    return {
        "stage": stage,
        "question": question,
        "options": list(options),
        "correct": correct,
        "explanation": explanation,
    }


class CheckPairTest(unittest.TestCase):
    def check(self, en_doc, zh_doc, lang="zh"):
        """Run the checker over a fixture pair, returning the rule codes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lesson = root / "phases" / "00-p" / "01-l"
            lesson.mkdir(parents=True)
            en_path = lesson / "quiz.json"
            zh_path = lesson / f"quiz.{lang}.json"
            en_path.write_text(json.dumps(en_doc), encoding="utf-8")
            zh_path.write_text(
                zh_doc if isinstance(zh_doc, str) else json.dumps(zh_doc, ensure_ascii=False),
                encoding="utf-8",
            )
            with mock.patch.object(cqt, "REPO", root):
                issues = cqt.check_pair(en_path, zh_path, lang)
        return [i["rule"] for i in issues], issues

    def test_a_faithful_translation_is_clean(self):
        rules, issues = self.check([question()], [zh_question()])
        self.assertEqual(rules, [], issues)

    def test_q001_invalid_json(self):
        rules, _ = self.check([question()], "{not json")
        self.assertEqual(rules, ["Q001"])

    def test_q002_top_level_shape_must_match(self):
        # The site branches on the shape; a bare list where the English is
        # {"questions": [...]} renders nothing.
        rules, _ = self.check({"questions": [question()]}, [zh_question()])
        self.assertEqual(rules, ["Q002"])

    def test_q002_dict_without_a_questions_array(self):
        rules, _ = self.check({"questions": [question()]}, {"items": []})
        self.assertEqual(rules, ["Q002"])

    def test_q003_question_count_must_match(self):
        rules, _ = self.check([question(), question()], [zh_question()])
        self.assertEqual(rules, ["Q003"])

    def test_q004_stage_sequence_must_match(self):
        rules, _ = self.check([question(stage="pre")], [zh_question(stage="post")])
        self.assertIn("Q004", rules)

    def test_q005_correct_index_drift_is_caught(self):
        rules, issues = self.check([question(correct=1)], [zh_question(correct=0)])
        self.assertIn("Q005", rules)
        self.assertIn("correct=0", issues[0]["message"])

    def test_q006_option_count_must_match(self):
        rules, _ = self.check(
            [question(options=("A", "B", "C"))], [zh_question(options=("甲", "乙"))]
        )
        self.assertIn("Q006", rules)

    def test_q007_missing_required_key(self):
        broken = zh_question()
        del broken["explanation"]
        rules, issues = self.check([question()], [broken])
        self.assertEqual(rules, ["Q007"])
        self.assertIn("explanation", issues[0]["message"])

    def test_q007_blank_where_the_english_has_prose(self):
        rules, _ = self.check([question()], [zh_question(explanation="   ")])
        self.assertIn("Q007", rules)

    def test_q007_blank_is_allowed_where_the_english_is_also_blank(self):
        # 524 English questions ship an empty explanation; mirroring that is
        # correct, not a defect.
        rules, issues = self.check(
            [question(explanation="")], [zh_question(explanation="")]
        )
        self.assertEqual(rules, [], issues)

    def test_q008_untranslated_question_has_no_cjk(self):
        rules, _ = self.check([question()], [zh_question(question="What?")])
        self.assertIn("Q008", rules)

    def test_q009_simplified_characters_are_rejected(self):
        # 这 is Simplified; the site ships 繁體中文, and the surrounding
        # sentence stays valid Chinese, so review will not catch it.
        rules, issues = self.check([question()], [zh_question(question="这是什麼？")])
        self.assertIn("Q009", rules)
        self.assertIn("这", "".join(i["message"] for i in issues))

    def test_q008_and_q009_apply_only_to_zh(self):
        # A Japanese translation is not Traditional Chinese and must not be
        # measured against either rule.
        rules, _ = self.check(
            [question()], [zh_question(question="What?")], lang="ja"
        )
        self.assertEqual(rules, [])

    def test_issue_paths_are_repo_relative(self):
        _, issues = self.check([question()], [zh_question(correct=0)])
        self.assertEqual(issues[0]["file"], "phases/00-p/01-l/quiz.zh.json")


class QuestionsOfTest(unittest.TestCase):
    def test_bare_list(self):
        self.assertEqual(cqt.questions_of([{"a": 1}]), ([{"a": 1}], "list"))

    def test_wrapped_dict(self):
        self.assertEqual(cqt.questions_of({"questions": []}), ([], "dict"))

    def test_neither(self):
        self.assertEqual(cqt.questions_of("nope"), (None, "str"))


class RuleTableTest(unittest.TestCase):
    def test_every_documented_rule_is_reachable(self):
        """Each Q00N in the docstring must be a code the checker can emit."""
        import re
        documented = set(re.findall(r"^  (Q\d{3})", cqt.__doc__, re.M))
        implemented = set(re.findall(r'add\("(Q\d{3})"',
                                     Path(cqt.__file__).read_text(encoding="utf-8")))
        self.assertEqual(documented, implemented)


if __name__ == "__main__":
    unittest.main(verbosity=2)
