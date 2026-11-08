import json
import tempfile
import unittest
from pathlib import Path

from verifier import verify_report


class VerifierTests(unittest.TestCase):
    def test_seeded_eps_is_wrong_and_corrected(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            current = lambda name, value, unit="USD": {
                "tag": name, "value": value, "unit": unit, "end": "2026-08-30",
                "filing": "0000909832-26-000093",
            }
            facts = {"concepts": {
                "total_revenue": {"current": current("Revenue", 303154000000)},
                "operating_income": {"current": current("OperatingIncomeLoss", 11685000000)},
                "net_income": {"current": current("NetIncomeLoss", 9226000000)},
                "diluted_eps": {"current": current("EarningsPerShareDiluted", 20.76, "USD/shares")},
            }}
            ratios = {
                key: {"value": value, "definition": key, "arithmetic": "saved arithmetic"}
                for key, value in {
                    "revenue_growth": .101437, "operating_margin": .038545,
                    "return_on_average_equity": .284021, "debt_to_equity": .172108,
                    "free_cash_flow": 9382000000,
                }.items()
            }
            quarter = {
                "latest_quarter_total_revenue": 95723, "quarter_revenue_growth": .11105,
                "quarter_diluted_eps_gaap": 6.75, "quarter_revenue_growth_arithmetic": "saved",
                "total_revenue_release_line": "Total revenue 95,723 86,156",
                "diluted_eps_release_line": "Diluted 6.75 5.87",
            }
            for name, value in (("facts.json", facts), ("ratios.json", ratios), ("quarter_claims.json", quarter)):
                (run / name).write_text(json.dumps(value), encoding="utf-8")
            (run / "equity_research_report.md").write_text(
                "Filings read: test\nAnnual diluted EPS, GAAP: $21.76\n", encoding="utf-8"
            )
            output, rows = verify_report(run)
            eps = next(row for row in rows if row["claim"] == "5")
            self.assertEqual(eps["mark"], "wrong")
            self.assertEqual(eps["expected_value"], 20.76)
            self.assertIn("20.76", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
