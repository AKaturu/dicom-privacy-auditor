from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import (
    TABLE_OPTIONS,
    AttributeRule,
    CodeRule,
    CodeRuleResolution,
    PolicySelection,
    ProfileOption,
    RuleResolution,
)

DEFAULT_EDITION = "2026c"
DATA_DIR_ENV = "DICOM_PRIVACY_PS315_DATA_DIR"
EDITION_ENV = "DICOM_PRIVACY_PS315_EDITION"


class StandardsDataNotInstalledError(RuntimeError):
    """Raised when user-generated PS3.15 tables are not available locally."""


def default_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "DICOMPrivacyAuditor" / "ps315"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DICOMPrivacyAuditor" / "ps315"
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "dicom-privacy-auditor" / "ps315"


def selected_edition() -> str:
    return os.environ.get(EDITION_ENV, DEFAULT_EDITION)


def table_paths(*, data_dir: str | Path | None = None, edition: str | None = None) -> tuple[Path, Path]:
    directory = Path(data_dir).expanduser().resolve() if data_dir else default_data_dir()
    selected = edition or selected_edition()
    return (
        directory / f"ps315_{selected}_table_e1_1.json",
        directory / f"ps315_{selected}_table_e1_2.json",
    )


def data_status(*, data_dir: str | Path | None = None, edition: str | None = None) -> dict[str, Any]:
    attribute_path, code_path = table_paths(data_dir=data_dir, edition=edition)
    return {
        "installed": attribute_path.is_file() and code_path.is_file(),
        "edition": edition or selected_edition(),
        "data_dir": str(attribute_path.parent),
        "attribute_table": str(attribute_path),
        "attribute_table_present": attribute_path.is_file(),
        "code_table": str(code_path),
        "code_table_present": code_path.is_file(),
        "bundled_with_project": False,
        "setup": (
            "Run 'dicom-privacy-ps315 --edition <edition> prepare-data --download' or provide "
            "an official local DOCX with '--source /path/to/part15.docx'."
        ),
    }


def _missing_error() -> StandardsDataNotInstalledError:
    status = data_status()
    return StandardsDataNotInstalledError(
        "DICOM PS3.15 rule data is not installed. The project intentionally does not redistribute "
        "the DICOM Standard or complete extracted tables. "
        + status["setup"]
        + f" Data directory: {status['data_dir']}"
    )


