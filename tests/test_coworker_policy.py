import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.approval import approval_matches, build_approval  # noqa: E402
from yordam_agent.coworker.plan import auto_checkpoints, compute_plan_hash  # noqa: E402
from yordam_agent.coworker.policy import CoworkerPolicy, validate_plan  # noqa: E402
from yordam_agent.coworker.registry import DEFAULT_REGISTRY  # noqa: E402


class TestCoworkerPlanAndPolicy(unittest.TestCase):
    def test_plan_hash_ignores_existing_hash(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {"id": "1", "tool": "fs.read_text", "args": {"path": "/tmp/example.txt"}}
            ],
        }
        hash_one = compute_plan_hash(plan)
        plan["plan_hash"] = "sha256:bad"
        hash_two = compute_plan_hash(plan)
        self.assertEqual(hash_one, hash_two)
        checkpoints = auto_checkpoints(plan["tool_calls"], every=2)
        self.assertEqual(checkpoints, [])

    def test_approval_matches_plan_hash(self) -> None:
        plan_hash = "sha256:abc123"
        approval = build_approval(plan_hash)
        self.assertTrue(approval_matches(plan_hash, approval))
        self.assertFalse(approval_matches("sha256:other", approval))
        approval_checkpoint = build_approval(plan_hash, checkpoint_id="cp1")
        self.assertTrue(approval_matches(plan_hash, approval_checkpoint, checkpoint_id="cp1"))
        self.assertFalse(approval_matches(plan_hash, approval_checkpoint, checkpoint_id="cp2"))

    def test_policy_allows_read_within_root(self) -> None:
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
            policy = CoworkerPolicy(
                allowed_roots=[root],
                max_read_bytes=1000,
                max_write_bytes=1000,
                max_web_bytes=1000,
                max_query_chars=256,
                require_approval=True,
                web_enabled=False,
                web_allowlist=[],
            )
            errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
            self.assertEqual(errors, [])

    def test_policy_blocks_non_positive_read_max_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.read_text",
                        "args": {"path": str(path), "max_bytes": 0},
                    }
                ],
            }
            policy = CoworkerPolicy(
                allowed_roots=[root],
                max_read_bytes=1000,
                max_write_bytes=1000,
                max_web_bytes=1000,
                max_query_chars=256,
                require_approval=True,
                web_enabled=False,
                web_allowlist=[],
            )
            errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
            self.assertTrue(any("max_bytes must be positive" in err for err in errors))

    def test_auto_checkpoints_every_writes(self) -> None:
        tool_calls = [
            {"id": "1", "tool": "fs.apply_write_file", "args": {"path": "/tmp/a", "content": "x"}},
            {"id": "2", "tool": "fs.move", "args": {"path": "/tmp/a", "dst": "/tmp/b"}},
            {"id": "3", "tool": "fs.read_text", "args": {"path": "/tmp/b"}},
            {"id": "4", "tool": "fs.rename", "args": {"path": "/tmp/b", "dst": "/tmp/c"}},
        ]
        checkpoints = auto_checkpoints(tool_calls, every=2)
        self.assertEqual(checkpoints, ["2"])

    def test_doc_tool_ocr_mode_validation(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "doc.extract_pdf_text",
                    "args": {"path": "/tmp/file.pdf", "ocr_mode": "invalid"},
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=False,
            web_allowlist=[],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("invalid ocr_mode" in err for err in errors))

    def test_policy_blocks_overwrite_in_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            path = root / "note.txt"
            path.write_text("hello", encoding="utf-8")
            plan = {
                "version": 1,
                "tool_calls": [
                    {
                        "id": "1",
                        "tool": "fs.apply_write_file",
                        "args": {"path": str(path), "content": "new"},
                    }
                ],
            }
            policy = CoworkerPolicy(
                allowed_roots=[root],
                max_read_bytes=1000,
                max_write_bytes=1000,
                max_web_bytes=1000,
                max_query_chars=256,
                require_approval=True,
                web_enabled=False,
                web_allowlist=[],
            )
            errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
            self.assertTrue(any("cannot overwrite" in err for err in errors))

    def test_policy_blocks_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            plan = {
                "version": 1,
                "tool_calls": [
                    {"id": "1", "tool": "fs.read_text", "args": {"path": "/etc/hosts"}}
                ],
            }
            policy = CoworkerPolicy(
                allowed_roots=[root],
                max_read_bytes=1000,
                max_write_bytes=1000,
                max_web_bytes=1000,
                max_query_chars=256,
                require_approval=True,
                web_enabled=False,
                web_allowlist=[],
            )
            errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
            self.assertTrue(any("outside allowlist" in err for err in errors))

    def test_web_fetch_requires_allowlist(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {"id": "1", "tool": "web.fetch", "args": {"url": "https://example.com"}}
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("allowlist" in err for err in errors))

    def test_web_fetch_allows_per_task_allowlist(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {"url": "https://example.com", "allowlist": ["example.com"]},
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertEqual(errors, [])

    def test_policy_blocks_unknown_tool(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "shell.exec",
                    "args": {"cmd": "ls"},
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=False,
            web_allowlist=[],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("allowlisted" in err for err in errors))

    def test_web_fetch_blocks_query_without_allow_query(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com/search?q=test",
                        "allowlist": ["example.com"],
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("allow_query" in err for err in errors))

    def test_web_fetch_allows_query_with_allow_query(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com/search?q=test",
                        "allowlist": ["example.com"],
                        "allow_query": True,
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertEqual(errors, [])

    def test_web_fetch_blocks_long_query(self) -> None:
        long_query = "q=" + ("a" * 50)
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": f"https://example.com/search?{long_query}",
                        "allowlist": ["example.com"],
                        "allow_query": True,
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=10,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("query exceeds policy limit" in err for err in errors))

    def test_web_fetch_blocks_body(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com",
                        "allowlist": ["example.com"],
                        "content": "secret",
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("cannot send local content" in err for err in errors))

    def test_web_fetch_blocks_method(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com",
                        "allowlist": ["example.com"],
                        "method": "POST",
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("method must be GET" in err for err in errors))

    def test_web_fetch_blocks_unsupported_fields(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com",
                        "allowlist": ["example.com"],
                        "headers": {"X-Test": "value"},
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("unsupported fields" in err for err in errors))

    def test_web_fetch_blocks_non_positive_max_bytes(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com",
                        "allowlist": ["example.com"],
                        "max_bytes": 0,
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("max_bytes must be positive" in err for err in errors))

    def test_web_fetch_blocks_excessive_max_bytes(self) -> None:
        plan = {
            "version": 1,
            "tool_calls": [
                {
                    "id": "1",
                    "tool": "web.fetch",
                    "args": {
                        "url": "https://example.com",
                        "allowlist": ["example.com"],
                        "max_bytes": 5000,
                    },
                }
            ],
        }
        policy = CoworkerPolicy(
            allowed_roots=[Path("/tmp")],
            max_read_bytes=1000,
            max_write_bytes=1000,
            max_web_bytes=1000,
            max_query_chars=256,
            require_approval=True,
            web_enabled=True,
            web_allowlist=["example.com"],
        )
        errors = validate_plan(plan, policy, DEFAULT_REGISTRY)
        self.assertTrue(any("max_bytes exceeds policy limit" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
