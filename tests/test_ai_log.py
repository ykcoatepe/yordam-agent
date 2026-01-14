import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.ai_log import (  # noqa: E402
    append_ai_log,
    build_log_entry,
    resolve_log_path,
)


class AiLogTests(unittest.TestCase):
    def test_resolve_log_path_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = resolve_log_path(".yordam-agent/ai-interactions.jsonl", root)
            self.assertEqual(
                resolved, root / ".yordam-agent" / "ai-interactions.jsonl"
            )

    def test_resolve_log_path_empty(self) -> None:
        self.assertIsNone(resolve_log_path("", Path("/tmp")))

    def test_build_log_entry_sanitizes_context(self) -> None:
        entry = build_log_entry(
            model="test",
            temperature=0.2,
            prompt_chars=10,
            system_chars=0,
            response_chars=5,
            duration_ms=12,
            success=True,
            error_type=None,
            context={"operation": "rewrite", "source": "file", "prompt": "secret"},
        )
        self.assertIn("context", entry)
        self.assertIn("operation", entry["context"])
        self.assertIn("source", entry["context"])
        self.assertNotIn("prompt", entry["context"])

    def test_append_ai_log_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / ".yordam-agent" / "ai-interactions.jsonl"
            entry = build_log_entry(
                model="test",
                temperature=None,
                prompt_chars=3,
                system_chars=1,
                response_chars=2,
                duration_ms=7,
                success=True,
                error_type=None,
                context={"operation": "rewrite"},
            )
            append_ai_log(log_path, entry)
            lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            parsed = json.loads(lines[0])
            self.assertEqual(parsed["event"], "ollama.generate")


if __name__ == "__main__":
    unittest.main()
