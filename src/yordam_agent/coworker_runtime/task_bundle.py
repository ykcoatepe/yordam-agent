import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ..coworker.plan import build_preview, ensure_plan_hash, write_plan


@dataclass(frozen=True)
class TaskBundlePaths:
    root: Path
    task_path: Path
    plan_path: Path
    preview_path: Path
    events_path: Path
    resume_state_path: Path
    scratch_dir: Path
    staging_dir: Path


def bundle_paths(root: Path) -> TaskBundlePaths:
    return TaskBundlePaths(
        root=root,
        task_path=root / "task.json",
        plan_path=root / "plan.json",
        preview_path=root / "preview.txt",
        events_path=root / "events.jsonl",
        resume_state_path=root / "resume_state.json",
        scratch_dir=root / "scratch",
        staging_dir=root / "staging",
    )


def init_task_bundle(
    root: Path,
    *,
    task_id: str,
    plan: Dict[str, Any],
    preview_lines: Optional[Iterable[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskBundlePaths:
    paths = bundle_paths(root)
    root.mkdir(parents=True, exist_ok=True)
    paths.scratch_dir.mkdir(parents=True, exist_ok=True)
    paths.staging_dir.mkdir(parents=True, exist_ok=True)

    plan_hash = ensure_plan_hash(plan)
    write_plan(paths.plan_path, plan)

    if preview_lines is None:
        preview_lines = build_preview(plan)
    _write_lines(paths.preview_path, preview_lines)

    snapshot = _build_task_snapshot(
        task_id=task_id,
        plan_hash=plan_hash,
        state="queued",
        metadata=metadata,
    )
    _write_json(paths.task_path, snapshot)

    if not paths.events_path.exists():
        paths.events_path.write_text("", encoding="utf-8")

    return paths


def ensure_task_bundle(
    root: Path,
    *,
    task_id: str,
    plan: Dict[str, Any],
    preview_lines: Optional[Iterable[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskBundlePaths:
    paths = bundle_paths(root)
    if not paths.task_path.exists():
        return init_task_bundle(
            root,
            task_id=task_id,
            plan=plan,
            preview_lines=preview_lines,
            metadata=metadata,
        )
    return paths


def update_task_snapshot(
    paths: TaskBundlePaths,
    *,
    task_id: str,
    plan_hash: str,
    state: str,
    metadata: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    snapshot = _build_task_snapshot(
        task_id=task_id,
        plan_hash=plan_hash,
        state=state,
        metadata=metadata,
        error=error,
    )
    _write_json(paths.task_path, snapshot)


def append_event(paths: TaskBundlePaths, event: Dict[str, Any]) -> None:
    payload = dict(event)
    payload.setdefault("ts", _utc_now())
    paths.events_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True))
        fh.write("\n")


def _build_task_snapshot(
    *,
    task_id: str,
    plan_hash: str,
    state: str,
    metadata: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "task_id": task_id,
        "plan_hash": plan_hash,
        "state": state,
        "updated_at": _utc_now(),
    }
    if metadata:
        snapshot["metadata"] = metadata
    if error:
        snapshot["error"] = error
    return snapshot


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
