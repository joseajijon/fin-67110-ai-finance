import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


HOOK = Path(__file__).parents[1] / ".codex" / "hooks" / "verify_skill_output.py"
SPEC = importlib.util.spec_from_file_location("verify_skill_output", HOOK)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class SkillOutputHookTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.report = Path(self.folder.name) / "report.md"
        self.manifest = self.report.with_suffix(".md.evidence.json")
        self.manifest.write_text(
            json.dumps(
                {
                    "evidence": [
                        {
                            "id": "calc-1",
                            "type": "computation",
                            "expression": "10 + 2 - 3 = 9",
                            "inputs": [10, 2, 3],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.folder.cleanup()

    def test_accepts_supported_number(self):
        self.report.write_text("Owner cash flow is 9. <!-- evidence:calc-1 -->\n", encoding="utf-8")
        self.assertEqual(MODULE.check(self.report), [])

    def test_rejects_number_without_marker(self):
        self.report.write_text("Owner cash flow is 9.\n", encoding="utf-8")
        errors = MODULE.check(self.report)
        self.assertTrue(any("without evidence" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
