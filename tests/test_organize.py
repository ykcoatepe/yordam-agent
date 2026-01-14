import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.organize import (  # noqa: E402
    FileMeta,
    _extract_person_from_filename,
    _extract_person_from_text,
    apply_policy,
    gather_files,
    resolve_reorg_selection,
)


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

    def test_resolve_reorg_selection_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved_root, selected = resolve_reorg_selection([root])
            self.assertEqual(resolved_root.resolve(), root.resolve())
            self.assertIsNone(selected)

    def test_resolve_reorg_selection_files_same_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_a = root / "a.txt"
            file_b = root / "b.txt"
            file_a.write_text("a", encoding="utf-8")
            file_b.write_text("b", encoding="utf-8")
            resolved_root, selected = resolve_reorg_selection([file_a, file_b])
            self.assertEqual(resolved_root.resolve(), root.resolve())
            self.assertEqual(selected, [file_a, file_b])

    def test_resolve_reorg_selection_rejects_multiple_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "other"
            other.mkdir()
            file_a = root / "a.txt"
            file_b = other / "b.txt"
            file_a.write_text("a", encoding="utf-8")
            file_b.write_text("b", encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_reorg_selection([file_a, file_b])

    def test_resolve_reorg_selection_rejects_folder_in_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_a = root / "a.txt"
            file_a.write_text("a", encoding="utf-8")
            subdir = root / "subdir"
            subdir.mkdir()
            with self.assertRaises(ValueError):
                resolve_reorg_selection([file_a, subdir])

    def test_extract_person_from_filename(self) -> None:
        name = "Yordam_Kocatepe_CV.docx"
        person = _extract_person_from_filename(name)
        self.assertEqual(person, "Yordam Kocatepe")

    def test_extract_person_from_text(self) -> None:
        text = "Bu belge Cahit Senol Kocatepe icindir."
        person = _extract_person_from_text(text)
        self.assertEqual(person, "Cahit Senol Kocatepe")


if __name__ == "__main__":
    unittest.main()
