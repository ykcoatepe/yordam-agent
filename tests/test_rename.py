import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.rename import (  # noqa: E402
    RenameOp,
    _normalize_target_name,
    _resolve_name_collision,
    apply_renames,
)


class RenameTests(unittest.TestCase):
    def test_normalize_target_name_adds_extension(self) -> None:
        src = Path("/tmp/report.pdf")
        normalized = _normalize_target_name("2025 Q1 Report", src)
        self.assertEqual(normalized, "2025 Q1 Report.pdf")

    def test_normalize_target_name_preserves_extension(self) -> None:
        src = Path("/tmp/photo.jpg")
        normalized = _normalize_target_name("Beach.jpg", src)
        self.assertEqual(normalized, "Beach.jpg")

    def test_normalize_target_name_forces_original_extension(self) -> None:
        src = Path("/tmp/report.pdf")
        normalized = _normalize_target_name("Report.txt", src)
        self.assertEqual(normalized, "Report.pdf")

    def test_resolve_name_collision(self) -> None:
        reserved = {"Report.pdf", "Report__1.pdf"}
        resolved = _resolve_name_collision("Report.pdf", reserved)
        self.assertEqual(resolved, "Report__2.pdf")

    def test_apply_renames_handles_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.txt"
            b = root / "b.txt"
            a.write_text("A", encoding="utf-8")
            b.write_text("B", encoding="utf-8")
            ops = [RenameOp(src=a, dst=b), RenameOp(src=b, dst=a)]
            apply_renames(ops)
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "B")
            self.assertEqual((root / "b.txt").read_text(encoding="utf-8"), "A")


if __name__ == "__main__":
    unittest.main()
