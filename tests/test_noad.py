from __future__ import annotations

import copy
import unittest

from scripts import noad


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogs = noad.load_catalogs()

    def test_catalog_is_valid(self) -> None:
        self.assertEqual([], noad.validate_catalogs(self.catalogs))

    def test_all_required_apps_exist(self) -> None:
        self.assertEqual(
            set(noad.APP_ORDER), {catalog.app_id for catalog in self.catalogs}
        )

    def test_outputs_are_only_individual_app_modules(self) -> None:
        outputs = noad.build_outputs(self.catalogs)
        self.assertEqual(5, len(outputs))
        self.assertEqual(
            {f"{app_id}.sgmodule" for app_id in noad.APP_ORDER},
            {path.name for path in outputs},
        )
        self.assertTrue(all(path.parent == noad.DIST_DIR for path in outputs))

    def test_app_modules_do_not_embed_general_rules(self) -> None:
        outputs = noad.build_outputs(self.catalogs)
        for content in outputs.values():
            self.assertIn("[MITM]", content)
            self.assertNotIn("[Rule]", content)
            self.assertNotIn("RULE-SET,", content)
            self.assertNotIn("DOMAIN-SET,", content)
            self.assertNotIn(",DIRECT", content)
            self.assertNotIn(",PROXY", content)

    def test_all_generated_modules_pass_line_validator(self) -> None:
        outputs = noad.build_outputs(self.catalogs)
        errors = []
        for path, content in outputs.items():
            errors.extend(noad.validate_module_text(path, content))
        self.assertEqual([], errors)

    def test_bilibili_uses_owned_response_script(self) -> None:
        outputs = noad.build_outputs(self.catalogs)
        content = outputs[noad.DIST_DIR / "bilibili.sgmodule"]
        self.assertIn("[Script]", content)
        self.assertNotIn("[URL Rewrite]", content)
        self.assertIn("type=http-response", content)
        self.assertIn(
            "https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/"
            "runtime/bilibili-splash.js",
            content,
        )
        self.assertNotIn("reject-dict", content)

    def test_bilibili_runtime_script_has_no_logging_or_network_calls(self) -> None:
        script = (noad.ROOT / "runtime" / "bilibili-splash.js").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "console.",
            "$notification",
            "$notify",
            "$httpClient",
            "$task.fetch",
            "$request.url",
            "access_key",
        ):
            self.assertNotIn(forbidden, script)
        for field in ("max_time", "keep_ids", "list", "show"):
            self.assertIn(field, script)

    def test_duplicate_rule_id_is_rejected(self) -> None:
        copied = copy.deepcopy(self.catalogs)
        duplicate = copy.deepcopy(copied[0].data["rules"][0])
        copied[0].data["rules"].append(duplicate)
        errors = noad.validate_catalogs(copied)
        self.assertTrue(any("duplicate rule id" in error for error in errors))

    def test_every_regex_matches_its_examples(self) -> None:
        for catalog in self.catalogs:
            for rule in catalog.rules:
                self.assertTrue(rule.get("match_examples"), rule["id"])
                for example in rule["match_examples"]:
                    self.assertRegex(example, rule["match"])


if __name__ == "__main__":
    unittest.main()
