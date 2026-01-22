from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import load_config
from ..coworker.executor import ApprovalError, PlanValidationError, apply_plan_with_state
from ..coworker.plan import ensure_plan_hash, load_plan
from ..coworker.policy import policy_from_config
from ..coworker.registry import DEFAULT_REGISTRY
from ..coworker.run_state import load_state, write_state
from .locks import LockHandle, acquire_locks
from .task_bundle import append_event, ensure_task_bundle, update_task_snapshot
from .task_store import TaskRecord, TaskStore


@dataclass(frozen=True)
class DaemonResult:
    task: Optional[TaskRecord]
    message: str


def run_once(store: TaskStore, *, worker_id: str) -> DaemonResult:
    task = store.claim_next_task(worker_id=worker_id)
    if task is None:
        task = _claim_waiting_task(store, worker_id=worker_id)
        if task is None:
            return DaemonResult(task=None, message="no queued tasks")
    try:
        processed = _run_task(task, store=store, worker_id=worker_id)
    except Exception as exc:  # noqa: BLE001 - daemon must not crash
        store.update_task_state(task.id, state="failed", error=str(exc), clear_lock=True)
        return DaemonResult(task=task, message=f"task failed: {exc}")
    if processed:
        return DaemonResult(task=store.get_task(task.id), message="task processed")
    waiting_task = _claim_waiting_task(store, worker_id=worker_id)
    if waiting_task is None:
        return DaemonResult(task=store.get_task(task.id), message="task deferred (locks busy)")
    try:
        waiting_processed = _run_task(waiting_task, store=store, worker_id=worker_id)
    except Exception as exc:  # noqa: BLE001 - daemon must not crash
        store.update_task_state(
            waiting_task.id, state="failed", error=str(exc), clear_lock=True
        )
        return DaemonResult(task=waiting_task, message=f"task failed: {exc}")
    message = "task processed" if waiting_processed else "task deferred (locks busy)"
    return DaemonResult(task=store.get_task(waiting_task.id), message=message)


