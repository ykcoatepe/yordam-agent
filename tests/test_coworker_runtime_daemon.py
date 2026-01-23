import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.plan import compute_plan_hash  # noqa: E402
from yordam_agent.coworker_runtime.daemon import (  # noqa: E402
    _claim_waiting_task,
    _run_task,
    run_once,
)
from yordam_agent.coworker_runtime.locks import LockHandle, acquire_locks  # noqa: E402
from yordam_agent.coworker_runtime.task_bundle import (  # noqa: E402
    ensure_task_bundle,
    update_task_snapshot,
)
from yordam_agent.coworker_runtime.task_store import TaskStore  # noqa: E402


class TestCoworkerRuntimeDaemon(unittest.TestCase):
    def test_claim_waiting_task_ignores_checkpoint_approval_without_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task = store.create_task(
                plan_hash="sha256:test",
                plan_path=Path("/tmp/plan.json"),
                bundle_path=Path("/tmp/bundle"),
            )
            store.update_task_state(task.id, state="waiting_approval")
            store.record_approval(
                plan_hash="sha256:test",
                checkpoint_id="cp-final",
                approved_by="tester",
            )

            claimed = _claim_waiting_task(store, worker_id="worker-1")
            self.assertIsNone(claimed)

            store.record_approval(plan_hash="sha256:test", approved_by="tester")
            claimed = _claim_waiting_task(store, worker_id="worker-1")
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, task.id)
            self.assertEqual(claimed.state, "running")

            store.close()

    def test_claim_waiting_task_paginates_waiting_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            tasks = []
            for idx in range(55):
                task = store.create_task(
                    plan_hash=f"sha256:{idx}",
                    plan_path=Path(f"/tmp/plan-{idx}.json"),
                    bundle_path=Path(f"/tmp/bundle-{idx}"),
                )
                store.update_task_state(task.id, state="waiting_approval")
                tasks.append(task)

            base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            with store._conn:
                for idx, task in enumerate(tasks):
                    created_at = base_time + timedelta(seconds=idx)
                    store._conn.execute(
                        "UPDATE tasks SET created_at = ?, updated_at = ? WHERE id = ?",
                        (created_at.isoformat(), created_at.isoformat(), task.id),
                    )

            store.record_approval(plan_hash=tasks[0].plan_hash, approved_by="tester")
            claimed = _claim_waiting_task(store, worker_id="worker-1")
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, tasks[0].id)

            store.close()

    def test_run_once_prefers_waiting_task_when_lock_busy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_path = root / "note.txt"
            selected_path.write_text("hello", encoding="utf-8")
            waiting_plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(selected_path)}}
                ],
            }
            queued_plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(selected_path)}}
                ],
            }
            waiting_path = root / "waiting.json"
            queued_path = root / "queued.json"
            waiting_path.write_text(json.dumps(waiting_plan), encoding="utf-8")
            queued_path.write_text(json.dumps(queued_plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            waiting_task = store.create_task(
                plan_hash=compute_plan_hash(waiting_plan),
                plan_path=waiting_path,
                bundle_path=root / "bundle-waiting",
                metadata={"selected_paths": [str(selected_path)]},
                state="waiting_approval",
            )
            queued_task = store.create_task(
                plan_hash=compute_plan_hash(queued_plan),
                plan_path=queued_path,
                bundle_path=root / "bundle-queued",
                metadata={"selected_paths": [str(selected_path)]},
                state="queued",
            )
            store.record_approval(plan_hash=waiting_task.plan_hash, approved_by="tester")
            acquire_locks(
                [selected_path],
                locks_dir=store.db_path.parent / "locks",
                task_id=waiting_task.id,
                owner="worker-1",
            )

            result = run_once(store, worker_id="worker-1")
            self.assertIsNotNone(result.task)
            self.assertEqual(result.task.id, waiting_task.id)
            self.assertEqual(store.get_task(queued_task.id).state, "queued")

            store.close()

    def test_lock_busy_updates_bundle_snapshot_to_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_path = root / "note.txt"
            selected_path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(selected_path)}}
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=compute_plan_hash(plan),
                plan_path=plan_path,
                bundle_path=root / "bundle",
                metadata={"selected_paths": [str(selected_path)]},
                state="queued",
            )
            bundle_paths = ensure_task_bundle(
                Path(task.bundle_path),
                task_id=task.id,
                plan=plan,
                metadata=task.metadata,
            )
            update_task_snapshot(
                bundle_paths,
                task_id=task.id,
                plan_hash=task.plan_hash,
                state="running",
                metadata=task.metadata,
            )
            blocking_lock = acquire_locks(
                [selected_path],
                locks_dir=store.db_path.parent / "locks",
                task_id="blocking",
                owner="worker-blocking",
            )

            result = run_once(store, worker_id="worker-1")
            self.assertIsNotNone(result.task)
            self.assertEqual(result.task.id, task.id)
            self.assertEqual(store.get_task(task.id).state, "queued")

            snapshot = json.loads((Path(task.bundle_path) / "task.json").read_text("utf-8"))
            self.assertEqual(snapshot["state"], "queued")

            blocking_lock.release()
            store.close()

    def test_run_task_loads_plan_from_bundle_when_original_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_path = root / "note.txt"
            selected_path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "created_at": "20260101T000000Z",
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(selected_path)}}
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=compute_plan_hash(plan),
                plan_path=plan_path,
                bundle_path=root / "bundle",
                metadata={"selected_paths": [str(selected_path)]},
            )
            ensure_task_bundle(
                Path(task.bundle_path),
                task_id=task.id,
                plan=plan,
                metadata=task.metadata,
            )
            plan_path.unlink()
            store.record_approval(plan_hash=task.plan_hash, approved_by="tester")

            processed = _run_task(task, store=store, worker_id="worker-1")
            self.assertTrue(processed)
            self.assertEqual(store.get_task(task.id).state, "completed")

            store.close()

    def test_run_task_honors_cancellation_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            bundle_path = root / "bundle"
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {}},
                ],
            }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            plan_hash = compute_plan_hash(plan)
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=plan_hash,
                plan_path=plan_path,
                bundle_path=bundle_path,
            )
            store.record_approval(plan_hash=plan_hash, approved_by="tester")

            def _fake_apply_plan_with_state(*_args, **_kwargs):
                store.update_task_state(
                    task.id, state="canceled", error="canceled by test", clear_lock=True
                )
                return [], None

            with patch(
                "yordam_agent.coworker_runtime.daemon.apply_plan_with_state",
                side_effect=_fake_apply_plan_with_state,
            ):
                _run_task(task, store=store, worker_id="worker-1")

            self.assertEqual(store.get_task(task.id).state, "canceled")
            store.close()

    def test_run_task_locks_state_dir_when_paths_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = {"version": 1, "tool_calls": []}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=compute_plan_hash(plan),
                plan_path=plan_path,
                bundle_path=root / "bundle",
            )
            store.record_approval(plan_hash=task.plan_hash, approved_by="tester")
            captured: dict[str, list[Path]] = {}

            def _fake_acquire(paths, *, locks_dir, task_id, owner):
                captured["paths"] = list(paths)
                return LockHandle(paths=list(paths), lock_files=[locks_dir / "fake.lock"])

            with patch(
                "yordam_agent.coworker_runtime.daemon.acquire_locks",
                side_effect=_fake_acquire,
            ), patch(
                "yordam_agent.coworker_runtime.daemon.apply_plan_with_state",
                return_value=([], None),
            ):
                processed = _run_task(task, store=store, worker_id="worker-1")

            self.assertTrue(processed)
            self.assertEqual(captured["paths"], [store.db_path.parent])
            store.close()

    def test_run_task_uses_allowed_roots_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed_root = root / "allowed"
            allowed_root.mkdir()
            plan = {"version": 1, "tool_calls": []}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=compute_plan_hash(plan),
                plan_path=plan_path,
                bundle_path=root / "bundle",
                metadata={"allowed_roots": [str(allowed_root)]},
            )
            store.record_approval(plan_hash=task.plan_hash, approved_by="tester")
            captured: dict[str, list[Path]] = {}

            def _fake_acquire(paths, *, locks_dir, task_id, owner):
                captured["paths"] = list(paths)
                return LockHandle(paths=list(paths), lock_files=[locks_dir / "fake.lock"])

            with patch(
                "yordam_agent.coworker_runtime.daemon.acquire_locks",
                side_effect=_fake_acquire,
            ), patch(
                "yordam_agent.coworker_runtime.daemon.apply_plan_with_state",
                return_value=([], None),
            ):
                processed = _run_task(task, store=store, worker_id="worker-1")

            self.assertTrue(processed)
            self.assertEqual(captured["paths"], [allowed_root.resolve()])
            store.close()

    def test_run_task_locks_parent_directory_for_selected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_path = root / "note.txt"
            selected_path.write_text("hello", encoding="utf-8")
            plan = {"version": 1, "tool_calls": []}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            store = TaskStore(root / "tasks.db")
            task = store.create_task(
                plan_hash=compute_plan_hash(plan),
                plan_path=plan_path,
                bundle_path=root / "bundle",
                metadata={"selected_paths": [str(selected_path)]},
            )
            store.record_approval(plan_hash=task.plan_hash, approved_by="tester")
            captured: dict[str, list[Path]] = {}

            def _fake_acquire(paths, *, locks_dir, task_id, owner):
                captured["paths"] = list(paths)
                return LockHandle(paths=list(paths), lock_files=[locks_dir / "fake.lock"])

            with patch(
                "yordam_agent.coworker_runtime.daemon.acquire_locks",
                side_effect=_fake_acquire,
            ), patch(
                "yordam_agent.coworker_runtime.daemon.apply_plan_with_state",
                return_value=([], None),
            ):
                processed = _run_task(task, store=store, worker_id="worker-1")

            self.assertTrue(processed)
            self.assertEqual(captured["paths"], [selected_path.parent.resolve()])
            store.close()


if __name__ == "__main__":
    unittest.main()
