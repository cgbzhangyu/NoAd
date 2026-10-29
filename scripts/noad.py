#!/usr/bin/env python3
"""Build, validate and audit NoAd Shadowrocket modules.

The tool intentionally uses only Python's standard library. It validates the
project's own conservative subset of Shadowrocket module syntax; passing this
validator is not equivalent to a successful import on a real iPhone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "catalog" / "apps"
ALLOWLIST_FILE = ROOT / "catalog" / "allowlist.json"
SOURCES_FILE = ROOT / "catalog" / "sources.json"
DIST_DIR = ROOT / "dist"

APP_ORDER = ("bilibili", "xiachufang", "taobao", "jd", "smzdm")
TIERS = {"stable", "experimental"}
SECTIONS = {"Rule", "URL Rewrite"}
SAFE_RULE_DIRECTIVES = {"DOMAIN"}
SAFE_ACTIONS = {"REJECT"}
REWRITE_ACTIONS = {"reject", "reject-200", "reject-dict", "reject-array"}
SENSITIVE_TOKENS = {
    "account",
    "auth",
    "cart",
    "cashier",
    "coupon",
    "login",
    "order",
    "passport",
    "pay",
    "payment",
    "trade",
}
BANNED_MITM_HOSTS = {"*", "*.com", "*.cn", "*.net", "*.org"}


class ValidationError(Exception):
    """Raised when catalog or output validation fails."""


@dataclass(frozen=True)
class AppCatalog:
    path: Path
    data: dict[str, Any]

    @property
    def app_id(self) -> str:
        return self.data["app"]["id"]

    @property
    def name(self) -> str:
        return self.data["app"]["name"]

    @property
    def rules(self) -> list[dict[str, Any]]:
        return self.data["rules"]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_catalogs(catalog_dir: Path = CATALOG_DIR) -> list[AppCatalog]:
    catalogs: list[AppCatalog] = []
    for path in sorted(catalog_dir.glob("*.json")):
        catalogs.append(AppCatalog(path=path, data=read_json(path)))
    return catalogs


def load_disabled_rule_ids(path: Path = ALLOWLIST_FILE) -> set[str]:
    data = read_json(path)
    values = data.get("disabled_rule_ids", [])
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValidationError(f"{path}: disabled_rule_ids must be a string array")
    return set(values)


def _require(mapping: dict[str, Any], keys: Iterable[str], context: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValidationError(f"{context}: missing fields: {', '.join(missing)}")


def _validate_evidence(rule: dict[str, Any], context: str) -> None:
    evidence = rule.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValidationError(f"{context}: at least one evidence item is required")
    for index, item in enumerate(evidence):
        item_context = f"{context}.evidence[{index}]"
        if not isinstance(item, dict):
            raise ValidationError(f"{item_context}: must be an object")
        _require(item, ("project", "url", "license", "usage"), item_context)
        if item["usage"] not in {"derived", "evidence-only"}:
            raise ValidationError(f"{item_context}: invalid usage")
        if item["usage"] == "derived" and item["license"] != "GPL-2.0-only":
            raise ValidationError(
                f"{item_context}: derived material must be GPL-2.0-only compatible"
            )
        if not str(item["url"]).startswith("https://"):
            raise ValidationError(f"{item_context}: evidence URL must use HTTPS")


def validate_catalogs(
    catalogs: list[AppCatalog], disabled_rule_ids: set[str]
) -> list[str]:
    errors: list[str] = []
    seen_apps: set[str] = set()
    seen_rules: dict[str, str] = {}
    seen_matches: dict[tuple[str, str, str], tuple[str, str]] = {}

    def capture(callable_: Any) -> None:
        try:
            callable_()
        except (ValidationError, re.error) as exc:
            errors.append(str(exc))

    for catalog in catalogs:
        path = catalog.path
        data = catalog.data
        try:
            _require(data, ("schema_version", "app", "rules"), str(path))
            if data["schema_version"] != 1:
                raise ValidationError(f"{path}: unsupported schema_version")
            app = data["app"]
            _require(app, ("id", "name", "critical_flows"), f"{path}.app")
            if app["id"] in seen_apps:
                raise ValidationError(f"{path}: duplicate app id {app['id']}")
            seen_apps.add(app["id"])
            if path.stem != app["id"]:
                raise ValidationError(f"{path}: filename must equal app id")
            if not isinstance(app["critical_flows"], list) or not app["critical_flows"]:
                raise ValidationError(f"{path}.app: critical_flows must be non-empty")
            if not isinstance(data["rules"], list):
                raise ValidationError(f"{path}: rules must be an array")
        except ValidationError as exc:
            errors.append(str(exc))
            continue

        for index, rule in enumerate(catalog.rules):
            context = f"{path}.rules[{index}]"
            try:
                _require(
                    rule,
                    (
                        "id",
                        "tier",
                        "section",
                        "match",
                        "action",
                        "purpose",
                        "risk",
                        "source_status",
                        "device_status",
                        "evidence",
                    ),
                    context,
                )
                rule_id = rule["id"]
                if rule_id in seen_rules:
                    raise ValidationError(
                        f"{context}: duplicate rule id; first seen in {seen_rules[rule_id]}"
                    )
                seen_rules[rule_id] = context
                if not rule_id.startswith(f"{catalog.app_id}."):
                    raise ValidationError(f"{context}: rule id must start with app id")
                if rule["tier"] not in TIERS:
                    raise ValidationError(f"{context}: invalid tier")
                if rule["section"] not in SECTIONS:
                    raise ValidationError(f"{context}: invalid section")
                if rule["source_status"] not in {"supported", "candidate", "retired"}:
                    raise ValidationError(f"{context}: invalid source_status")
                if rule["device_status"] not in {"unverified", "passed", "failed", "stale"}:
                    raise ValidationError(f"{context}: invalid device_status")
                if rule["risk"] not in {"low", "medium", "high"}:
                    raise ValidationError(f"{context}: invalid risk")
                _validate_evidence(rule, context)

                if rule["section"] == "Rule":
                    _require(rule, ("directive",), context)
                    if rule["directive"] not in SAFE_RULE_DIRECTIVES:
                        raise ValidationError(f"{context}: unsupported Rule directive")
                    if rule["action"] not in SAFE_ACTIONS:
                        raise ValidationError(f"{context}: unsupported Rule action")
                    if rule["tier"] != "stable":
                        raise ValidationError(f"{context}: Rule entries belong in stable tier")
                    if rule.get("mitm_hosts"):
                        raise ValidationError(f"{context}: stable rule cannot declare MITM")
                else:
                    if rule["tier"] != "experimental":
                        raise ValidationError(f"{context}: rewrites must be experimental")
                    if rule["action"] not in REWRITE_ACTIONS:
                        raise ValidationError(f"{context}: unsupported rewrite action")
                    hosts = rule.get("mitm_hosts")
                    if not isinstance(hosts, list) or not hosts:
                        raise ValidationError(f"{context}: rewrite requires MITM hosts")
                    for host in hosts:
                        if host in BANNED_MITM_HOSTS:
                            raise ValidationError(f"{context}: unsafe MITM host {host}")
                        if any(token in host.lower() for token in SENSITIVE_TOKENS):
                            raise ValidationError(f"{context}: sensitive MITM host {host}")
                    re.compile(rule["match"])
                    for example in rule.get("match_examples", []):
                        if re.search(rule["match"], example) is None:
                            raise ValidationError(
                                f"{context}: regex does not match example {example}"
                            )

                signature = (rule["tier"], rule["section"], rule["match"])
                previous = seen_matches.get(signature)
                if previous and previous[1] != rule["action"]:
                    raise ValidationError(
                        f"{context}: action conflicts with {previous[0]} for same match"
                    )
                if previous and previous[1] == rule["action"]:
                    raise ValidationError(f"{context}: duplicate match from {previous[0]}")
                seen_matches[signature] = (rule_id, rule["action"])
            except (ValidationError, re.error) as exc:
                errors.append(str(exc))

    missing_apps = set(APP_ORDER) - seen_apps
    extra_apps = seen_apps - set(APP_ORDER)
    if missing_apps:
        errors.append(f"missing app catalogs: {', '.join(sorted(missing_apps))}")
    if extra_apps:
        errors.append(f"unknown app catalogs: {', '.join(sorted(extra_apps))}")
    unknown_disabled = disabled_rule_ids - set(seen_rules)
    if unknown_disabled:
        errors.append(f"allowlist references unknown rules: {', '.join(sorted(unknown_disabled))}")
    return errors


def _header(name: str, tier: str, rule_count: int) -> list[str]:
    label = "Stable" if tier == "stable" else "Experimental / MITM Required"
    return [
        f"#!name=NoAd - {name} ({label})",
        "#!desc=安全优先的 Shadowrocket 去广告模块；规则状态以仓库报告为准",
        "#!author=cgbzhangyu",
        "#!homepage=https://github.com/cgbzhangyu/NoAd",
        "#!category=广告拦截",
        "#!system=ios",
        f"#!rule-count={rule_count}",
        "",
    ]


def render_module(
    name: str,
    tier: str,
    rules: list[dict[str, Any]],
    disabled_rule_ids: set[str],
) -> str:
    active = [rule for rule in rules if rule["tier"] == tier and rule["id"] not in disabled_rule_ids]
    lines = _header(name, tier, len(active))
    if tier == "stable":
        lines.append("[Rule]")
        if not active:
            lines.append("# 当前没有符合稳定版安全门槛的规则")
        for rule in active:
            lines.append(f"# {rule['id']} | {rule['purpose']} | device={rule['device_status']}")
            lines.append(
                f"{rule['directive']},{rule['match']},{rule['action']}"
            )
    else:
        lines.extend(
            [
                "# WARNING: 本模块需要 HTTPS 解密，默认不得启用。",
                "# 仅在阅读风险说明并准备完成真机回归后安装。",
                "",
                "[URL Rewrite]",
            ]
        )
        if not active:
            lines.append("# 当前没有实验规则")
        for rule in active:
            lines.append(
                f"# {rule['id']} | {rule['purpose']} | risk={rule['risk']} | device={rule['device_status']}"
            )
            lines.append(f"{rule['match']} - {rule['action']}")
        hosts = sorted({host for rule in active for host in rule.get("mitm_hosts", [])})
        if hosts:
            lines.extend(["", "[MITM]", f"hostname = %APPEND% {','.join(hosts)}"])
    return "\n".join(lines).rstrip() + "\n"


def build_outputs(
    catalogs: list[AppCatalog], disabled_rule_ids: set[str]
) -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    all_rules: list[dict[str, Any]] = []
    by_id = {catalog.app_id: catalog for catalog in catalogs}
    for app_id in APP_ORDER:
        catalog = by_id[app_id]
        all_rules.extend(catalog.rules)
        outputs[DIST_DIR / "canary" / f"{app_id}.sgmodule"] = render_module(
            catalog.name, "stable", catalog.rules, disabled_rule_ids
        )
        outputs[DIST_DIR / "experimental" / f"{app_id}.sgmodule"] = render_module(
            catalog.name, "experimental", catalog.rules, disabled_rule_ids
        )
    outputs[DIST_DIR / "canary" / "all.sgmodule"] = render_module(
        "五 App 合集", "stable", all_rules, disabled_rule_ids
    )
    return outputs


def validate_module_text(path: Path, content: str) -> list[str]:
    """Validate the generated conservative module subset line by line."""
    errors: list[str] = []
    lines = content.splitlines()
    if not lines or not lines[0].startswith("#!name="):
        errors.append(f"{path}: missing #!name header")
    current_section: str | None = None
    seen_sections: set[str] = set()
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            if current_section not in {"Rule", "URL Rewrite", "MITM"}:
                errors.append(f"{path}:{number}: unsupported section {current_section}")
            if current_section in seen_sections:
                errors.append(f"{path}:{number}: duplicate section {current_section}")
            seen_sections.add(current_section)
            continue
        if current_section == "Rule":
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 3 or parts[0] != "DOMAIN" or parts[2] != "REJECT":
                errors.append(f"{path}:{number}: invalid stable rule line")
        elif current_section == "URL Rewrite":
            if " - " not in line:
                errors.append(f"{path}:{number}: invalid URL Rewrite line")
                continue
            pattern, action = line.rsplit(" - ", 1)
            if action not in REWRITE_ACTIONS:
                errors.append(f"{path}:{number}: invalid rewrite action {action}")
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{path}:{number}: invalid regex: {exc}")
        elif current_section == "MITM":
            if not line.startswith("hostname = %APPEND% "):
                errors.append(f"{path}:{number}: invalid MITM declaration")
        else:
            errors.append(f"{path}:{number}: content outside a section")
    if "canary" in path.parts and seen_sections != {"Rule"}:
        errors.append(f"{path}: canary module must contain only [Rule]")
    if "experimental" in path.parts:
        if "Rule" in seen_sections:
            errors.append(f"{path}: experimental module cannot contain [Rule]")
        if "URL Rewrite" not in seen_sections:
            errors.append(f"{path}: missing [URL Rewrite]")
    return errors


def write_or_check_outputs(outputs: dict[Path, str], check: bool) -> list[str]:
    mismatches: list[str] = []
    expected_paths = set(outputs)
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    for directory in (DIST_DIR / "canary", DIST_DIR / "experimental"):
        if directory.exists():
            for path in directory.glob("*.sgmodule"):
                if path not in expected_paths:
                    if check:
                        mismatches.append(str(path.relative_to(ROOT)))
                    else:
                        path.unlink()
    return sorted(set(mismatches))


def validation_report(catalogs: list[AppCatalog]) -> dict[str, Any]:
    apps: list[dict[str, Any]] = []
    for catalog in catalogs:
        rules = []
        for rule in catalog.rules:
            rules.append(
                {
                    "id": rule["id"],
                    "tier": rule["tier"],
                    "syntax_status": "passed",
                    "source_status": rule["source_status"],
                    "device_status": rule["device_status"],
                    "risk": rule["risk"],
                }
            )
        apps.append({"id": catalog.app_id, "name": catalog.name, "rules": rules})
    return {
        "schema_version": 1,
        "notice": "Static syntax pass does not prove Shadowrocket import or ad blocking.",
        "apps": apps,
    }


def check_promotion(catalogs: list[AppCatalog]) -> list[str]:
    """Require a matching privacy-safe device record for every stable rule."""
    errors: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    verification_dir = ROOT / "verifications"
    for path in sorted(verification_dir.glob("*.json")):
        if path.name == "template.json":
            continue
        data = read_json(path)
        rule_id = data.get("rule_id")
        if not isinstance(rule_id, str):
            errors.append(f"{path}: missing rule_id")
            continue
        if rule_id in records:
            errors.append(f"{path}: duplicate verification for {rule_id}")
        records[rule_id] = data

    for catalog in catalogs:
        for rule in catalog.rules:
            if rule["tier"] != "stable":
                continue
            if rule["device_status"] != "passed":
                errors.append(f"{rule['id']}: stable promotion requires device_status=passed")
            record = records.get(rule["id"])
            if not record:
                errors.append(f"{rule['id']}: missing device verification record")
                continue
            if record.get("result") != "passed":
                errors.append(f"{rule['id']}: verification result is not passed")
            privacy = record.get("privacy", {})
            privacy_keys = {
                "contains_headers",
                "contains_query_values",
                "contains_bodies",
                "contains_identifiers",
            }
            missing_privacy = privacy_keys - set(privacy)
            unsafe = [key for key in privacy_keys if privacy.get(key) is not False]
            if missing_privacy:
                errors.append(
                    f"{rule['id']}: missing privacy declarations: {', '.join(sorted(missing_privacy))}"
                )
            if unsafe:
                errors.append(
                    f"{rule['id']}: privacy declaration is incomplete/unsafe: {', '.join(unsafe)}"
                )
    return errors


def write_checksums(output: Path) -> int:
    paths = sorted((DIST_DIR / "canary").glob("*.sgmodule"))
    if not paths:
        print("No canary modules found; run build first.", file=sys.stderr)
        return 1
    lines = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


def audit_sources(output: Path) -> int:
    data = read_json(SOURCES_FILE)
    results: list[dict[str, Any]] = []
    changed = False
    failed = False
    for source in data["sources"]:
        result = {"id": source["id"], "url": source["url"], "status": "unknown"}
        try:
            request = urllib.request.Request(
                source["url"], headers={"User-Agent": "NoAd-source-audit/0.1"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            digest = hashlib.sha256(body).hexdigest()
            result.update({"status": "ok", "sha256": digest, "bytes": len(body)})
            expected = source.get("expected_sha256")
            if expected and expected != digest:
                result["status"] = "changed"
                changed = True
            elif expected is None:
                result["status"] = "baseline-required"
        except (OSError, urllib.error.URLError) as exc:
            result.update({"status": "unavailable", "error": str(exc)})
            failed = True
        results.append(result)
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "results": results,
        "changed": changed,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if changed:
        return 2
    return 1 if failed else 0


def command_validate() -> int:
    catalogs = load_catalogs()
    disabled = load_disabled_rule_ids()
    errors = validate_catalogs(catalogs, disabled)
    if not errors:
        for path, content in build_outputs(catalogs, disabled).items():
            errors.extend(validate_module_text(path, content))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Validated {sum(len(item.rules) for item in catalogs)} rules across {len(catalogs)} apps.")
    return 0


def command_build(check: bool) -> int:
    catalogs = load_catalogs()
    disabled = load_disabled_rule_ids()
    errors = validate_catalogs(catalogs, disabled)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    outputs = build_outputs(catalogs, disabled)
    for path, content in outputs.items():
        errors.extend(validate_module_text(path, content))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    mismatches = write_or_check_outputs(outputs, check)
    if mismatches:
        print("Generated output is stale:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  {mismatch}", file=sys.stderr)
        return 1
    verb = "Checked" if check else "Wrote"
    print(f"{verb} {len(outputs)} Shadowrocket modules.")
    return 0


def command_report(output: Path) -> int:
    catalogs = load_catalogs()
    disabled = load_disabled_rule_ids()
    errors = validate_catalogs(catalogs, disabled)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    report = validation_report(catalogs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate rule catalogs")
    build = subparsers.add_parser("build", help="build deterministic modules")
    build.add_argument("--check", action="store_true", help="check outputs without writing")
    report = subparsers.add_parser("report", help="write validation status report")
    report.add_argument(
        "--output", type=Path, default=ROOT / "dist" / "status.json"
    )
    audit = subparsers.add_parser("audit-sources", help="download and hash source material")
    audit.add_argument("--output", type=Path, default=ROOT / "source-audit.json")
    subparsers.add_parser(
        "check-promotion", help="require device evidence for all stable rules"
    )
    checksums = subparsers.add_parser("checksums", help="hash stable modules")
    checksums.add_argument(
        "--output", type=Path, default=ROOT / "dist" / "SHA256SUMS"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return command_validate()
    if args.command == "build":
        return command_build(args.check)
    if args.command == "report":
        return command_report(args.output)
    if args.command == "audit-sources":
        return audit_sources(args.output)
    if args.command == "check-promotion":
        catalogs = load_catalogs()
        errors = check_promotion(catalogs)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("Stable promotion gate passed.")
        return 0
    if args.command == "checksums":
        return write_checksums(args.output)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

