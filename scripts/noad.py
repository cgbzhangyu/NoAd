#!/usr/bin/env python3
"""Build, validate and audit app-specific NoAd Shadowrocket modules."""

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
SOURCES_FILE = ROOT / "catalog" / "sources.json"
DIST_DIR = ROOT / "dist" / "apps"

APP_ORDER = ("bilibili", "xiachufang", "taobao", "jd", "smzdm")
SECTIONS = {"URL Rewrite", "Script"}
REWRITE_ACTIONS = {"reject", "reject-200", "reject-dict", "reject-array"}
SCRIPT_ACTIONS = {"http-response"}
OWNED_SCRIPT_PREFIX = (
    "https://raw.githubusercontent.com/cgbzhangyu/NoAd/refs/heads/main/runtime/"
)
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


def load_catalogs(catalog_dir: Path = CATALOG_DIR) -> list[AppCatalog]:
    return [
        AppCatalog(path=path, data=read_json(path))
        for path in sorted(catalog_dir.glob("*.json"))
    ]


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


def _validate_mitm_hosts(rule: dict[str, Any], context: str) -> None:
    hosts = rule.get("mitm_hosts")
    if not isinstance(hosts, list) or not hosts:
        raise ValidationError(f"{context}: app rule requires MITM hosts")
    for host in hosts:
        if not isinstance(host, str) or not host:
            raise ValidationError(f"{context}: invalid MITM host")
        if host in BANNED_MITM_HOSTS:
            raise ValidationError(f"{context}: unsafe MITM host {host}")
        if any(token in host.lower() for token in SENSITIVE_TOKENS):
            raise ValidationError(f"{context}: sensitive MITM host {host}")


def _validate_match(rule: dict[str, Any], context: str) -> None:
    re.compile(rule["match"])
    examples = rule.get("match_examples")
    if not isinstance(examples, list) or not examples:
        raise ValidationError(f"{context}: match_examples must be non-empty")
    for example in examples:
        if re.search(rule["match"], example) is None:
            raise ValidationError(f"{context}: regex does not match example {example}")


def validate_catalogs(catalogs: list[AppCatalog]) -> list[str]:
    errors: list[str] = []
    seen_apps: set[str] = set()
    seen_rules: dict[str, str] = {}
    seen_matches: dict[tuple[str, str], tuple[str, str]] = {}

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
            if not isinstance(data["rules"], list) or not data["rules"]:
                raise ValidationError(f"{path}: rules must be a non-empty array")
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
                        "section",
                        "match",
                        "action",
                        "purpose",
                        "risk",
                        "source_status",
                        "device_status",
                        "mitm_hosts",
                        "match_examples",
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
                if rule["section"] not in SECTIONS:
                    raise ValidationError(f"{context}: invalid section")
                if rule["source_status"] not in {"supported", "candidate", "retired"}:
                    raise ValidationError(f"{context}: invalid source_status")
                if rule["device_status"] not in {"unverified", "passed", "failed", "stale"}:
                    raise ValidationError(f"{context}: invalid device_status")
                if rule["risk"] not in {"low", "medium", "high"}:
                    raise ValidationError(f"{context}: invalid risk")
                _validate_evidence(rule, context)
                _validate_mitm_hosts(rule, context)
                _validate_match(rule, context)

                if rule["section"] == "URL Rewrite":
                    if rule["action"] not in REWRITE_ACTIONS:
                        raise ValidationError(f"{context}: unsupported rewrite action")
                else:
                    if rule["action"] not in SCRIPT_ACTIONS:
                        raise ValidationError(f"{context}: unsupported script action")
                    _require(
                        rule,
                        ("script_name", "script_path", "requires_body", "max_size"),
                        context,
                    )
                    script_name = rule["script_name"]
                    if (
                        not isinstance(script_name, str)
                        or not script_name.strip()
                        or any(token in script_name for token in ("=", ",", "\n", "\r"))
                    ):
                        raise ValidationError(f"{context}: invalid script_name")
                    if not str(rule["script_path"]).startswith(OWNED_SCRIPT_PREFIX):
                        raise ValidationError(
                            f"{context}: script_path must use the owned runtime directory"
                        )
                    if rule["requires_body"] is not True:
                        raise ValidationError(f"{context}: response script requires body")
                    if (
                        not isinstance(rule["max_size"], int)
                        or isinstance(rule["max_size"], bool)
                        or rule["max_size"] <= 0
                    ):
                        raise ValidationError(
                            f"{context}: max_size must be a positive integer"
                        )

                signature = (rule["section"], rule["match"])
                previous = seen_matches.get(signature)
                if previous:
                    detail = "conflicts with" if previous[1] != rule["action"] else "duplicates"
                    raise ValidationError(
                        f"{context}: {detail} {previous[0]} for the same match"
                    )
                seen_matches[signature] = (rule_id, rule["action"])
            except (ValidationError, re.error) as exc:
                errors.append(str(exc))

    missing_apps = set(APP_ORDER) - seen_apps
    extra_apps = seen_apps - set(APP_ORDER)
    if missing_apps:
        errors.append(f"missing app catalogs: {', '.join(sorted(missing_apps))}")
    if extra_apps:
        errors.append(f"unknown app catalogs: {', '.join(sorted(extra_apps))}")
    return errors


def _header(name: str, rule_count: int) -> list[str]:
    return [
        f"#!name=NoAd - {name} (App-specific / MITM Required)",
        "#!desc=仅处理目标 App 的精确 HTTPS 广告接口；通用广告请直接引用上游规则集",
        "#!author=cgbzhangyu",
        "#!homepage=https://github.com/cgbzhangyu/NoAd",
        "#!category=广告拦截",
        "#!system=ios",
        f"#!rule-count={rule_count}",
        "",
    ]


