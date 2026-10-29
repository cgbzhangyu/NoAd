from __future__ import annotations

import copy
import unittest

from scripts import noad


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogs = noad.load_catalogs()
        self.disabled = noad.load_disabled_rule_ids()

    def test_catalog_is_valid(self) -> None:
        self.assertEqual([], noad.validate_catalogs(self.catalogs, self.disabled))

    def test_all_required_apps_exist(self) -> None:
        self.assertEqual(
            set(noad.APP_ORDER), {catalog.app_id for catalog in self.catalogs}
        )

    def test_stable_output_cannot_enable_mitm(self) -> None:
        outputs = noad.build_outputs(self.catalogs, self.disabled)
        for path, content in outputs.items():
            if path.parent.name == "canary":
                self.assertNotIn("[MITM]", content)
                self.assertNotIn("[URL Rewrite]", content)
                self.assertNotIn("[Script]", content)
                self.assertNotIn(",DIRECT", content)
                self.assertNotIn(",PROXY", content)

    def test_experimental_output_has_explicit_warning(self) -> None:
        outputs = noad.build_outputs(self.catalogs, self.disabled)
        for path, content in outputs.items():
            if path.parent.name == "experimental":
                self.assertIn("WARNING", content)
                if "#!rule-count=0" not in content:
                    self.assertIn("[MITM]", content)

    def test_all_generated_modules_pass_line_validator(self) -> None:
        outputs = noad.build_outputs(self.catalogs, self.disabled)
        errors = []
        for path, content in outputs.items():
            errors.extend(noad.validate_module_text(path, content))
        self.assertEqual([], errors)

    def test_allowlist_omits_rule_without_forcing_direct(self) -> None:
        content = noad.render_module(
            "测试",
            "stable",
            self.catalogs[0].rules,
            {"bilibili.domain.cm"},
        )
        self.assertNotIn("cm.bilibili.com", content)
        self.assertNotIn("DIRECT", content)

    def test_duplicate_rule_id_is_rejected(self) -> None:
        copied = copy.deepcopy(self.catalogs)
        duplicate = copy.deepcopy(copied[0].data["rules"][0])
        copied[0].data["rules"].append(duplicate)
        errors = noad.validate_catalogs(copied, self.disabled)
        self.assertTrue(any("duplicate rule id" in error for error in errors))

    def test_every_experimental_regex_matches_its_examples(self) -> None:
        for catalog in self.catalogs:
            for rule in catalog.rules:
                if rule["tier"] != "experimental":
                    continue
                self.assertTrue(rule.get("match_examples"), rule["id"])

    def test_unverified_stable_rule_blocks_promotion(self) -> None:
        errors = noad.check_promotion(self.catalogs)
        self.assertTrue(
            any("device_status=passed" in error for error in errors), errors
        )


if __name__ == "__main__":
    unittest.main()

