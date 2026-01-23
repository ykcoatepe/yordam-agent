import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def build_state(
    *,
    plan_hash: str,
    completed_ids: Iterable[str],
    next_checkpoint: Optional[str],
) -> Dict[str, Any]:
    return {
        "plan_hash": plan_hash,
        "completed_ids": list(completed_ids),
        "next_checkpoint": next_checkpoint,
        "updated_at": _utc_now(),
    }


def load_state(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def completed_ids_from_state(state: Dict[str, Any]) -> List[str]:
    raw = state.get("completed_ids", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, (str, int))]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
