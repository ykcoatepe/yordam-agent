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
    preview_plan,
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

    def test_rejects_unknown_checkpoint_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": str(path)}}
                ],
                "checkpoints": ["missing"],
            }
            policy = self._policy(root, require_approval=False)
            with self.assertRaises(PlanValidationError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=None,
                    resume_state=None,
                    stop_at_checkpoints=False,
                )

    def test_checkpoint_at_final_call_does_not_pause(self) -> None:
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
            self.assertIsNone(state)

    def test_resume_after_last_checkpoint_runs_remaining_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            input_path = root / "note.txt"
            output_c = root / "out-c.txt"
            input_path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.read_text",
                        "args": {"path": str(input_path)},
                    },
                    {
                        "id": "2",
                        "tool": "fs.read_text",
                        "args": {"path": str(input_path)},
                    },
                    {
                        "id": "3",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(output_c), "content": "c"},
                    },
                ],
                "checkpoints": ["2"],
            }
            plan_hash = compute_plan_hash(plan)
            approval = build_approval(plan_hash, checkpoint_id="2")
            policy = self._policy(root, require_approval=True)

            _, state = apply_plan_with_state(
                plan,
                policy,
                DEFAULT_REGISTRY,
                approval=approval,
                resume_state=None,
                stop_at_checkpoints=True,
            )
            self.assertIsNotNone(state)
            self.assertEqual(state.get("next_checkpoint"), None)
            self.assertFalse(output_c.exists())

            plan_level_approval = build_approval(plan_hash)
            _, resumed_state = apply_plan_with_state(
                plan,
                policy,
                DEFAULT_REGISTRY,
                approval=plan_level_approval,
                resume_state=state,
                stop_at_checkpoints=True,
            )
            self.assertIsNone(resumed_state)
            self.assertTrue(output_c.exists())

    def test_move_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / "src.txt"
            dest = root / "dest.txt"
            src.write_text("src", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(dest), "content": "dest"},
                    },
                    {
                        "id": "2",
                        "tool": "fs.move",
                        "args": {"path": str(src), "dst": str(dest)},
                    },
                ],
            }
            policy = self._policy(root, require_approval=False)
            with self.assertRaises(PlanValidationError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=None,
                    resume_state=None,
                    stop_at_checkpoints=False,
                )

    def test_rename_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            src = root / "src.txt"
            dest = root / "dest.txt"
            src.write_text("src", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(dest), "content": "dest"},
                    },
                    {
                        "id": "2",
                        "tool": "fs.rename",
                        "args": {"path": str(src), "dst": str(dest)},
                    },
                ],
            }
            policy = self._policy(root, require_approval=False)
            with self.assertRaises(PlanValidationError):
                apply_plan_with_state(
                    plan,
                    policy,
                    DEFAULT_REGISTRY,
                    approval=None,
                    resume_state=None,
                    stop_at_checkpoints=False,
                )

    def test_preview_plan_limits_diff_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            content = "line1\nline2\n"
            path.write_text(content, encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.propose_write_file",
                        "args": {"path": str(path), "content": content},
                    }
                ],
            }
            policy = CoworkerPolicy(
                allowed_roots=[root],
                max_read_bytes=5,
                max_write_bytes=1000,
                max_web_bytes=1000,
                max_query_chars=256,
                require_approval=False,
                web_enabled=False,
                web_allowlist=[],
            )
            lines = preview_plan(plan, policy, DEFAULT_REGISTRY, include_diffs=True)
            diff_output = "\n".join(lines)
            self.assertIn("Diff for", diff_output)
            self.assertIn("+line2", diff_output)


if __name__ == "__main__":
    unittest.main()
