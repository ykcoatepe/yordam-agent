import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_POLICY: Dict[str, Any] = {
    "ignore_patterns": [],
    "extension_overrides": {},
    "type_group_overrides": {},
    "name_contains_rules": [],
}


def load_policy(path: Path) -> Dict[str, Any]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_POLICY, indent=2), encoding="utf-8")
    raw = json.loads(path.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_POLICY)
    merged.update(raw)
    if merged != raw:
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
