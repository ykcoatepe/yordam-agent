import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def build_approval(
    plan_hash: str,
    approved_by: Optional[str] = None,
    checkpoint_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "plan_hash": plan_hash,
        "approved_at": _utc_now(),
    }
    if approved_by:
        payload["approved_by"] = approved_by
    if checkpoint_id:
        payload["checkpoint_id"] = checkpoint_id
    return payload


def load_approval(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_approval(path: Path, approval: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, indent=2), encoding="utf-8")
    return path


def approval_matches(
    plan_hash: str, approval: Dict[str, Any], checkpoint_id: Optional[str] = None
) -> bool:
    if approval.get("plan_hash") != plan_hash:
        return False
    approval_checkpoint = approval.get("checkpoint_id")
    if checkpoint_id is None:
        return approval_checkpoint in (None, "")
    return approval_checkpoint == checkpoint_id


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
