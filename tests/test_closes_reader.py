import tempfile
import unittest
from pathlib import Path

from closes_reader import last_close_before, official_daily_closes


class ClosesReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "closes.csv"
        self.path.write_text(
            "ticker,date,close\nABC,2026-11-06,10.00\nABC,2026-11-09,10.50\nXYZ,2026-11-09,22.00\n",
            encoding="utf-8",
        )
        self.env = {"LSEG_EXPORT_PATH": str(self.path)}

    def tearDown(self):
        self.folder.cleanup()

    def test_daily_closes_filters_ticker_and_dates(self):
        values = official_daily_closes("ABC", "2026-11-06", "2026-11-09", self.env)
        self.assertNotEqual(values, "not available")
        self.assertEqual([item.close for item in values], [10.0, 10.5])

    def test_filing_before_four_uses_prior_trading_close(self):
        value = last_close_before("ABC", "2026-11-09T15:59:59", self.env)
        self.assertNotEqual(value, "not available")
        self.assertEqual(value.date, "2026-11-06")

    def test_filing_at_four_uses_prior_close_because_before_is_strict(self):
        value = last_close_before("ABC", "2026-11-09T16:00:00", self.env)
        self.assertNotEqual(value, "not available")
        self.assertEqual(value.date, "2026-11-06")

    def test_filing_after_four_can_use_same_day_close(self):
        value = last_close_before("ABC", "2026-11-09T16:00:01", self.env)
        self.assertNotEqual(value, "not available")
        self.assertEqual(value.date, "2026-11-09")

    def test_missing_ticker_is_not_available(self):
        self.assertEqual(last_close_before("MISS", "2026-11-09T18:00:00", self.env), "not available")


if __name__ == "__main__":
    unittest.main()

