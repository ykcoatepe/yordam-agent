from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .policy import DEFAULT_POLICY


def _parse_override_value(raw: str) -> object:
    raw = raw.strip()
    if not raw:
        return ""
    if "/" in raw:
        category, subcategory = raw.split("/", 1)
        category = category.strip()
        subcategory = subcategory.strip()
        if not category:
            return ""
        if subcategory:
            return {"category": category, "subcategory": subcategory}
        return category
    return raw


def _parse_key_value_list(raw: str) -> Dict[str, object]:
    result: Dict[str, object] = {}
    if not raw:
        return result
    pairs = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        parsed = _parse_override_value(value)
        if parsed:
            result[key] = parsed
    return result


def _prompt_line(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def _prompt_ignore_patterns() -> List[str]:
    raw = _prompt_line("Ignore patterns (comma-separated, blank to skip): ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _prompt_overrides(label: str) -> Dict[str, object]:
    raw = _prompt_line(
        f"{label} overrides (key=value, comma-separated, blank to skip): "
    ).strip()
    return _parse_key_value_list(raw)


def _prompt_name_rules() -> List[Dict[str, object]]:
    rules: List[Dict[str, object]] = []
    while True:
        needle = _prompt_line("Name contains (blank to finish): ").strip()
        if not needle:
            break
        category = _prompt_line("  Category: ").strip()
        if not category:
            print("  Skipped (category required).")
            continue
        subcategory = _prompt_line("  Subcategory (optional): ").strip()
        rule: Dict[str, object] = {"contains": needle, "category": category}
        if subcategory:
            rule["subcategory"] = subcategory
        rules.append(rule)
    return rules


def _merge_policy(base: Dict[str, object], new: Dict[str, object]) -> Dict[str, object]:
    merged = dict(base)
    merged["ignore_patterns"] = list(
        dict.fromkeys(base.get("ignore_patterns", []) + new.get("ignore_patterns", []))
    )
    merged["extension_overrides"] = {
        **base.get("extension_overrides", {}),
        **new.get("extension_overrides", {}),
    }
    merged["type_group_overrides"] = {
        **base.get("type_group_overrides", {}),
        **new.get("type_group_overrides", {}),
    }
    merged["name_contains_rules"] = base.get("name_contains_rules", []) + new.get(
        "name_contains_rules", []
    )
    return merged


def run_policy_wizard(path: Path) -> Tuple[Path, bool]:
    path = path.expanduser()
    existing: Optional[Dict[str, object]] = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None

    overwrite = False
    if existing is not None:
        choice = _prompt_line("Policy exists. Overwrite? [y/N]: ").strip().lower()
        overwrite = choice.startswith("y")

    policy = dict(DEFAULT_POLICY)
    policy["ignore_patterns"] = _prompt_ignore_patterns()
    policy["extension_overrides"] = _prompt_overrides("Extension")
    policy["type_group_overrides"] = _prompt_overrides("Type group")
    policy["name_contains_rules"] = _prompt_name_rules()

    if existing and not overwrite:
        policy = _merge_policy(existing, policy)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return path, overwrite


def parse_extension_overrides(raw: str) -> Dict[str, object]:
    return _parse_key_value_list(raw)


def parse_type_overrides(raw: str) -> Dict[str, object]:
    return _parse_key_value_list(raw)
