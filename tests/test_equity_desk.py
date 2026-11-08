import unittest

from equity_desk import (
    calculate_ratios,
    html_to_text,
    release_quarter_claims,
    select_concept_tag,
    select_filings,
)


def fact(value, tag, end="2025-08-31"):
    return {
        "concept": tag,
        "tag": tag,
        "value": value,
        "unit": "USD",
        "start": "2024-09-01",
        "end": end,
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "form": "10-K",
        "filing": "0000000000-25-000001",
        "filed": "2025-10-01",
    }


class DeskTests(unittest.TestCase):
    def test_select_filings_skips_newer_non_earnings_8k(self):
        rows = [
            {"form": "8-K", "items": "5.02", "acceptanceDateTime": "2026-10-20T10:00:00.000Z", "accessionNumber": "0001-26-000003", "filingDate": "2026-10-20", "reportDate": "2026-10-20", "primaryDocument": "other.htm"},
            {"form": "8-K", "items": "2.02,9.01", "acceptanceDateTime": "2026-10-10T10:00:00.000Z", "accessionNumber": "0001-26-000002", "filingDate": "2026-10-10", "reportDate": "2026-10-10", "primaryDocument": "earnings.htm"},
            {"form": "10-Q", "items": "", "acceptanceDateTime": "2026-09-01T10:00:00.000Z", "accessionNumber": "0001-26-000001", "filingDate": "2026-09-01", "reportDate": "2026-08-01", "primaryDocument": "q.htm"},
            {"form": "10-K", "items": "", "acceptanceDateTime": "2026-08-01T10:00:00.000Z", "accessionNumber": "0001-26-000000", "filingDate": "2026-08-01", "reportDate": "2026-07-01", "primaryDocument": "k.htm"},
        ]
        selected = select_filings("0000000001", rows)
        self.assertEqual(selected["8-K"].accession, "0001-26-000002")

    def test_select_concept_tag_uses_newest_period(self):
        company_facts = {
            "facts": {"us-gaap": {
                "Revenues": {"units": {"USD": [{"form": "10-K", "end": "2024-12-31", "val": 1}]}},
                "RevenueFromContractWithCustomerIncludingAssessedTax": {"units": {"USD": [{"form": "10-K", "end": "2025-12-31", "val": 2}]}},
            }}
        }
        self.assertEqual(
            select_concept_tag(company_facts, ("Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax")),
            "RevenueFromContractWithCustomerIncludingAssessedTax",
        )

    def test_ratios_show_expected_arithmetic(self):
        concepts = {
            "total_revenue": {"current": fact(120, "Revenues"), "prior": fact(100, "Revenues", "2024-08-31")},
            "operating_income": {"current": fact(12, "OperatingIncomeLoss"), "prior": None},
            "net_income": {"current": fact(9, "NetIncomeLoss"), "prior": None},
            "diluted_eps": {"current": fact(3, "EarningsPerShareDiluted"), "prior": None},
            "stockholders_equity": {"current": fact(50, "StockholdersEquity"), "prior": fact(40, "StockholdersEquity", "2024-08-31")},
            "long_term_debt": {"current": fact(20, "LongTermDebtNoncurrent"), "prior": None},
            "current_debt_portion": {"current": fact(5, "LongTermDebtCurrent"), "prior": None},
            "cash_from_operations": {"current": fact(15, "NetCashProvidedByUsedInOperatingActivities"), "prior": None},
            "capital_expenditures": {"current": fact(4, "PaymentsToAcquirePropertyPlantAndEquipment"), "prior": None},
        }
        ratios = calculate_ratios({"concepts": concepts}, price=30)
        self.assertAlmostEqual(ratios["revenue_growth"]["value"], 0.2)
        self.assertAlmostEqual(ratios["operating_margin"]["value"], 0.1)
        self.assertAlmostEqual(ratios["return_on_average_equity"]["value"], 0.2)
        self.assertAlmostEqual(ratios["debt_to_equity"]["value"], 0.5)
        self.assertEqual(ratios["free_cash_flow"]["value"], 11)
        self.assertEqual(ratios["price_to_earnings"]["value"], 10)

    def test_release_table_rows_and_quarter_growth(self):
        document = b"""
        <table><tr><td>Total revenue</td><td>$</td><td>95,723</td>
        <td>$</td><td>86,156</td><td>$</td><td>303,154</td></tr>
        <tr><td>Diluted</td><td>$</td><td>6.75</td><td>$</td><td>5.87</td></tr></table>
        """
        text = html_to_text(document)
        claims = release_quarter_claims(text)
        self.assertEqual(claims["latest_quarter_total_revenue"], 95723)
        self.assertEqual(claims["quarter_diluted_eps_gaap"], 6.75)
        self.assertAlmostEqual(
            claims["quarter_revenue_growth"], (95723 - 86156) / 86156
        )


if __name__ == "__main__":
    unittest.main()
