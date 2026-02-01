import plistlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker_runtime.launchd import (  # noqa: E402
    render_launchd_plist,
)


class TestCoworkerLaunchd(unittest.TestCase):
    def test_render_launchd_plist(self) -> None:
        plist_text = render_launchd_plist(
            program=Path("/usr/local/bin/yordam-agent"),
            label="com.example.yordam.runtime",
            state_dir=Path("/tmp/yordam-runtime"),
            workers=2,
            poll_seconds=2.5,
            worker_id="worker-test",
            stdout_path=Path("/tmp/yordam-runtime.out"),
            stderr_path=Path("/tmp/yordam-runtime.err"),
            enable_runtime_env=True,
        )
        payload = plistlib.loads(plist_text.encode("utf-8"))
        self.assertEqual(payload["Label"], "com.example.yordam.runtime")
        self.assertTrue(payload["RunAtLoad"])
        self.assertTrue(payload["KeepAlive"])
        args = payload["ProgramArguments"]
        self.assertEqual(args[0], "/usr/local/bin/yordam-agent")
        self.assertEqual(args[1:3], ["coworker-runtime", "daemon"])
        self.assertIn("--workers", args)
        self.assertIn("--state-dir", args)
        self.assertIn("--poll-seconds", args)
        self.assertIn("--worker-id", args)
        self.assertEqual(payload["StandardOutPath"], "/tmp/yordam-runtime.out")
        self.assertEqual(payload["StandardErrorPath"], "/tmp/yordam-runtime.err")
        env = payload["EnvironmentVariables"]
        self.assertEqual(env["YORDAM_COWORKER_RUNTIME_ENABLED"], "1")


if __name__ == "__main__":
    unittest.main()