def render_module(name: str, rules: list[dict[str, Any]]) -> str:
    lines = _header(name, len(rules))
    lines.extend(
        [
            "# WARNING: 本模块需要 HTTPS 解密和系统信任 Shadowrocket CA。",
            "# 仅解密下方 [MITM] 中列出的目标 App 主机。",
        ]
    )
    rewrites = [rule for rule in rules if rule["section"] == "URL Rewrite"]
    scripts = [rule for rule in rules if rule["section"] == "Script"]
    if rewrites:
        lines.extend(["", "[URL Rewrite]"])
        for rule in rewrites:
            lines.append(
                f"# {rule['id']} | {rule['purpose']} | risk={rule['risk']} | device={rule['device_status']}"
            )
            lines.append(f"{rule['match']} - {rule['action']}")
    if scripts:
        lines.extend(["", "[Script]"])
        for rule in scripts:
            lines.append(
                f"# {rule['id']} | {rule['purpose']} | risk={rule['risk']} | device={rule['device_status']}"
            )
            lines.append(
                f"{rule['script_name']} = type={rule['action']},"
                f"requires-body={1 if rule['requires_body'] else 0},"
                f"max-size={rule['max_size']},pattern={rule['match']},"
                f"script-path={rule['script_path']}"
            )
    hosts = sorted({host for rule in rules for host in rule["mitm_hosts"]})
    lines.extend(["", "[MITM]", f"hostname = %APPEND% {','.join(hosts)}"])
    return "\n".join(lines).rstrip() + "\n"


def build_outputs(catalogs: list[AppCatalog]) -> dict[Path, str]:
    by_id = {catalog.app_id: catalog for catalog in catalogs}
    return {
        DIST_DIR / f"{app_id}.sgmodule": render_module(
            by_id[app_id].name, by_id[app_id].rules
        )
        for app_id in APP_ORDER
    }


def validate_module_text(path: Path, content: str) -> list[str]:
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
            if current_section not in {"URL Rewrite", "Script", "MITM"}:
                errors.append(f"{path}:{number}: unsupported section {current_section}")
            if current_section in seen_sections:
                errors.append(f"{path}:{number}: duplicate section {current_section}")
            seen_sections.add(current_section)
            continue
        if current_section == "URL Rewrite":
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
        elif current_section == "Script":
            script_match = re.fullmatch(
                r"([^=,]+) = type=(http-response),requires-body=1,max-size=(\d+),"
                r"pattern=(.+),script-path=(https://\S+)",
                line,
            )
            if not script_match:
                errors.append(f"{path}:{number}: invalid Script line")
                continue
            _, action, max_size, pattern, script_path = script_match.groups()
            if action not in SCRIPT_ACTIONS:
                errors.append(f"{path}:{number}: invalid script action {action}")
            if int(max_size) <= 0:
                errors.append(f"{path}:{number}: invalid script max-size")
            if not script_path.startswith(OWNED_SCRIPT_PREFIX):
                errors.append(f"{path}:{number}: unowned script path")
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{path}:{number}: invalid script regex: {exc}")
        elif current_section == "MITM":
            if not line.startswith("hostname = %APPEND% "):
                errors.append(f"{path}:{number}: invalid MITM declaration")
        else:
            errors.append(f"{path}:{number}: content outside a section")
    if not ({"URL Rewrite", "Script"} & seen_sections):
        errors.append(f"{path}: missing [URL Rewrite] or [Script]")
    if "MITM" not in seen_sections:
        errors.append(f"{path}: app module requires [MITM]")
    if "[Rule]" in content or "RULE-SET," in content or "DOMAIN-SET," in content:
        errors.append(f"{path}: app module must not embed general rule sets")
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
    if DIST_DIR.exists():
        for path in DIST_DIR.glob("*.sgmodule"):
            if path not in expected_paths:
                if check:
                    mismatches.append(str(path.relative_to(ROOT)))
                else:
                    path.unlink()
    return sorted(set(mismatches))


def audit_sources(output: Path) -> int:
    data = read_json(SOURCES_FILE)
    results: list[dict[str, Any]] = []
    changed = False
    failed = False
    for source in data["sources"]:
        result = {"id": source["id"], "url": source["url"], "status": "unknown"}
        try:
            request = urllib.request.Request(
                source["url"], headers={"User-Agent": "NoAd-source-audit/0.2"}
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
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if changed:
        return 2
    return 1 if failed else 0


def command_validate() -> int:
    catalogs = load_catalogs()
    errors = validate_catalogs(catalogs)
    if not errors:
        for path, content in build_outputs(catalogs).items():
            errors.extend(validate_module_text(path, content))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Validated {sum(len(item.rules) for item in catalogs)} app-specific rules "
        f"across {len(catalogs)} apps."
    )
    return 0


def command_build(check: bool) -> int:
    catalogs = load_catalogs()
    errors = validate_catalogs(catalogs)
    outputs = build_outputs(catalogs) if not errors else {}
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
    print(f"{verb} {len(outputs)} app-specific Shadowrocket modules.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate app-specific rule catalogs")
    build = subparsers.add_parser("build", help="build deterministic app modules")
    build.add_argument("--check", action="store_true", help="check outputs without writing")
    audit = subparsers.add_parser("audit-sources", help="download and hash source material")
    audit.add_argument("--output", type=Path, default=ROOT / "source-audit.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return command_validate()
    if args.command == "build":
        return command_build(args.check)
    if args.command == "audit-sources":
        return audit_sources(args.output)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