def _run_task(task: TaskRecord, *, store: TaskStore, worker_id: str) -> bool:
    lock_handle: Optional[LockHandle] = None
    retain_lock = False
    latest = store.get_task(task.id)
    if latest.state == "canceled":
        bundle_root = Path(latest.bundle_path)
        bundle_paths = ensure_task_bundle(
            bundle_root,
            task_id=latest.id,
            plan=load_plan(_plan_path_for_task(latest)),
            metadata=latest.metadata,
        )
        append_event(
            bundle_paths,
            {"task_id": latest.id, "event": "task_canceled", "state": "canceled"},
        )
        update_task_snapshot(
            bundle_paths,
            task_id=latest.id,
            plan_hash=latest.plan_hash,
            state="canceled",
            metadata=latest.metadata,
        )
        return True
    lock_handle = _try_lock_task(task, store=store, worker_id=worker_id)
    if lock_handle is None:
        return False
    try:
        cfg = load_config()
        bundle_root = Path(task.bundle_path)
        plan = load_plan(_plan_path_for_task(task))
        plan_hash = ensure_plan_hash(plan)
        if plan_hash != task.plan_hash:
            error = "plan hash mismatch; refusing to execute"
            store.update_task_state(task.id, state="failed", error=error, clear_lock=True)
            bundle_paths = ensure_task_bundle(
                bundle_root,
                task_id=task.id,
                plan=plan,
                metadata=task.metadata,
            )
            append_event(
                bundle_paths,
                {
                    "task_id": task.id,
                    "event": "task_failed",
                    "state": "failed",
                    "error": error,
                },
            )
            update_task_snapshot(
                bundle_paths,
                task_id=task.id,
                plan_hash=plan_hash,
                state="failed",
                metadata=task.metadata,
                error=error,
            )
            return True

        selected_paths = _paths_from_metadata(task.metadata.get("selected_paths"))
        extra_roots = _paths_from_metadata(task.metadata.get("allow_roots"))
        policy = policy_from_config(cfg, selected_paths, extra_roots)

        bundle_paths = ensure_task_bundle(
            bundle_root,
            task_id=task.id,
            plan=plan,
            metadata=task.metadata,
        )

        append_event(
            bundle_paths,
            {
                "task_id": task.id,
                "event": "task_claimed",
                "state": "running",
                "metadata": {"worker_id": worker_id},
            },
        )
        update_task_snapshot(
            bundle_paths,
            task_id=task.id,
            plan_hash=plan_hash,
            state="running",
            metadata=task.metadata,
        )

        checkpoints = plan.get("checkpoints", [])
        resume_state = _load_resume_state(bundle_paths)
        checkpoint_id = _resolve_checkpoint_id(checkpoints, resume_state)

        try:
            approval = _resolve_approval(store, plan_hash, checkpoint_id)
            if policy.require_approval and approval is None:
                store.update_task_state(
                    task.id,
                    state="waiting_approval",
                    next_checkpoint=checkpoint_id,
                )
                append_event(
                    bundle_paths,
                    {
                        "task_id": task.id,
                        "event": "task_waiting_approval",
                        "state": "waiting_approval",
                        "checkpoint_id": checkpoint_id,
                    },
                )
                update_task_snapshot(
                    bundle_paths,
                    task_id=task.id,
                    plan_hash=plan_hash,
                    state="waiting_approval",
                    metadata=task.metadata,
                )
                retain_lock = True
                return True

            results, state = apply_plan_with_state(
                plan,
                policy,
                DEFAULT_REGISTRY,
                approval=approval,
                resume_state=resume_state,
                stop_at_checkpoints=bool(checkpoints) and policy.require_approval,
            )
            if state is not None:
                retain_lock = True
        except ApprovalError:
            store.update_task_state(
                task.id,
                state="waiting_approval",
                next_checkpoint=checkpoint_id,
            )
            append_event(
                bundle_paths,
                {
                    "task_id": task.id,
                    "event": "task_waiting_approval",
                    "state": "waiting_approval",
                    "checkpoint_id": checkpoint_id,
                },
            )
            update_task_snapshot(
                bundle_paths,
                task_id=task.id,
                plan_hash=plan_hash,
                state="waiting_approval",
                metadata=task.metadata,
            )
            retain_lock = True
            return True
        except PlanValidationError as exc:
            store.update_task_state(
                task.id, state="failed", error=str(exc), clear_lock=True
            )
            append_event(
                bundle_paths,
                {
                    "task_id": task.id,
                    "event": "task_failed",
                    "state": "failed",
                    "error": str(exc),
                },
            )
            update_task_snapshot(
                bundle_paths,
                task_id=task.id,
                plan_hash=plan_hash,
                state="failed",
                metadata=task.metadata,
                error=str(exc),
            )
            return True

        _emit_tool_results(bundle_paths, task_id=task.id, results=results)

        if store.get_task(task.id).state == "canceled":
            retain_lock = False
            return True

        if state is not None:
            write_state(bundle_paths.resume_state_path, state)
            store.update_task_state(
                task.id,
                state="waiting_approval",
                next_checkpoint=state.get("next_checkpoint"),
                current_step=len(state.get("completed_ids", [])),
            )
            append_event(
                bundle_paths,
                {
                    "task_id": task.id,
                    "event": "task_waiting_approval",
                    "state": "waiting_approval",
                    "checkpoint_id": state.get("next_checkpoint"),
                },
            )
            update_task_snapshot(
                bundle_paths,
                task_id=task.id,
                plan_hash=plan_hash,
                state="waiting_approval",
                metadata=task.metadata,
            )
            return True

        store.update_task_state(
            task.id,
            state="completed",
            current_step=len(plan.get("tool_calls", [])),
            clear_lock=True,
        )
        append_event(
            bundle_paths,
            {"task_id": task.id, "event": "task_completed", "state": "completed"},
        )
        update_task_snapshot(
            bundle_paths,
            task_id=task.id,
            plan_hash=plan_hash,
            state="completed",
            metadata=task.metadata,
        )
        retain_lock = False
    finally:
        if lock_handle and not retain_lock:
            lock_handle.release()
    return True


