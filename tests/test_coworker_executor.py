import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.approval import build_approval  # noqa: E402
from yordam_agent.coworker.executor import (  # noqa: E402
    ApprovalError,
    PlanValidationError,
    apply_plan_with_state,
)
from yordam_agent.coworker.plan import compute_plan_hash  # noqa: E402
from yordam_agent.coworker.policy import CoworkerPolicy  # noqa: E402
from yordam_agent.coworker.registry import DEFAULT_REGISTRY  # noqa: E402


class TestCoworkerExecutor(unittest.TestCase):
    def _policy(self, root: Path, *, require_approval: bool = True) -> CoworkerPolicy:
        return CoworkerPolicy(
            allowed_roots=[root],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=require_approval,
            web_enabled=False,
            web_allowlist=[],
        )

    def test_apply_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(path)}}
                ],
            }
            policy = self._policy(root, require_approval=True)
            with self.assertRaises(ApprovalError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=None,
                    resume_state=None,
                    stop_at_checkpoints=False,
                )

    def test_apply_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(path)}}
                ],
            }
            plan_hash = compute_plan_hash(plan)
            approval = build_approval(plan_hash)
            plan["tool_calls"].append(
                {"id": "2", "tool": "fs.read_text", "args": {"path": str(path)}}
            )
            policy = self._policy(root, require_approval=True)
            with self.assertRaises(ApprovalError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=approval,
                    resume_state=None,
                    stop_at_checkpoints=False,
                )

    def test_resume_state_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(path)}}
                ],
            }
            policy = self._policy(root, require_approval=False)
            with self.assertRaises(PlanValidationError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=None,
                    resume_state={"plan_hash": "sha256:bad"},
                    stop_at_checkpoints=False,
                )

    def test_checkpoint_stop_returns_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            output_a = root / "out-a.txt"
            output_b = root / "out-b.txt"
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(output_a), "content": "a"},
                    },
                    {
                        "id": "2",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(output_b), "content": "b"},
                    },
                ],
                "checkpoints": ["2"],
            }
            plan_hash = compute_plan_hash(plan)
            approval = build_approval(plan_hash, checkpoint_id="2")
            policy = self._policy(root, require_approval=True)
            results, state = apply_plan_with_state(
                plan,
                policy,
                DEFAULT_REGISTRY,
                approval=approval,
                resume_state=None,
                stop_at_checkpoints=True,
            )
            self.assertTrue(any("wrote:" in result for result in results))
            self.assertIsNotNone(state)
            self.assertEqual(state.get("next_checkpoint"), None)


if __name__ == "__main__":
    unittest.main()
