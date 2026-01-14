import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.organize import FileMeta, apply_policy, gather_files  # noqa: E402


class OrganizeTests(unittest.TestCase):
    def test_apply_policy_extension_override(self) -> None:
        meta = FileMeta(
            path=Path("/tmp/report.pdf"),
            name="report.pdf",
            extension=".pdf",
            size_bytes=100,
            modified_iso="2025-01-01T00:00:00",
            type_group="Document",
            snippet="",
        )
        policy = {"extension_overrides": {".pdf": "Finance"}}
        category = apply_policy(meta, policy)
        self.assertEqual(category, ("Finance", None))

    def test_apply_policy_name_rule(self) -> None:
        meta = FileMeta(
            path=Path("/tmp/invoice-2024.txt"),
            name="invoice-2024.txt",
            extension=".txt",
            size_bytes=100,
            modified_iso="2025-01-01T00:00:00",
            type_group="Text",
            snippet="",
        )
        policy = {
            "name_contains_rules": [
                {"contains": "invoice", "category": "Finance", "subcategory": "Taxes"}
            ]
        }
        category = apply_policy(meta, policy)
        self.assertEqual(category, ("Finance", "Taxes"))

    def test_gather_files_ignore_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("ok", encoding="utf-8")
            ignored_dir = root / "node_modules"
            ignored_dir.mkdir()
            (ignored_dir / "ignore.txt").write_text("no", encoding="utf-8")

            files = gather_files(
                root,
                recursive=True,
                include_hidden=True,
                ignore_patterns=["node_modules"],
            )
            names = {path.name for path in files}
            self.assertIn("keep.txt", names)
            self.assertNotIn("ignore.txt", names)


if __name__ == "__main__":
    unittest.main()
