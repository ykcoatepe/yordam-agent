import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent import config as config_module  # noqa: E402
from yordam_agent.cli import cmd_coworker_runtime_cancel  # noqa: E402
from yordam_agent.coworker_runtime.task_store import TaskStore  # noqa: E402


class TestCoworkerRuntimeCancel(unittest.TestCase):
    def test_cancel_terminal_task_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_dir = config_module.CONFIG_DIR
            original_file = config_module.CONFIG_FILE
            original_enabled = os.environ.get("YORDAM_COWORKER_RUNTIME_ENABLED")
            original_state_dir = os.environ.get("YORDAM_COWORKER_RUNTIME_STATE_DIR")
            try:
                config_module.CONFIG_DIR = tmp_path / "config"
                config_module.CONFIG_FILE = config_module.CONFIG_DIR / "config.json"
                os.environ["YORDAM_COWORKER_RUNTIME_ENABLED"] = "1"
                state_dir = tmp_path / "state"
                os.environ["YORDAM_COWORKER_RUNTIME_STATE_DIR"] = str(state_dir)

                store = TaskStore(state_dir / "tasks.db")
                task = store.create_task(
                    plan_hash="sha256:test",
                    plan_path=tmp_path / "plan.json",
                    bundle_path=tmp_path / "bundle",
                    state="completed",
                )

                args = SimpleNamespace(task=task.id, state_dir=str(state_dir))
                result = cmd_coworker_runtime_cancel(args)

                self.assertEqual(result, 0)
                refreshed = store.get_task(task.id)
                self.assertEqual(refreshed.state, "completed")
            finally:
                if "store" in locals():
                    try:
                        store.close()
                    except Exception:
                        pass
                if original_enabled is None:
                    os.environ.pop("YORDAM_COWORKER_RUNTIME_ENABLED", None)
                else:
                    os.environ["YORDAM_COWORKER_RUNTIME_ENABLED"] = original_enabled
                if original_state_dir is None:
                    os.environ.pop("YORDAM_COWORKER_RUNTIME_STATE_DIR", None)
                else:
                    os.environ["YORDAM_COWORKER_RUNTIME_STATE_DIR"] = original_state_dir
                config_module.CONFIG_DIR = original_dir
                config_module.CONFIG_FILE = original_file


if __name__ == "__main__":
    unittest.main()
