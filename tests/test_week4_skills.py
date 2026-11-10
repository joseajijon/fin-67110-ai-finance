import tempfile
import unittest
from pathlib import Path

from spinoff_seeker import factors_complete
from spinoff_worksheet import value_range


class Week4SkillTests(unittest.TestCase):
    def test_owner_cash_flow_multiple(self):
        result = value_range(100.0, 20.0, 30.0, "owner_cash_flow_multiple", 8.0, 10.0)
        self.assertEqual(result, {"owner_cash_flow": 90.0, "low_value": 720.0, "mid_value": 900.0})

    def test_capitalization_rate(self):
        result = value_range(100.0, 20.0, 30.0, "capitalization_rate", 0.12, 0.10)
        self.assertAlmostEqual(result["low_value"], 750.0)
        self.assertAlmostEqual(result["mid_value"], 900.0)

    def test_blank_factor_file_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "factors.json"
            path.write_text('{"window_days_after_distribution": null, "factors": []}', encoding="utf-8")
            self.assertFalse(factors_complete(path))


if __name__ == "__main__":
    unittest.main()
