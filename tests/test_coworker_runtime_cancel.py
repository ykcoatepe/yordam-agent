import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent import config as config_module  # noqa: E402
from yordam_agent.cli import cmd_coworker_runtime_cancel  # noqa: E402
from yordam_agent.coworker_runtime.locks import acquire_locks  # noqa: E402
from yordam_agent.coworker_runtime.task_bundle import ensure_task_bundle  # noqa: E402
from yordam_agent.coworker_runtime.task_store import TaskStore  # noqa: E402


class TestCoworkerRuntimeCancel(unittest.TestCase):
    def test_cancel_does_not_release_running_locks(self) -> None:
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

                target = tmp_path / "data.txt"
                target.write_text("data", encoding="utf-8")
                store = TaskStore(state_dir / "tasks.db")
                task = store.create_task(
                    plan_hash="sha256:run",
                    plan_path=tmp_path / "plan.json",
                    bundle_path=tmp_path / "bundle",
                    metadata={"selected_paths": [str(target)]},
                    state="running",
                )
                handle = acquire_locks(
                    [target],
                    locks_dir=state_dir / "locks",
                    task_id=task.id,
                    owner="worker-1",
                )
                self.assertTrue(handle.lock_files)

                args = SimpleNamespace(task=task.id, state_dir=str(state_dir))
                result = cmd_coworker_runtime_cancel(args)

                self.assertEqual(result, 0)
                refreshed = store.get_task(task.id)
                self.assertEqual(refreshed.state, "canceled")
                for lock_file in handle.lock_files:
                    self.assertTrue(lock_file.exists())
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

    def test_cancel_handles_missing_original_plan(self) -> None:
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

                plan = {"version": 1, "tool_calls": []}
                plan_path = tmp_path / "plan.json"
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                store = TaskStore(state_dir / "tasks.db")
                task = store.create_task(
                    plan_hash="sha256:test",
                    plan_path=plan_path,
                    bundle_path=tmp_path / "bundle",
                )
                ensure_task_bundle(
                    Path(task.bundle_path),
                    task_id=task.id,
                    plan=plan,
                    metadata=task.metadata,
                )
                plan_path.unlink()

                args = SimpleNamespace(task=task.id, state_dir=str(state_dir))
                result = cmd_coworker_runtime_cancel(args)

                self.assertEqual(result, 0)
                refreshed = store.get_task(task.id)
                self.assertEqual(refreshed.state, "canceled")
                self.assertTrue((Path(task.bundle_path) / "events.jsonl").exists())
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

    def test_cancel_releases_allowed_roots_when_selected_paths_missing(self) -> None:
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

                allowed_root = tmp_path / "allowed"
                allowed_root.mkdir()
                store = TaskStore(state_dir / "tasks.db")
                task = store.create_task(
                    plan_hash="sha256:allow",
                    plan_path=tmp_path / "plan.json",
                    bundle_path=tmp_path / "bundle",
                    metadata={"allowed_roots": [str(allowed_root)]},
                    state="waiting_approval",
                )
                handle = acquire_locks(
                    [allowed_root],
                    locks_dir=state_dir / "locks",
                    task_id=task.id,
                    owner="worker-1",
                )
                self.assertTrue(handle.lock_files)

                args = SimpleNamespace(task=task.id, state_dir=str(state_dir))
                result = cmd_coworker_runtime_cancel(args)

                self.assertEqual(result, 0)
                for lock_file in handle.lock_files:
                    self.assertFalse(lock_file.exists())
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
