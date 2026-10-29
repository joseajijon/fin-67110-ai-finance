"""Known-answer checks from Costco's fiscal 2026 Form 10-K.

Filing: https://www.sec.gov/Archives/edgar/data/909832/000090983226000093/cost-20260830.htm
Amounts are USD millions except diluted EPS.
"""

import unittest

from equity_desk import calculate_ratios


def record(value, tag, end, unit="USD"):
    return {
        "concept": tag,
        "tag": tag,
        "value": value,
        "unit": unit,
        "start": None,
        "end": end,
        "fiscal_year": int(end[:4]),
        "fiscal_period": "FY",
        "form": "10-K",
        "filing": "0000909832-26-000093",
        "filed": "2026-10-06",
    }


class CostcoKnownAnswerTests(unittest.TestCase):
    def test_fiscal_2026_ratios_match_filing_arithmetic(self):
        current_end = "2026-08-30"
        prior_end = "2025-08-31"
        concepts = {
            "total_revenue": {
                "current": record(303154, "Revenues", current_end),
                "prior": record(275235, "Revenues", prior_end),
            },
            "operating_income": {
                "current": record(11685, "OperatingIncomeLoss", current_end),
                "prior": record(10383, "OperatingIncomeLoss", prior_end),
            },
            "net_income": {
                "current": record(9226, "NetIncomeLoss", current_end),
                "prior": record(8099, "NetIncomeLoss", prior_end),
            },
            "diluted_eps": {
                "current": record(20.76, "EarningsPerShareDiluted", current_end, "USD/shares"),
                "prior": record(18.21, "EarningsPerShareDiluted", prior_end, "USD/shares"),
            },
            "stockholders_equity": {
                "current": record(35803, "StockholdersEquity", current_end),
                "prior": record(29164, "StockholdersEquity", prior_end),
            },
            "long_term_debt": {
                "current": record(3914, "LongTermDebtNoncurrent", current_end),
                "prior": record(5713, "LongTermDebtNoncurrent", prior_end),
            },
            "current_debt_portion": {
                "current": record(2248, "LongTermDebtCurrent", current_end),
                "prior": record(75, "LongTermDebtCurrent", prior_end),
            },
            "cash_from_operations": {
                "current": record(15817, "NetCashProvidedByUsedInOperatingActivities", current_end),
                "prior": record(13335, "NetCashProvidedByUsedInOperatingActivities", prior_end),
            },
            "capital_expenditures": {
                "current": record(6435, "PaymentsToAcquirePropertyPlantAndEquipment", current_end),
                "prior": record(5498, "PaymentsToAcquirePropertyPlantAndEquipment", prior_end),
            },
        }
        ratios = calculate_ratios({"concepts": concepts}, price=None)
        self.assertAlmostEqual(
            ratios["revenue_growth"]["value"], (303154 - 275235) / 275235
        )
        self.assertAlmostEqual(
            ratios["operating_margin"]["value"], 11685 / 303154
        )
        self.assertAlmostEqual(
            ratios["return_on_average_equity"]["value"], 9226 / ((35803 + 29164) / 2)
        )
        self.assertAlmostEqual(
            ratios["debt_to_equity"]["value"], (3914 + 2248) / 35803
        )
        self.assertEqual(ratios["free_cash_flow"]["value"], 15817 - 6435)


if __name__ == "__main__":
    unittest.main()
