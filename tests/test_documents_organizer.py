import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.documents_organizer import (  # noqa: E402
    match_extension,
    match_keyword,
    parse_ai_response,
    resolve_existing_folder,
    sanitize_folder_name,
)


class DocumentsOrganizerTests(unittest.TestCase):
    def test_sanitize_folder_name_basic(self) -> None:
        self.assertEqual(sanitize_folder_name("  /Reports/ "), "Reports")

    def test_sanitize_folder_name_invalid(self) -> None:
        self.assertEqual(sanitize_folder_name("."), "")
        self.assertEqual(sanitize_folder_name(""), "")

    def test_parse_ai_response_json(self) -> None:
        folder, reason = parse_ai_response('{"folder": "Projects", "reason": "work"}')
        self.assertEqual(folder, "Projects")
        self.assertEqual(reason, "work")

    def test_parse_ai_response_fallback(self) -> None:
        folder, reason = parse_ai_response("Archive")
        self.assertEqual(folder, "Archive")
        self.assertEqual(reason, "")

    def test_match_extension_rule(self) -> None:
        rules = [{"extensions": [".pdf"], "dest": "Documents", "reason": "doc"}]
        dest, reason = match_extension(".pdf", rules)
        self.assertEqual(dest, "Documents")
        self.assertEqual(reason, "doc")

    def test_match_keyword_rule(self) -> None:
        rules = [{"keyword": "cessna", "dest": "Aviation"}]
        dest, reason = match_keyword("cessna logbook", rules)
        self.assertEqual(dest, "Aviation")
        self.assertEqual(reason, "cessna")

    def test_resolve_existing_folder(self) -> None:
        folder, found = resolve_existing_folder("projects", ["Projects", "Personal"])
        self.assertEqual(folder, "Projects")
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