def _claim_waiting_task(store: TaskStore, *, worker_id: str) -> Optional[TaskRecord]:
    offset = 0
    limit = 50
    while True:
        candidates = store.list_tasks(state="waiting_approval", limit=limit, offset=offset)
        if not candidates:
            return None
        for task in candidates:
            checkpoint_id = task.next_checkpoint
            approval = store.latest_approval(plan_hash=task.plan_hash, checkpoint_id=checkpoint_id)
            if approval is None:
                continue
            if store.claim_task(task.id, expected_state="waiting_approval", worker_id=worker_id):
                return store.get_task(task.id)
        offset += len(candidates)
    return None


def _emit_tool_results(bundle_paths, *, task_id: str, results: Any) -> None:
    if not results:
        return
    for result in results:
        append_event(
            bundle_paths,
            {
                "task_id": task_id,
                "event": "tool_call_finished",
                "state": "running",
                "message": str(result),
            },
        )


def _resolve_checkpoint_id(
    checkpoints: Any, resume_state: Optional[Dict[str, Any]]
) -> Optional[str]:
    if resume_state:
        if "next_checkpoint" in resume_state:
            next_checkpoint = resume_state.get("next_checkpoint")
            if next_checkpoint is None:
                return None
            return str(next_checkpoint)
    if isinstance(checkpoints, list) and checkpoints:
        return str(checkpoints[0])
    return None


def _resolve_approval(
    store: TaskStore, plan_hash: str, checkpoint_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    approval = store.latest_approval(plan_hash=plan_hash, checkpoint_id=checkpoint_id)
    if approval is None:
        return None
    payload: Dict[str, Any] = {
        "plan_hash": approval.plan_hash,
        "approved_at": approval.approved_at,
        "approved_by": approval.approved_by,
    }
    if approval.checkpoint_id:
        payload["checkpoint_id"] = approval.checkpoint_id
    return payload


def _paths_from_metadata(values: Any) -> list[Path]:
    if not isinstance(values, list):
        return []
    resolved = []
    for item in values:
        try:
            resolved.append(Path(str(item)).expanduser().resolve())
        except OSError:
            continue
    return resolved


def _load_resume_state(bundle_paths) -> Optional[Dict[str, Any]]:
    if bundle_paths.resume_state_path.exists():
        return load_state(bundle_paths.resume_state_path)
    return None


def _plan_path_for_task(task: TaskRecord) -> Path:
    bundle_plan_path = Path(task.bundle_path) / "plan.json"
    if bundle_plan_path.exists():
        return bundle_plan_path
    return Path(task.plan_path)


def _try_lock_task(task: TaskRecord, *, store: TaskStore, worker_id: str) -> Optional[LockHandle]:
    selected_paths = _paths_from_metadata(task.metadata.get("selected_paths"))
    if not selected_paths:
        return LockHandle(paths=[], lock_files=[])
    locks_dir = store.db_path.parent / "locks"
    handle = acquire_locks(
        selected_paths,
        locks_dir=locks_dir,
        task_id=task.id,
        owner=worker_id,
    )
    if not handle.lock_files:
        store.update_task_state(task.id, state="queued", clear_lock=True)
        bundle_root = Path(task.bundle_path)
        bundle_paths = ensure_task_bundle(
            bundle_root,
            task_id=task.id,
            plan=load_plan(_plan_path_for_task(task)),
            metadata=task.metadata,
        )
        append_event(
            bundle_paths,
            {
                "task_id": task.id,
                "event": "task_lock_failed",
                "state": "queued",
                "message": "path locks busy",
            },
        )
        return None
    return handle
