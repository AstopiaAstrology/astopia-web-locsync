import json
import tempfile
import unittest
from pathlib import Path
from webloc.json_io import load, flatten, unflatten, validate_paths, write
from webloc.icu import signature
from webloc.core import sync, validate
from webloc.sheet import Row, SheetClient
from webloc.merge import merge


class FakeSheet:
    def __init__(self):
        self.tables = {}
        self.writes = 0

    def read_rows(self, tab):
        return self.tables.get(tab, [])

    def replace_many(self, tables):
        self.tables.update(tables)
        self.writes += 1


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = {"InsightsHub": {"title": "  Hi {name}!\n"}, "credits_wallet_title": "Wallet"}
        self.cfg = {"locales_dir": str(self.root), "locales": ["en", "tr", "es", "fr", "pt"],
                    "source_locale": "en", "spreadsheet_id": "fake", "tab_prefix": "web_"}
        for locale in self.cfg["locales"]:
            write(self.root / f"{locale}.json", self.src)
        self.sheet = FakeSheet()

    def test_roundtrip_and_rejections(self):
        self.assertEqual(unflatten(flatten(self.src)), self.src)
        for obj in [{"a.b": "x"}, {"a[0]": "x"}, {"": "x"}]:
            with self.assertRaises(ValueError): flatten(obj)
        with self.assertRaises(ValueError): unflatten({"a": "x", "a.b": "y"})
        path = self.root / "duplicate.json"
        path.write_text('{"a":"x","a":"y"}')
        with self.assertRaises(ValueError): load(path)
        write(path, self.src)
        self.assertEqual(load(path), self.src)

    def test_arrays_metadata_and_empty_containers_roundtrip(self):
        data = {"cards": [{"id": 12, "text": "  Hello {name}\n", "active": True},
                          {"id": 25, "text": "Second", "extra": None}],
                "nested": [["A", "B"], ["C"]], "empty": [], "obj": {}}
        flat = flatten(data)
        self.assertEqual(flat["cards[0].text"], "  Hello {name}\n")
        self.assertNotIn("cards[0].id", flat)
        self.assertEqual(unflatten(flat, template=data), data)
        self.assertEqual(unflatten({"a[0]": "x", "a[1]": "y"}), {"a": ["x", "y"]})
        validate_paths({"a[5].text": "valid partial Sheet row"})
        for messages in [{"a": "x", "a[0]": "y"}, {"a.b": "x", "a[0]": "y"},
                         {"a[01]": "x"}, {"a[-1]": "x"}, {"a[0]b": "x"}]:
            with self.assertRaises(ValueError): validate_paths(messages)
        with self.assertRaises(ValueError): unflatten({"a[1]": "sparse"})
        with self.assertRaises(ValueError): unflatten({"cards[0].id": "bad"}, template=data)

    def test_array_pull_fallback_and_source_metadata(self):
        data = {"reviews": [{"id": 7, "text": "Hello {name}"},
                            {"id": 9, "text": "Fallback"}], "empty": []}
        for locale in self.cfg["locales"]:
            write(self.root / f"{locale}.json", data)
        sync(self.cfg, "seed", client=self.sheet)
        self.sheet.tables["web_tr"] = [Row("reviews[0].text", "  Merhaba {name}\n"),
                                        Row("reviews[1].text", "")]
        en = (self.root / "en.json").read_bytes()
        sync(self.cfg, "pull", client=self.sheet)
        result = load(self.root / "tr.json")
        self.assertEqual(result, {"reviews": [{"id": 7, "text": "  Merhaba {name}\n"},
                                              {"id": 9, "text": "Fallback"}], "empty": []})
        self.assertEqual((self.root / "en.json").read_bytes(), en)
        self.assertEqual(self.sheet.writes, 1)

    def test_icu(self):
        self.assertEqual(signature("{n, plural, one {<b>{name}</b>} other {# {name}}}"),
                         {"n": {"plural"}, "name": {"argument"}, "b": {"tag"}})
        self.assertEqual(signature("don't '{name}' ''"), {})
        for msg in ["{a", "{n, plural, one {x}}", "{n, plural, other {x} other {y}}",
                    "<b>x</c>", "{n, bogus}", "{n, plural, wat {x} other {x}}",
                    "{d, date, ::yyyy}"]:
            with self.assertRaises(ValueError, msg=msg): signature(msg)

    def test_push_preserves_targets_updates_source_and_pr_delta(self):
        sync(self.cfg, "seed", client=self.sheet)
        self.sheet.tables["web_tr"][0] = Row("InsightsHub.title", "Merhaba {name}")
        before = (self.root / "en.json").read_bytes()
        updated = dict(self.src, added="New")
        updated.pop("credits_wallet_title")
        base = self.root / "base.json"
        write(base, self.src)
        write(self.root / "en.json", updated)
        for locale in self.cfg["locales"][1:]:
            write(self.root / f"{locale}.json", updated)
        report, code = validate(self.cfg, base_source=base, client=self.sheet)
        self.assertEqual(code, 0, report)
        report, code = validate(self.cfg, client=self.sheet)
        self.assertEqual(code, 1)
        sync(self.cfg, "push", client=self.sheet)
        tr = {r.key: r.value for r in self.sheet.tables["web_tr"]}
        self.assertEqual(tr, {"InsightsHub.title": "Merhaba {name}", "added": ""})
        self.assertEqual({r.key: r.value for r in self.sheet.tables["web_en"]}, flatten(updated))
        en = (self.root / "en.json").read_bytes()
        sync(self.cfg, "pull", client=self.sheet)
        self.assertEqual((self.root / "en.json").read_bytes(), en)
        self.assertEqual(load(self.root / "tr.json")["added"], "New")

    def test_seed_skip_fallback_and_strict(self):
        sync(self.cfg, "seed", skip_fallback=True, client=self.sheet)
        self.assertTrue(all(not r.value for r in self.sheet.tables["web_tr"]))
        self.assertEqual(validate(self.cfg, client=self.sheet)[1], 0)
        self.assertEqual(validate(self.cfg, strict=True, client=self.sheet)[1], 1)

    def test_duplicate_and_bad_icu_fail_before_mutation(self):
        sync(self.cfg, "seed", client=self.sheet)
        self.sheet.tables["web_pt"].append(Row("credits_wallet_title", "x"))
        with self.assertRaises(ValueError): sync(self.cfg, "push", client=self.sheet)
        self.assertEqual(self.sheet.writes, 1)
        self.sheet.tables["web_pt"] = [Row("InsightsHub.title", "{wrong}")]
        before = (self.root / "tr.json").read_bytes()
        with self.assertRaises(ValueError): sync(self.cfg, "pull", client=self.sheet)
        self.assertEqual((self.root / "tr.json").read_bytes(), before)

    def test_genuine_sheet_missing_rows(self):
        sync(self.cfg, "seed", client=self.sheet)
        self.sheet.tables["web_es"].pop()
        report, code = validate(self.cfg, client=self.sheet)
        self.assertEqual(code, 1)
        self.assertTrue(any("missing rows" in e for e in report["errors"]))

    def test_merge(self):
        self.assertEqual(merge({"a": "old", "b": "old"}, {"a": "ours", "b": "old"},
                               {"a": "old", "b": "theirs"}), {"a": "ours", "b": "theirs"})
        self.assertEqual(merge({}, {"n": {"a": "x"}}, {"n": {"b": "y"}}),
                         {"n": {"a": "x", "b": "y"}})
        self.assertEqual(merge({"a": "x"}, {}, {"a": "x"}), {})
        for b, o, t in [({"a": "x"}, {}, {"a": "y"}),
                         ({"a": "x"}, {"a": "y"}, {"a": "z"})]:
            with self.assertRaises(ValueError): merge(b, o, t)

    def test_sheet_atomic_body(self):
        class Request:
            def execute(self): return {}
        class API:
            def batchUpdate(self, **kwargs):
                self.body = kwargs["body"]
                return Request()
        client = SheetClient.__new__(SheetClient)
        client.sid, client.api = "test", API()
        client.tabs = lambda: {"web_en": {"sheetId": 4, "gridProperties": {"rowCount": 100}}}
        client.replace_many({"web_en": [Row("a", "=literal")], "web_tr": []})
        requests = client.api.body["requests"]
        self.assertEqual(len(requests), 3)
        update = requests[0]["updateCells"]
        self.assertNotIn("endRowIndex", update["range"])
        self.assertEqual(update["rows"][1]["values"][1]["userEnteredValue"], {"stringValue": "=literal"})


if __name__ == "__main__":
    unittest.main()
