#!/usr/bin/env python3
"""Regression checks for the translation coverage reporter.

--verify is the only automated guard on a `docs/<lang>.md`: audit_lessons.py
reads en.md alone and build.js never opens a translation, so a structural
mistake in one reaches the site. These tests pin the checks it makes, and the
two places a naive implementation reports the opposite of the truth: a `#`
comment inside a fenced block is not a heading, and alt text that survives
translation untouched passes every check that only compares image paths.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import i18n_status


EN = """# Lesson Title

Intro prose.

## Section

```bash
# macOS
brew install node
```

![A diagram of the cache](assets/cache.svg)

See the [spec](https://example.com/spec).

```figure
kv-cache
```
"""

ZH = """# 課程標題

介紹文字。

## 章節

```bash
# macOS
brew install node
```

![快取示意圖](assets/cache.svg)

參見[規格](https://example.com/spec)。

```figure
kv-cache
```
"""


def write_lesson(root: Path, en: str, zh: str) -> Path:
    lesson = root / "01-lesson"
    (lesson / "docs").mkdir(parents=True)
    (lesson / "docs" / "en.md").write_text(en, encoding="utf-8")
    (lesson / "docs" / "zh.md").write_text(zh, encoding="utf-8")
    return lesson


class ShapeTest(unittest.TestCase):
    def test_hash_inside_a_fence_is_not_a_heading(self):
        # The bash comment `# macOS` would otherwise be counted as an H1 and
        # mask a genuinely missing heading in the translation.
        self.assertEqual(i18n_status.shape(EN)["headings"], ["#", "##"])

    def test_fenced_blocks_are_counted_and_their_bodies_captured(self):
        shape = i18n_status.shape(EN)
        self.assertEqual(shape["fences"], 2)
        self.assertIn("brew install node\n```", shape["code"][0])

    def test_figure_widget_names_are_extracted(self):
        # lesson-figures.js mounts on this exact string; translating it would
        # leave the widget unmounted.
        self.assertEqual(i18n_status.shape(EN)["figures"], ["kv-cache"])

    def test_links_images_and_alt_text_are_extracted(self):
        shape = i18n_status.shape(EN)
        self.assertEqual(shape["links"], ["https://example.com/spec"])
        self.assertEqual(shape["images"], ["assets/cache.svg"])
        self.assertEqual(shape["alts"], ["A diagram of the cache"])


class VerifyTest(unittest.TestCase):
    def verify(self, en: str, zh: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            lesson = write_lesson(Path(tmp), en, zh)
            return i18n_status.verify(lesson, "zh")

    def test_a_faithful_translation_reports_nothing(self):
        self.assertEqual(self.verify(EN, ZH), [])

    def test_dropped_heading_is_reported(self):
        self.assertTrue(
            any("heading outline differs" in p
                for p in self.verify(EN, ZH.replace("## 章節\n\n", "")))
        )

    def test_dropped_fence_is_reported(self):
        broken = ZH.replace("```bash\n# macOS\nbrew install node\n```\n\n", "")
        problems = self.verify(EN, broken)
        self.assertTrue(any("fence count differs" in p for p in problems))

    def test_translated_figure_name_is_reported(self):
        problems = self.verify(EN, ZH.replace("kv-cache", "kv-快取"))
        self.assertTrue(any("figure widgets differ" in p for p in problems))

    def test_changed_link_is_reported(self):
        problems = self.verify(EN, ZH.replace("https://example.com/spec",
                                              "https://example.com/other"))
        self.assertTrue(any("links differ" in p for p in problems))

    def test_changed_image_path_is_reported(self):
        problems = self.verify(EN, ZH.replace("assets/cache.svg", "assets/other.svg"))
        self.assertTrue(any("image paths differ" in p for p in problems))

    def test_untranslated_alt_text_is_reported(self):
        # Same image path, same everything else: only the alt text gives it
        # away, and it is what a screen reader actually reads out.
        problems = self.verify(EN, ZH.replace("![快取示意圖]", "![A diagram of the cache]"))
        self.assertTrue(any("alt text left untranslated" in p for p in problems))

    def test_translated_alt_text_is_accepted(self):
        self.assertEqual(
            [p for p in self.verify(EN, ZH) if "alt text" in p], []
        )

    def test_drifted_code_block_is_reported(self):
        # Lesson code mirrors code/main.*; translating a code block silently
        # forks the prose from the program the lesson ships.
        problems = self.verify(EN, ZH.replace("brew install node", "brew install 節點"))
        self.assertTrue(any("code block contents drifted" in p for p in problems))


class TotalsTest(unittest.TestCase):
    def test_totals_sum_only_translated_words(self):
        phases = [{
            "phase": "00-setup",
            "lessons": [
                {"slug": "a", "path": "p/a", "words": 100, "translated": True},
                {"slug": "b", "path": "p/b", "words": 250, "translated": False},
            ],
        }]
        self.assertEqual(
            i18n_status.totals(phases),
            {"lessons": 2, "done": 1, "words": 350, "words_done": 100},
        )

    def test_totals_of_nothing_do_not_divide_by_zero(self):
        self.assertEqual(
            i18n_status.totals([]),
            {"lessons": 0, "done": 0, "words": 0, "words_done": 0},
        )

    def test_word_count_of_a_missing_file_is_zero(self):
        self.assertEqual(i18n_status.word_count(Path("/nonexistent/en.md")), 0)


class CollectTest(unittest.TestCase):
    def test_translated_flag_follows_the_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            phase = root / "phases" / "00-setup"
            for slug, translated in (("01-a", True), ("02-b", False)):
                docs = phase / slug / "docs"
                docs.mkdir(parents=True)
                (docs / "en.md").write_text("one two three", encoding="utf-8")
                if translated:
                    (docs / "zh.md").write_text("一 二 三", encoding="utf-8")
            # A lesson with no en.md is not part of the denominator.
            (phase / "03-no-docs").mkdir(parents=True)

            with mock.patch.object(i18n_status, "ROOT", root), \
                 mock.patch.object(i18n_status, "PHASES", root / "phases"):
                phases = i18n_status.collect("zh")

            lessons = phases[0]["lessons"]
            self.assertEqual([l["slug"] for l in lessons], ["01-a", "02-b"])
            self.assertEqual([l["translated"] for l in lessons], [True, False])
            self.assertEqual(lessons[0]["words"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
