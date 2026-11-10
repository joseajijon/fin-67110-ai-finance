#!/usr/bin/env python3
"""Build the arithmetic section of a filing-backed spinoff worksheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_CONFIG = (
    "valuation_method",
    "low_case_rate_or_multiple",
    "mid_case_rate_or_multiple",
    "client_purchase_size_usd",
    "high_conviction_rule",
    "low_conviction_rule",
)


def value_range(after_tax_earnings: float, depreciation: float, capex: float, method: str, low: float, mid: float) -> dict[str, float]:
    owner_cash_flow = after_tax_earnings + depreciation - capex
    if method == "owner_cash_flow_multiple":
        low_value = owner_cash_flow * low
        mid_value = owner_cash_flow * mid
    elif method == "capitalization_rate":
        if low <= 0 or mid <= 0:
            raise ValueError("Capitalization rates must be greater than zero.")
        low_value = owner_cash_flow / low
        mid_value = owner_cash_flow / mid
    else:
        raise ValueError("valuation_method must be owner_cash_flow_multiple or capitalization_rate.")
    return {"owner_cash_flow": owner_cash_flow, "low_value": low_value, "mid_value": mid_value}


def _load_complete_config(path: Path) -> dict[str, object]:
    config = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_CONFIG if config.get(key) in (None, "")]
    if missing:
        raise ValueError("Complete these student-authored worksheet fields: " + ", ".join(missing))
    return config


def build(facts_path: Path, config_path: Path, output: Path) -> Path:
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    config = _load_complete_config(config_path)
    required_facts = ("company", "ticker", "as_of_date", "after_tax_earnings", "depreciation", "capital_spending")
    missing = [key for key in required_facts if facts.get(key) in (None, "")]
    if missing:
        raise ValueError("The facts file lacks: " + ", ".join(missing))
    results = value_range(
        float(facts["after_tax_earnings"]),
        float(facts["depreciation"]),
        float(facts["capital_spending"]),
        str(config["valuation_method"]),
        float(config["low_case_rate_or_multiple"]),
        float(config["mid_case_rate_or_multiple"]),
    )
    units = str(facts.get("units", "USD"))
    calc_id = "owner-cash-flow"
    low_id = "low-value"
    mid_id = "mid-value"
    date_id = "worksheet-date"
    lines = [
        f"# {facts['company']} ({facts['ticker']}): spinoff worksheet, {facts['as_of_date']} <!-- evidence:{date_id} -->",
        "",
        "Screens to look at, not a recommendation.",
        "",
        "## Facts",
        "",
        "Complete the filing-backed facts sections before use.",
        "",
        "## Value range",
        "",
        f"Owner cash flow = {facts['after_tax_earnings']} + {facts['depreciation']} - {facts['capital_spending']} = {results['owner_cash_flow']} {units}. <!-- evidence:{calc_id} -->",
        f"Low case = {results['low_value']} {units}. <!-- evidence:{low_id} -->",
        f"Mid case = {results['mid_value']} {units}. <!-- evidence:{mid_id} -->",
        "",
        "## Why it may be cheap",
        "",
        "Student persona judgment required.",
        "",
        "## What the parent pushed into it",
        "",
        "Not known until the cited filing facts are complete.",
        "",
        "## The parent after the spin",
        "",
        "Not known until the cited filing facts are complete.",
        "",
        "## Insiders and catalysts",
        "",
        "Not known until the cited filing facts are complete.",
        "",
        "## Can you buy it",
        "",
        "Not known until price and volume facts are complete.",
        "",
        "## Not known",
        "",
        "All incomplete filing-backed fields listed above.",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence = {
        "evidence": [
            {"id": date_id, "type": "fact", "facts_file": str(facts_path), "key": "as_of_date"},
            {
                "id": calc_id,
                "type": "computation",
                "expression": "after_tax_earnings + depreciation - capital_spending",
                "inputs": [facts["after_tax_earnings"], facts["depreciation"], facts["capital_spending"]],
            },
            {
                "id": low_id,
                "type": "computation",
                "expression": f"{config['valuation_method']} low case",
                "inputs": [results["owner_cash_flow"], config["low_case_rate_or_multiple"]],
            },
            {
                "id": mid_id,
                "type": "computation",
                "expression": f"{config['valuation_method']} mid case",
                "inputs": [results["owner_cash_flow"], config["mid_case_rate_or_multiple"]],
            },
        ]
    }
    output.with_suffix(output.suffix + ".evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("week4/student_inputs/worksheet_method.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build(args.facts, args.config, args.output)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(report)
    print(f"SKILL_OUTPUT: {report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
