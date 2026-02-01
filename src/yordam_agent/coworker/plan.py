import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PLAN_VERSION = 1
HASH_PREFIX = "sha256:"
WRITE_TOOLS = {"fs.apply_write_file", "fs.move", "fs.rename"}


def load_plan(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_plan(raw)
    return raw


def write_plan(path: Path, plan: Dict[str, Any]) -> Path:
    ensure_plan_fields(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return path


def ensure_plan_fields(plan: Dict[str, Any]) -> None:
    plan.setdefault("version", PLAN_VERSION)
    plan.setdefault("created_at", _utc_now())


def validate_plan(plan: Dict[str, Any]) -> None:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object.")
    if plan.get("version") != PLAN_VERSION:
        raise ValueError(f"Unsupported plan version: {plan.get('version')}")
    tool_calls = plan.get("tool_calls")
    if not isinstance(tool_calls, list):
        raise ValueError("Plan must include tool_calls list.")
    for idx, call in enumerate(tool_calls):
        if not isinstance(call, dict):
            raise ValueError(f"Tool call {idx} must be an object.")
        if not call.get("id") or not isinstance(call.get("id"), str):
            raise ValueError(f"Tool call {idx} missing id.")
        if not call.get("tool") or not isinstance(call.get("tool"), str):
            raise ValueError(f"Tool call {idx} missing tool.")
        args = call.get("args")
        if args is None:
            raise ValueError(f"Tool call {idx} missing args.")
        if not isinstance(args, dict):
            raise ValueError(f"Tool call {idx} args must be an object.")


def compute_plan_hash(plan: Dict[str, Any]) -> str:
    payload = _strip_hash_fields(plan)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{HASH_PREFIX}{digest}"


def ensure_plan_hash(plan: Dict[str, Any]) -> str:
    plan_hash = compute_plan_hash(plan)
    plan["plan_hash"] = plan_hash
    return plan_hash


def build_preview(plan: Dict[str, Any]) -> List[str]:
    tool_calls = plan.get("tool_calls", [])
    lines = [f"Tool calls: {len(tool_calls)}"]
    for call in tool_calls:
        tool = call.get("tool", "unknown")
        args = call.get("args", {})
        lines.append(_format_tool_preview(tool, args, call.get("rollback")))
    return lines


def _format_tool_preview(tool: str, args: Dict[str, Any], rollback: Any) -> str:
    if tool in {"fs.move", "fs.rename"}:
        src = args.get("path", "")
        dst = args.get("dst", "")
        line = f"- {tool}: {src} -> {dst}"
        if rollback:
            line += f" (rollback: {rollback})"
        return line
    if tool in {"fs.read_text", "fs.list_dir", "fs.propose_write_file", "fs.apply_write_file"}:
        path = args.get("path", "")
        return f"- {tool}: {path}"
    if tool == "doc.extract_pdf_text":
        return f"- {tool}: {args.get('path', '')}"
    if tool == "web.fetch":
        return f"- {tool}: {args.get('url', '')}"
    return f"- {tool}"


def auto_checkpoints(tool_calls: List[Dict[str, Any]], every: int) -> List[str]:
    if every <= 0:
        return []
    checkpoints: List[str] = []
    write_count = 0
    for call in tool_calls:
        tool = call.get("tool")
        if tool not in WRITE_TOOLS:
            continue
        call_id = str(call.get("id", "")).strip()
        if not call_id:
            continue
        write_count += 1
        if write_count % every == 0:
            checkpoints.append(call_id)
    return checkpoints


def _strip_hash_fields(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in plan.items() if key not in {"plan_hash", "approval"}}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
