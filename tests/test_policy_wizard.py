import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yordam_agent.policy_wizard import (  # noqa: E402
    parse_extension_overrides,
    parse_type_overrides,
)


class PolicyWizardParseTests(unittest.TestCase):
    def test_parse_extension_overrides(self) -> None:
        parsed = parse_extension_overrides(".pdf=Documents, .psd=Design/Assets")
        self.assertEqual(parsed[".pdf"], "Documents")
        self.assertEqual(parsed[".psd"], {"category": "Design", "subcategory": "Assets"})

    def test_parse_type_overrides(self) -> None:
        parsed = parse_type_overrides("Image=Images, Video=Media")
        self.assertEqual(parsed["Image"], "Images")
        self.assertEqual(parsed["Video"], "Media")


if __name__ == "__main__":
    unittest.main()
