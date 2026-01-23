import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker_runtime.task_bundle import (  # noqa: E402
    ensure_task_bundle,
)


class TestCoworkerTaskBundle(unittest.TestCase):
    def test_init_task_bundle_writes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bundle"
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.read_text",
                        "args": {"path": "/tmp/example.txt"},
                    }
                ],
            }
            paths = ensure_task_bundle(
                root,
                task_id="tsk_test",
                plan=plan,
                metadata={"selected_paths": ["/tmp"]},
            )

            self.assertTrue(paths.task_path.exists())
            self.assertTrue(paths.plan_path.exists())
            self.assertTrue(paths.preview_path.exists())
            self.assertTrue(paths.events_path.exists())
            self.assertTrue(paths.scratch_dir.exists())
            self.assertTrue(paths.staging_dir.exists())

            task_payload = json.loads(paths.task_path.read_text(encoding="utf-8"))
            self.assertEqual(task_payload["task_id"], "tsk_test")
            self.assertEqual(task_payload["state"], "queued")
            self.assertIn("plan_hash", task_payload)


if __name__ == "__main__":
    unittest.main()
