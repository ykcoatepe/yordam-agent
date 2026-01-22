import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.plan import compute_plan_hash  # noqa: E402
from yordam_agent.coworker_runtime.daemon import _claim_waiting_task, _run_task  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
