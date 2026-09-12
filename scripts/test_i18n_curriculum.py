#!/usr/bin/env python3
"""Regression checks for the zh-Hant curriculum dictionary generator.

The generator rewrites a committed file in place, keyed by position: title N in
TITLES_ZH is paired with lesson N out of data.js. If those lists ever disagree
in length, every title after the gap silently attaches to the wrong lesson —
which is why the generator refuses to run rather than shifting them. That guard
is the most important thing here, and it is exactly what fired when upstream
added twelve lessons to phase 14.

The rest pin the rewrite contract: regeneration replaces the previous generated
block instead of stacking a second one, and hand-written keys above the marker
win over anything generated, because the dictionary is one flat namespace where
a duplicate key is a silent overwrite.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import i18n_curriculum as ic


HEAD = '''/* i18n.zh-Hant.js — Traditional Chinese dictionary. */
window.I18N_ZH_HANT = {
  "Contents": "目錄",
};
'''

DATA = {
    "PHASES": [{
        "id": 0,
        "name": "Setup and Tooling",
        "desc": "Get the machine ready.",
        "lessons": [{"name": "Dev Environment"}, {"name": "Git and Collaboration"}],
    }],
    "GLOSSARY": [{"term": "KV Cache", "says": "kay-vee cache", "means": "Reused attention state."}],
}


class EmitTest(unittest.TestCase):
    def test_pairs_render_as_dictionary_entries(self):
        out = ic.emit([("Contents", "目錄")], "Phases", set())
        self.assertIn('"Contents": "目錄",', out)
        self.assertIn("Phases", out)

    def test_cjk_is_not_escaped(self):
        # ensure_ascii=False: an escaped \\uXXXX key would never match the
        # source string the site looks up.
        self.assertNotIn("\\u", ic.emit([("Contents", "目錄")], "T", set()))

    def test_a_key_already_seen_is_skipped(self):
        seen = {"Contents"}
        out = ic.emit([("Contents", "目錄"), ("Catalog", "課程總覽")], "T", seen)
        self.assertNotIn('"Contents"', out)
        self.assertIn('"Catalog"', out)

    def test_emitting_registers_the_key_so_later_pairs_cannot_repeat_it(self):
        seen = set()
        ic.emit([("Contents", "目錄")], "T", seen)
        self.assertIn("Contents", seen)

    def test_untranslated_pairs_are_dropped(self):
        out = ic.emit([("Contents", ""), ("", "目錄")], "T", set())
        self.assertNotIn('"Contents"', out)

    def test_long_entries_wrap_onto_a_second_line(self):
        # The generator wraps when the encoded key and value together exceed
        # 92 columns, so the emitted file stays readable in review.
        long_en = "x" * 95
        out = ic.emit([(long_en, "短")], "T", set())
        self.assertIn(f'"{long_en}":\n', out)

    def test_short_entries_stay_on_one_line(self):
        out = ic.emit([("Contents", "目錄")], "T", set())
        self.assertIn('"Contents": "目錄",', out)
        self.assertNotIn('"Contents":\n', out)


class MainTest(unittest.TestCase):
    def run_main(self, data=None, titles=None, phases=None, glossary=None, head=HEAD):
        """Run the generator against a fixture repo root, returning the file."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "site").mkdir()
        target = root / "site" / "i18n.zh-Hant.js"
        target.write_text(head, encoding="utf-8")

        with mock.patch.object(ic, "ROOT", root), \
             mock.patch.object(ic, "load_data", lambda: data or DATA), \
             mock.patch.object(ic, "TITLES_ZH",
                               titles if titles is not None
                               else {0: ["開發環境", "Git 與協作"]}), \
             mock.patch.object(ic, "PHASES_ZH",
                               phases if phases is not None
                               else {0: ("設定與工具", "讓機器就緒。")}), \
             mock.patch.object(ic, "GLOSSARY_ZH",
                               glossary if glossary is not None
                               else {"KV Cache": ("kay-vee 快取", "重複使用的注意力狀態。")}):
            with contextlib.redirect_stdout(io.StringIO()):
                ic.main()
        return target

    def test_a_title_count_mismatch_aborts_instead_of_shifting_titles(self):
        # One translation for two lessons: pairing would attach "開發環境" to
        # lesson 1 and leave lesson 2 English, or worse, shift a whole phase.
        with self.assertRaises(SystemExit) as caught:
            self.run_main(titles={0: ["開發環境"]})
        self.assertIn("phase 0", str(caught.exception))
        self.assertIn("1 translations for 2 lessons", str(caught.exception))

    def test_matching_counts_pair_each_title_with_its_lesson(self):
        text = self.run_main().read_text(encoding="utf-8")
        self.assertIn('"Dev Environment": "開發環境",', text)
        self.assertIn('"Git and Collaboration": "Git 與協作",', text)

    def test_phase_name_and_description_are_emitted(self):
        text = self.run_main().read_text(encoding="utf-8")
        self.assertIn('"Setup and Tooling": "設定與工具",', text)
        self.assertIn('"Get the machine ready.": "讓機器就緒。",', text)

    def test_glossary_says_and_means_are_emitted(self):
        text = self.run_main().read_text(encoding="utf-8")
        self.assertIn('"kay-vee cache": "kay-vee 快取",', text)
        self.assertIn('"Reused attention state.": "重複使用的注意力狀態。",', text)

    def test_a_phase_with_no_translations_is_skipped_not_failed(self):
        # Partial translation has to stay safe: an untranslated phase falls
        # back to English rather than blocking every other phase.
        text = self.run_main(titles={}).read_text(encoding="utf-8")
        self.assertNotIn('"Dev Environment"', text)
        self.assertIn('"Contents": "目錄",', text)

    def test_regeneration_is_idempotent(self):
        target = self.run_main()
        first = target.read_text(encoding="utf-8")
        # Re-run against the file the first pass produced, exactly as a second
        # invocation in a working tree would.
        second_target = self.run_main(head=first)
        self.assertEqual(second_target.read_text(encoding="utf-8"), first)

    def test_regeneration_replaces_the_previous_block_rather_than_stacking(self):
        first = self.run_main().read_text(encoding="utf-8")
        second = self.run_main(head=first).read_text(encoding="utf-8")
        self.assertEqual(second.count("── GENERATED"), 1)
        self.assertEqual(second.count('"Dev Environment"'), 1)

    def test_hand_written_keys_are_not_duplicated_by_the_generator(self):
        # "Setup and Tooling" is already defined above the marker; the flat
        # namespace means a second entry would silently overwrite the first.
        head = HEAD.replace('  "Contents": "目錄",\n',
                            '  "Contents": "目錄",\n  "Setup and Tooling": "手寫翻譯",\n')
        text = self.run_main(head=head).read_text(encoding="utf-8")
        self.assertEqual(text.count('"Setup and Tooling"'), 1)
        self.assertIn('"Setup and Tooling": "手寫翻譯",', text)

    def test_output_stays_a_valid_object_literal(self):
        text = self.run_main().read_text(encoding="utf-8")
        self.assertTrue(text.rstrip().endswith("};"))
        self.assertEqual(text.count("};"), 1)


class RealDictionaryTest(unittest.TestCase):
    """The committed dictionary must match what the generator would write.

    Nothing else checks this: build.js never reads i18n.zh-Hant.js, so a stale
    dictionary is invisible until a reader meets English where a translation
    should be. Run against a copy of the repo so a failure — or an interrupt —
    can never leave the real file half-written.
    """

    def test_committed_dictionary_is_up_to_date(self):
        repo = Path(ic.__file__).resolve().parents[1]
        committed = (repo / "site" / "i18n.zh-Hant.js").read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "site").mkdir()
            shutil.copy2(repo / "site" / "data.js", root / "site" / "data.js")
            target = root / "site" / "i18n.zh-Hant.js"
            target.write_text(committed, encoding="utf-8")

            with mock.patch.object(ic, "ROOT", root), \
                 contextlib.redirect_stdout(io.StringIO()):
                ic.main()
            regenerated = target.read_text(encoding="utf-8")

        self.assertEqual(
            regenerated, committed,
            "site/i18n.zh-Hant.js is stale — run python3 scripts/i18n_curriculum.py",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
