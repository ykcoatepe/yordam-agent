import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent import config as config_module  # noqa: E402
from yordam_agent.cli import cmd_coworker_runtime_logs  # noqa: E402


class TestCoworkerRuntimeLogs(unittest.TestCase):
    def test_logs_missing_task_returns_exit_code_2(self) -> None:
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
                    json.dumps({"coworker_runtime_enabled": True}),
                    encoding="utf-8",
                )
                os.environ["YORDAM_COWORKER_RUNTIME_ENABLED"] = "1"
                state_dir = tmp_path / "state"
                os.environ["YORDAM_COWORKER_RUNTIME_STATE_DIR"] = str(state_dir)

                args = SimpleNamespace(task="tsk_missing", state_dir=str(state_dir))
                result = cmd_coworker_runtime_logs(args)

                self.assertEqual(result, 2)
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


if __name__ == "__main__":
    unittest.main()
