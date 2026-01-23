import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent import config as config_module  # noqa: E402
from yordam_agent.cli import cmd_coworker_runtime_submit  # noqa: E402
from yordam_agent.coworker_runtime.task_store import TaskStore  # noqa: E402


class TestCoworkerRuntimeSubmit(unittest.TestCase):
    def test_submit_requires_allowed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_dir = config_module.CONFIG_DIR
            original_file = config_module.CONFIG_FILE
            original_enabled = os.environ.get("YORDAM_COWORKER_RUNTIME_ENABLED")
            original_state_dir = os.environ.get("YORDAM_COWORKER_RUNTIME_STATE_DIR")
            try:
                config_module.CONFIG_DIR = tmp_path / "config"
                config_module.CONFIG_FILE = config_module.CONFIG_DIR / "config.json"
                config_module.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                config_module.CONFIG_FILE.write_text(
                    json.dumps(
                        {
                            "coworker_runtime_enabled": True,
                            "coworker_allowed_paths": [],
                        }
                    ),
                    encoding="utf-8",
                )
                os.environ["YORDAM_COWORKER_RUNTIME_ENABLED"] = "1"
                state_dir = tmp_path / "state"
                os.environ["YORDAM_COWORKER_RUNTIME_STATE_DIR"] = str(state_dir)

                plan_path = tmp_path / "plan.json"
                plan_path.write_text(json.dumps({"version": 1, "tool_calls": []}))
                args = SimpleNamespace(
                    plan=str(plan_path),
                    bundle_root=None,
                    state_dir=str(state_dir),
                    paths=None,
                    allow_root=None,
                    metadata=None,
                )

                result = cmd_coworker_runtime_submit(args)

                self.assertEqual(result, 1)
                self.assertFalse((state_dir / "tasks.db").exists())
            finally:
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

    def test_submit_persists_allowed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            original_dir = config_module.CONFIG_DIR
            original_file = config_module.CONFIG_FILE
            original_enabled = os.environ.get("YORDAM_COWORKER_RUNTIME_ENABLED")
            original_state_dir = os.environ.get("YORDAM_COWORKER_RUNTIME_STATE_DIR")
            try:
                config_module.CONFIG_DIR = tmp_path / "config"
                config_module.CONFIG_FILE = config_module.CONFIG_DIR / "config.json"
                config_module.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                allowed_root = tmp_path / "allowed"
                allowed_root.mkdir()
                config_module.CONFIG_FILE.write_text(
                    json.dumps(
                        {
                            "coworker_runtime_enabled": True,
                            "coworker_allowed_paths": [str(allowed_root)],
                        }
                    ),
                    encoding="utf-8",
                )
                os.environ["YORDAM_COWORKER_RUNTIME_ENABLED"] = "1"
                state_dir = tmp_path / "state"
                os.environ["YORDAM_COWORKER_RUNTIME_STATE_DIR"] = str(state_dir)

                plan_path = tmp_path / "plan.json"
                plan_path.write_text(json.dumps({"version": 1, "tool_calls": []}))
                args = SimpleNamespace(
                    plan=str(plan_path),
                    bundle_root=None,
                    state_dir=str(state_dir),
                    paths=None,
                    allow_root=None,
                    metadata=None,
                )

                result = cmd_coworker_runtime_submit(args)

                self.assertEqual(result, 0)
                store = TaskStore(state_dir / "tasks.db")
                tasks = store.list_tasks()
                self.assertEqual(len(tasks), 1)
                metadata = tasks[0].metadata
                allowed_roots = metadata.get("allowed_roots")
                self.assertIsNotNone(allowed_roots)
                self.assertEqual(
                    [Path(value).resolve() for value in allowed_roots],
                    [allowed_root.resolve()],
                )
                store.close()
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