@lru_cache(maxsize=8)
def _read_payload(path_text: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns  # cache-key component
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


def _load_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise _missing_error()
    return _read_payload(str(path), path.stat().st_mtime_ns)


def load_table() -> dict[str, Any]:
    return _load_path(table_paths()[0])


def load_code_table() -> dict[str, Any]:
    return _load_path(table_paths()[1])


def clear_caches() -> None:
    _read_payload.cache_clear()
    all_code_rules.cache_clear()
    code_rule_index.cache_clear()
    all_rules.cache_clear()
    rules_by_tag.cache_clear()


@lru_cache(maxsize=1)
def all_code_rules() -> tuple[CodeRule, ...]:
    supported = {
        ProfileOption.RETAIN_UIDS,
        ProfileOption.RETAIN_DEVICE_IDENTITY,
        ProfileOption.RETAIN_INSTITUTION_IDENTITY,
        ProfileOption.RETAIN_PATIENT_CHARACTERISTICS,
        ProfileOption.RETAIN_LONGITUDINAL_FULL_DATES,
        ProfileOption.RETAIN_LONGITUDINAL_MODIFIED_DATES,
        ProfileOption.CLEAN_DESCRIPTORS,
    }
    output: list[CodeRule] = []
    for row in load_code_table()["rules"]:
        actions = {
            "basic_profile": row["basic_profile"],
            **{option.value: row.get(option.value, "") for option in supported},
        }
        output.append(
            CodeRule(
                code_meaning=row["code_meaning"],
                code_value=row["code_value"],
                coding_scheme_designator=row["coding_scheme_designator"],
                value_type=row["value_type"],
                retired=row["retired"] == "Y",
                standard_template=row["standard_template"] == "Y",
                actions=actions,
            )
        )
    return tuple(output)


@lru_cache(maxsize=1)
def code_rule_index() -> dict[tuple[str, str, str], CodeRule]:
    return {
        (rule.coding_scheme_designator, rule.code_value, rule.value_type): rule for rule in all_code_rules()
    }


def get_code_rule(coding_scheme_designator: str, code_value: str, value_type: str) -> CodeRule | None:
    return code_rule_index().get((str(coding_scheme_designator), str(code_value), str(value_type)))


def resolve_code_rule(rule: CodeRule, selection: PolicySelection) -> CodeRuleResolution:
    overrides: list[tuple[str, str]] = []
    for option in selection.options:
        action = rule.actions.get(option.value, "")
        if action:
            overrides.append((option.value, action))
    active = overrides or [("basic_profile", rule.actions["basic_profile"])]
    directives = tuple(action for _, action in active)
    return CodeRuleResolution(
        rule=rule,
        directives=directives,
        directive_sources=tuple(source for source, _ in active),
        conflicts=len(set(directives)) > 1,
    )


@lru_cache(maxsize=1)
def all_rules() -> tuple[AttributeRule, ...]:
    rules: list[AttributeRule] = []
    for row in load_table()["rules"]:
        actions = {
            "basic_profile": row["basic_profile"],
            **{option.value: row.get(option.value, "") for option in TABLE_OPTIONS},
        }
        rules.append(
            AttributeRule(
                name=row["name"],
                tag=row["tag"],
                tag_hex=row.get("tag_hex"),
                retired=row["retired"] == "Y",
                standard_composite_iod=row["standard_composite_iod"] == "Y",
                actions=actions,
            )
        )
    return tuple(rules)


@lru_cache(maxsize=1)
def rules_by_tag() -> dict[str, AttributeRule]:
    return {rule.tag_hex: rule for rule in all_rules() if rule.tag_hex}


def normalize_tag(tag: str | int) -> str:
    if isinstance(tag, int):
        return f"{tag:08X}"
    return str(tag).replace("(", "").replace(")", "").replace(",", "").replace(" ", "").upper()


def get_rule(tag: str | int) -> AttributeRule | None:
    normalized = normalize_tag(tag)
    if len(normalized) == 8 and all(ch in "0123456789ABCDEF" for ch in normalized):
        return rules_by_tag().get(normalized)
    if normalized == "GGGGEEEEWHEREGGGGISODD":
        return next(rule for rule in all_rules() if rule.name == "Private Attributes")
    return None


def private_rule() -> AttributeRule:
    return next(rule for rule in all_rules() if rule.name == "Private Attributes")


def resolve_rule(rule: AttributeRule, selection: PolicySelection) -> RuleResolution:
    overrides: list[tuple[str, str]] = []
    for option in selection.options:
        if option not in TABLE_OPTIONS:
            continue
        action = rule.actions.get(option.value, "")
        if action:
            overrides.append((option.value, action))
    active = overrides or [("basic_profile", rule.actions["basic_profile"])]
    directives = tuple(action for _, action in active)
    sources = tuple(source for source, _ in active)
    conflicts = len(set(directives)) > 1
    return RuleResolution(rule=rule, directives=directives, directive_sources=sources, conflicts=conflicts)


def rule_for_dataset_tag(tag_int: int, selection: PolicySelection) -> RuleResolution | None:
    group = (tag_int >> 16) & 0xFFFF
    normalized = normalize_tag(tag_int)
    if group % 2 == 1:
        rule = private_rule()
        if (
            ProfileOption.RETAIN_SAFE_PRIVATE in selection.options
            and normalized in selection.safe_private_tags
        ):
            custom = AttributeRule(
                name="Allow-listed Safe Private Attribute",
                tag=f"({normalized[:4]},{normalized[4:]})",
                tag_hex=normalized,
                retired=False,
                standard_composite_iod=False,
                actions={**rule.actions, ProfileOption.RETAIN_SAFE_PRIVATE.value: "K"},
            )
            return resolve_rule(custom, selection)
        return resolve_rule(rule, selection)
    standard_rule = get_rule(tag_int)
    return resolve_rule(standard_rule, selection) if standard_rule else None


def table_metadata() -> dict[str, Any]:
    payload = load_table()
    code_payload = load_code_table()
    metadata = {
        key: payload.get(key)
        for key in (
            "standard",
            "edition",
            "table",
            "title",
            "source_url",
            "source_sha256",
            "row_count",
            "generated_locally",
            "redistributed_by_project",
            "rights_notice",
        )
    }
    metadata["code_table"] = code_payload["table"]
    metadata["code_table_title"] = code_payload["title"]
    metadata["code_rule_count"] = code_payload["row_count"]
    metadata["data_dir"] = str(table_paths()[0].parent)
    return metadata
