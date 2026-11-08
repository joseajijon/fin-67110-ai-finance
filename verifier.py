#!/usr/bin/env python3
"""Deterministic report verifier for the FIN 67110 agent team."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClaimSpec:
    number: str
    label: str
    pattern: str
    expected: float | None
    source: str
    tolerance: float


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fact(facts: dict[str, Any], concept: str, period: str = "current") -> dict[str, Any] | None:
    return facts.get("concepts", {}).get(concept, {}).get(period)


def _value(facts: dict[str, Any], concept: str, period: str = "current") -> float | None:
    record = _fact(facts, concept, period)
    return float(record["value"]) if record else None


def _fact_source(record: dict[str, Any] | None) -> str:
    if not record:
        return "Not stated in the saved facts."
    return (
        f"XBRL tag {record['tag']}; period end {record['end']}; "
        f"filing {record['filing']}; filing value {record['value']:g} {record['unit']}."
    )


def _ratio_source(ratios: dict[str, Any], key: str) -> str:
    detail = ratios[key]
    return f"{detail['definition']}. Arithmetic: {detail['arithmetic']}."


def _filing_line(path: Path, required: tuple[str, ...]) -> str:
    if not path.exists():
        return "Saved filing line unavailable."
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        lower = line.lower()
        if all(token.lower() in lower for token in required):
            return f"{path.name} line {number}: {line}"
    return "Matching saved filing line not found."


def _claim_specs(run_dir: Path) -> list[ClaimSpec]:
    facts = _read_json(run_dir / "facts.json")
    ratios = _read_json(run_dir / "ratios.json")
    quarter = _read_json(run_dir / "quarter_claims.json")
    revenue = _fact(facts, "total_revenue")
    op_income = _fact(facts, "operating_income")
    net_income = _fact(facts, "net_income")
    eps = _fact(facts, "diluted_eps")
    eps_line = _filing_line(run_dir / "10-K.txt", ("diluted |", "20.76", "18.21"))
    return [
        ClaimSpec("1", "Annual total revenue", r"Annual total revenue", _value(facts, "total_revenue"), _fact_source(revenue), 1.0),
        ClaimSpec("2", "Annual revenue growth", r"Annual revenue growth", ratios["revenue_growth"]["value"], _ratio_source(ratios, "revenue_growth"), 0.00005),
        ClaimSpec("3a", "Annual operating income", r"Annual operating income", _value(facts, "operating_income"), _fact_source(op_income), 1.0),
        ClaimSpec("3b", "Annual operating margin", r"Annual operating margin", ratios["operating_margin"]["value"], _ratio_source(ratios, "operating_margin"), 0.00005),
        ClaimSpec("4", "Annual net income", r"Annual net income", _value(facts, "net_income"), _fact_source(net_income), 1.0),
        ClaimSpec("5", "Annual diluted EPS, GAAP", r"Annual diluted EPS, GAAP", _value(facts, "diluted_eps"), _fact_source(eps) + " " + eps_line, 0.005),
        ClaimSpec("6", "Return on average equity", r"Return on average equity", ratios["return_on_average_equity"]["value"], _ratio_source(ratios, "return_on_average_equity"), 0.00005),
        ClaimSpec("7", "Debt to equity", r"Debt to equity", ratios["debt_to_equity"]["value"], _ratio_source(ratios, "debt_to_equity"), 0.00005),
        ClaimSpec("8", "Free cash flow", r"Free cash flow", ratios["free_cash_flow"]["value"], _ratio_source(ratios, "free_cash_flow"), 1.0),
        ClaimSpec(
            "9",
            "Quarter total revenue",
            r"Quarter total revenue",
            None if quarter.get("latest_quarter_total_revenue") is None else float(quarter["latest_quarter_total_revenue"]) * 1_000_000,
            str(quarter.get("total_revenue_release_line") or "Not stated in the saved release.") + " Amounts are USD millions.",
            1.0,
        ),
        ClaimSpec("10", "Quarter revenue growth", r"Quarter revenue growth", quarter.get("quarter_revenue_growth"), f"Arithmetic: {quarter.get('quarter_revenue_growth_arithmetic')}", 0.00005),
        ClaimSpec("11", "Quarter diluted EPS, GAAP", r"Quarter diluted EPS, GAAP", quarter.get("quarter_diluted_eps_gaap"), str(quarter.get("diluted_eps_release_line") or "Not stated in the saved release."), 0.005),
    ]


def _parse_claim_line(report: str, pattern: str) -> tuple[float, str] | None:
    match = re.search(
        rf"^\s*[-*]?\s*{pattern}\s*:\s*([^\n]+)$",
        report,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        return None
    field = match.group(1).strip()
    number = re.search(r"[-+]?\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|x)?", field)
    if not number:
        return None
    token = number.group(0).replace("$", "").replace(",", "").replace(" ", "")
    is_percent = token.endswith("%")
    token = token.rstrip("%x")
    value = float(token)
    if is_percent:
        value /= 100
    unit_match = re.search(r"\b(thousand|million|billion|trillion)\b", field, re.IGNORECASE)
    if unit_match and not is_percent:
        scales = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
        value *= scales[unit_match.group(1).lower()]
    return value, field


def verify_report(run_dir: Path, report_path: Path | None = None) -> tuple[Path, list[dict[str, Any]]]:
    """Verify the 11 fixed claims and save the report with marks under its first line."""
    report_path = report_path or run_dir / "equity_research_report.md"
    report = report_path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for spec in _claim_specs(run_dir):
        parsed = _parse_claim_line(report, spec.pattern)
        if parsed is None:
            mark = "missing"
            observed: float | None = None
            report_text = "Not found"
        elif spec.expected is None:
            mark = "unsupported"
            observed, report_text = parsed
        else:
            observed, report_text = parsed
            mark = "correct" if math.isclose(observed, spec.expected, rel_tol=0, abs_tol=spec.tolerance) else "wrong"
        rows.append(
            {
                "claim": spec.number,
                "label": spec.label,
                "report_value": observed,
                "expected_value": spec.expected,
                "mark": mark,
                "evidence": spec.source,
                "report_text": report_text,
            }
        )

    errors = sum(row["mark"] in {"wrong", "unsupported"} for row in rows)
    missing = sum(row["mark"] == "missing" for row in rows)
    table = [
        "",
        "## Verifier marks",
        "",
        f"Errors (wrong + unsupported): {errors}",
        f"Missing claims: {missing}",
        "",
        "| Claim | Report value | Saved-evidence value | Mark | Correction and evidence |",
        "|---|---:|---:|---|---|",
    ]
    for row in rows:
        observed = "—" if row["report_value"] is None else f"{row['report_value']:g}"
        expected = "—" if row["expected_value"] is None else f"{row['expected_value']:g}"
        evidence = str(row["evidence"]).replace("|", "\\|").replace("\n", " ")
        table.append(
            f"| {row['claim']} {row['label']} | {observed} | {expected} | "
            f"{row['mark']} | {evidence} |"
        )

    lines = report.splitlines()
    first_line = lines[0] if lines else ""
    rest = "\n".join(lines[1:])
    verified = first_line + "\n" + "\n".join(table) + "\n\n" + rest.lstrip() + "\n"
    output = run_dir / "verified_report.md"
    output.write_text(verified, encoding="utf-8")
    (run_dir / "verifier_marks.json").write_text(
        json.dumps({"errors": errors, "missing": missing, "marks": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    return output, rows

