import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.policy import load_policy  # noqa: E402


class PolicyTests(unittest.TestCase):
    def test_load_policy_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            policy = load_policy(policy_path)
            self.assertTrue(policy_path.exists())
            self.assertIn("ignore_patterns", policy)
            self.assertIn("extension_overrides", policy)


if __name__ == "__main__":
    unittest.main()
