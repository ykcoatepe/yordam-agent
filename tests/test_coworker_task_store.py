import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker_runtime.task_store import (  # noqa: E402
    TaskStore,
)


class TestCoworkerTaskStore(unittest.TestCase):
    def test_task_store_migrations_and_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            self.assertEqual(store.schema_version(), 1)

            task = store.create_task(
                plan_hash="sha256:test",
                plan_path=Path("/tmp/plan.json"),
                bundle_path=Path("/tmp/bundle"),
                metadata={"source": "unit"},
            )
            self.assertEqual(task.state, "queued")
            self.assertEqual(task.metadata.get("source"), "unit")

            listed = store.list_tasks()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0].id, task.id)

            updated = store.update_task_state(task.id, state="running", current_step=2)
            self.assertEqual(updated.state, "running")
            self.assertEqual(updated.current_step, 2)

            approval = store.record_approval(
                plan_hash="sha256:test",
                checkpoint_id="cp1",
                approved_by="tester",
            )
            self.assertEqual(approval.plan_hash, "sha256:test")

            latest = store.latest_approval(plan_hash="sha256:test", checkpoint_id="cp1")
            self.assertIsNotNone(latest)
            self.assertEqual(latest.approved_by, "tester")

            latest_any = store.latest_approval_any(plan_hash="sha256:test")
            self.assertIsNotNone(latest_any)
            self.assertEqual(latest_any.approved_by, "tester")

            store.close()

    def test_claim_next_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task_one = store.create_task(
                plan_hash="sha256:a",
                plan_path=Path("/tmp/plan-a.json"),
                bundle_path=Path("/tmp/bundle-a"),
            )
            task_two = store.create_task(
                plan_hash="sha256:b",
                plan_path=Path("/tmp/plan-b.json"),
                bundle_path=Path("/tmp/bundle-b"),
            )
            claimed = store.claim_next_task(worker_id="worker-1")
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, task_one.id)
            self.assertEqual(claimed.state, "running")

            claimed_second = store.claim_next_task(worker_id="worker-1")
            self.assertIsNotNone(claimed_second)
            self.assertEqual(claimed_second.id, task_two.id)

            claimed_none = store.claim_next_task(worker_id="worker-1")
            self.assertIsNone(claimed_none)
            store.close()

    def test_requeued_task_moves_behind_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task_one = store.create_task(
                plan_hash="sha256:a",
                plan_path=Path("/tmp/plan-a.json"),
                bundle_path=Path("/tmp/bundle-a"),
            )
            task_two = store.create_task(
                plan_hash="sha256:b",
                plan_path=Path("/tmp/plan-b.json"),
                bundle_path=Path("/tmp/bundle-b"),
            )
            base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            with store._conn:
                store._conn.execute(
                    "UPDATE tasks SET updated_at = ? WHERE id = ?",
                    ((base_time - timedelta(seconds=5)).isoformat(), task_one.id),
                )
                store._conn.execute(
                    "UPDATE tasks SET updated_at = ? WHERE id = ?",
                    ((base_time - timedelta(seconds=1)).isoformat(), task_two.id),
                )

            claimed = store.claim_next_task(worker_id="worker-1")
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, task_one.id)

            store.update_task_state(task_one.id, state="queued")

            claimed_next = store.claim_next_task(worker_id="worker-1")
            self.assertIsNotNone(claimed_next)
            self.assertEqual(claimed_next.id, task_two.id)
            store.close()

    def test_store_persists_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task = store.create_task(
                plan_hash="sha256:persist",
                plan_path=Path("/tmp/plan.json"),
                bundle_path=Path("/tmp/bundle"),
            )
            store.close()

            store = TaskStore(db_path)
            reloaded = store.get_task(task.id)
            self.assertEqual(reloaded.plan_hash, "sha256:persist")
            store.close()

    def test_cancelled_task_is_not_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task = store.create_task(
                plan_hash="sha256:cancel",
                plan_path=Path("/tmp/plan.json"),
                bundle_path=Path("/tmp/bundle"),
            )
            store.update_task_state(task.id, state="canceled", error="canceled by test")
            claimed = store.claim_next_task(worker_id="worker-1")
            self.assertIsNone(claimed)
            store.close()

    def test_update_task_state_clears_next_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task = store.create_task(
                plan_hash="sha256:clear",
                plan_path=Path("/tmp/plan.json"),
                bundle_path=Path("/tmp/bundle"),
            )
            task = store.update_task_state(
                task.id, state="waiting_approval", next_checkpoint="cp-final"
            )
            self.assertEqual(task.next_checkpoint, "cp-final")

            task = store.update_task_state(task.id, state="waiting_approval", next_checkpoint=None)
            self.assertIsNone(task.next_checkpoint)
            store.close()

    def test_count_tasks_by_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "tasks.db"
            store = TaskStore(db_path)
            task_one = store.create_task(
                plan_hash="sha256:a",
                plan_path=Path("/tmp/plan-a.json"),
                bundle_path=Path("/tmp/bundle-a"),
            )
            task_two = store.create_task(
                plan_hash="sha256:b",
                plan_path=Path("/tmp/plan-b.json"),
                bundle_path=Path("/tmp/bundle-b"),
            )
            store.update_task_state(task_one.id, state="running")
            store.update_task_state(task_two.id, state="failed", error="boom")

            counts = store.count_tasks_by_state()
            self.assertEqual(counts.get("running"), 1)
            self.assertEqual(counts.get("failed"), 1)

            running_only = store.count_tasks_by_state(state="running")
            self.assertEqual(running_only, {"running": 1})

            store.close()


if __name__ == "__main__":
    unittest.main()
