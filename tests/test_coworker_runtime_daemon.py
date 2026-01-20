import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker_runtime.daemon import _claim_waiting_task  # noqa: E402
from yordam_agent.coworker_runtime.task_store import TaskStore  # noqa: E402


class TestCoworkerRuntimeDaemon(unittest.TestCase):
    def test_claim_waiting_task_accepts_checkpoint_approval_for_final_segment(self) -> None:
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
            self.assertIsNotNone(claimed)
            self.assertEqual(claimed.id, task.id)
            self.assertEqual(claimed.state, "running")

            store.close()


if __name__ == "__main__":
    unittest.main()
