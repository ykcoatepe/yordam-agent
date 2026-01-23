import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.coworker.summarize import (  # noqa: E402
    _format_output,
    _task_output_path,
    _task_spec,
)


class TestCoworkerSummarize(unittest.TestCase):
    def test_task_output_path_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.txt"
            path.write_text("hello", encoding="utf-8")
            spec = _task_spec("summary")
            output = _task_output_path(path, spec)
            self.assertEqual(output.name, "doc.summary.md")

    def test_task_output_path_outline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.pdf"
            path.write_text("hello", encoding="utf-8")
            spec = _task_spec("outline")
            output = _task_output_path(path, spec)
            self.assertEqual(output.name, "doc.outline.md")

    def test_format_output_header(self) -> None:
        source = Path("/tmp/example.pdf")
        spec = _task_spec("report")
        rendered = _format_output(source, "Content", spec)
        self.assertTrue(rendered.startswith("# Report: example.pdf"))


if __name__ == "__main__":
    unittest.main()
