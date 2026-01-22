from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .approval import approval_matches
from .doc_tools import extract_pdf_text
from .fs_tools import (
    apply_write_file,
    list_dir,
    move_path,
    propose_write_file,
    read_text,
    rename_path,
)
from .plan import build_preview, compute_plan_hash
from .policy import CoworkerPolicy, validate_plan
from .registry import ToolRegistry
from .run_state import build_state, completed_ids_from_state
from .web_tools import fetch_url


class PlanValidationError(Exception):
    pass


class ApprovalError(Exception):
    pass


def preview_plan(
    plan: Dict[str, Any],
    policy: CoworkerPolicy,
    registry: ToolRegistry,
    *,
    include_diffs: bool = False,
) -> List[str]:
    errors = validate_plan(plan, policy, registry)
    if errors:
        raise PlanValidationError("\n".join(errors))
    lines = build_preview(plan)
    if include_diffs:
        lines.extend(_collect_diffs(plan, max_bytes=policy.max_read_bytes))
    return lines


def apply_plan(
    plan: Dict[str, Any],
    policy: CoworkerPolicy,
    registry: ToolRegistry,
    *,
    approval: Dict[str, Any] | None,
) -> List[str]:
    results, _state = apply_plan_with_state(
        plan,
        policy,
        registry,
        approval=approval,
        resume_state=None,
        stop_at_checkpoints=False,
    )
    return results


def apply_plan_with_state(
    plan: Dict[str, Any],
    policy: CoworkerPolicy,
    registry: ToolRegistry,
    *,
    approval: Dict[str, Any] | None,
    resume_state: Optional[Dict[str, Any]],
    stop_at_checkpoints: bool,
) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    errors = validate_plan(plan, policy, registry)
    if errors:
        raise PlanValidationError("\n".join(errors))
    plan_hash = compute_plan_hash(plan)
    completed_ids = set(completed_ids_from_state(resume_state or {}))
    if resume_state and resume_state.get("plan_hash") != plan_hash:
        raise PlanValidationError("Resume state does not match plan hash.")
    checkpoints = plan.get("checkpoints", [])
    checkpoint_ids = [str(item) for item in checkpoints if isinstance(item, (str, int))]
    next_checkpoint = _next_checkpoint(checkpoint_ids, completed_ids)
    if policy.require_approval:
        if not approval:
            raise ApprovalError("Approval required but not provided.")
        if stop_at_checkpoints and checkpoint_ids:
            if next_checkpoint:
                if not approval_matches(plan_hash, approval, checkpoint_id=next_checkpoint):
                    raise ApprovalError("Approval does not match checkpoint.")
            elif not approval_matches(plan_hash, approval):
                raise ApprovalError("Approval does not match plan hash.")
        elif not approval_matches(plan_hash, approval):
            raise ApprovalError("Approval does not match plan hash.")
    results: List[str] = []
    tool_calls = plan.get("tool_calls", [])
    for idx, call in enumerate(tool_calls):
        call_id = str(call.get("id", ""))
        if call_id and call_id in completed_ids:
            continue
        tool = call.get("tool")
        args = call.get("args", {})
        if tool == "fs.apply_write_file":
            path = Path(args["path"]).expanduser().resolve()
            if path.exists():
                raise PlanValidationError(
                    "fs.apply_write_file cannot overwrite existing file in v1"
                )
            apply_write_file(path, args["content"])
            results.append(f"wrote:{path}")
        elif tool == "fs.move":
            src = Path(args["path"]).expanduser().resolve()
            dst = Path(args["dst"]).expanduser().resolve()
            if dst.exists():
                raise PlanValidationError("fs.move cannot overwrite existing file in v1")
            move_path(src, dst)
            results.append(f"moved:{src}->{dst}")
            results.append(f"rollback:{dst}->{src}")
        elif tool == "fs.rename":
            src = Path(args["path"]).expanduser().resolve()
            dst = Path(args["dst"]).expanduser().resolve()
            if dst.exists():
                raise PlanValidationError("fs.rename cannot overwrite existing file in v1")
            rename_path(src, dst)
            results.append(f"renamed:{src}->{dst}")
            results.append(f"rollback:{dst}->{src}")
        elif tool == "fs.propose_write_file":
            path = Path(args["path"]).expanduser().resolve()
            diff = propose_write_file(
                path,
                args.get("content", ""),
                max_bytes=policy.max_read_bytes,
            )
            if diff:
                results.append(f"diff:{path}")
        elif tool == "fs.read_text":
            path = Path(args["path"]).expanduser().resolve()
            content = read_text(path, int(args.get("max_bytes", policy.max_read_bytes)))
            results.append(f"read:{path} chars={len(content)}")
        elif tool == "fs.list_dir":
            path = Path(args["path"]).expanduser().resolve()
            entries = list_dir(path)
            results.append(f"list:{path} entries={len(entries)}")
        elif tool == "doc.extract_pdf_text":
            path = Path(args["path"]).expanduser().resolve()
            ocr_mode = str(args.get("ocr_mode", "off"))
            text = extract_pdf_text(
                path,
                int(args.get("max_chars", policy.max_read_bytes)),
                ocr_mode=ocr_mode,
            )
            results.append(f"extract_pdf:{path} chars={len(text)}")
        elif tool == "web.fetch":
            url = str(args["url"])
            allowlist = list(args.get("allowlist", []))
            max_bytes = int(args.get("max_bytes", policy.max_web_bytes))
            body, content_type = fetch_url(url, max_bytes=max_bytes, allowlist=allowlist)
            results.append(f"web:{url} bytes={len(body.encode('utf-8'))} type={content_type}")
        else:
            results.append(f"skipped:{tool}")
        if call_id:
            completed_ids.add(call_id)
        if stop_at_checkpoints and call_id and call_id in checkpoint_ids:
            if idx == len(tool_calls) - 1:
                continue
            state = build_state(
                plan_hash=plan_hash,
                completed_ids=sorted(completed_ids),
                next_checkpoint=_next_checkpoint(checkpoint_ids, completed_ids),
            )
            return results, state
    return results, None


def _next_checkpoint(checkpoints: Iterable[str], completed_ids: set[str]) -> Optional[str]:
    for checkpoint in checkpoints:
        if checkpoint not in completed_ids:
            return checkpoint
    return None


def _collect_diffs(plan: Dict[str, Any], *, max_bytes: int) -> List[str]:
    lines: List[str] = []
    for call in plan.get("tool_calls", []):
        if call.get("tool") != "fs.propose_write_file":
            continue
        args = call.get("args", {})
        path = Path(args["path"]).expanduser().resolve()
        diff = propose_write_file(path, args.get("content", ""), max_bytes=max_bytes)
        if diff:
            lines.append("")
            lines.append(f"Diff for {path}:")
            lines.append(diff)
    return lines
