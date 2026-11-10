#!/usr/bin/env python3
"""Find Form 10 candidates on EDGAR without treating search hits as facts."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from equity_desk import load_env


EFTS_URL = "https://efts.sec.gov/LATEST/search-index"


def search_candidates(start: str, end: str, user_agent: str) -> list[dict[str, str]]:
    parameters = {
        "q": '"information statement"',
        "forms": "10-12B,10-12G",
        "startdt": start,
        "enddt": end,
        "from": "0",
        "size": "100",
    }
    request = Request(
        f"{EFTS_URL}?{urlencode(parameters)}",
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    candidates: list[dict[str, str]] = []
    seen_accessions: set[str] = set()
    for hit in payload.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        accession = str(source.get("adsh", ""))
        if accession and accession in seen_accessions:
            continue
        seen_accessions.add(accession)
        cik_values = source.get("ciks") or []
        cik = str(cik_values[0]).lstrip("0") if cik_values else ""
        filing_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
            if cik and accession
            else ""
        )
        names = source.get("display_names") or []
        candidates.append(
            {
                "company": str(names[0] if names else source.get("entity_name", "not available")),
                "form": str(source.get("form", "not available")),
                "filing_date": str(source.get("file_date", "not available")),
                "accession": accession or "not available",
                "cik": cik or "not available",
                "filing_directory": filing_url or "not available",
                "classification": "candidate; parent distribution not yet established",
            }
        )
    return candidates


def factors_complete(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    factors = payload.get("factors", [])
    if not payload.get("window_days_after_distribution") or not factors:
        return False
    required = {"name", "direction", "weight", "chapter"}
    return all(isinstance(item, dict) and required <= set(item) for item in factors)


def save_run(candidates: list[dict[str, str]], start: str, end: str, output: Path, factors: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    registry = output / "candidate_registry.json"
    registry.write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    report = output / "spinoff_screen.md"
    evidence: list[dict[str, object]] = []
    lines = ["# EDGAR Form 10 candidate screen <!-- evidence:search-range -->", ""]
    range_id = "search-range"
    evidence.append(
        {
            "id": range_id,
            "type": "config",
            "config_file": str(registry),
            "key": "search range and Form 10 query",
        }
    )
    lines.append(f"Search period: {start} through {end}. <!-- evidence:{range_id} -->")
    lines.extend(["", "A search hit is a candidate. It is not proof of a spinoff.", ""])
    for index, candidate in enumerate(candidates, 1):
        evidence_id = f"candidate-{index}"
        evidence.append(
            {
                "id": evidence_id,
                "type": "filing",
                "filing": candidate["accession"],
                "section": "EDGAR full-text search result",
                "date": candidate["filing_date"],
                "source": candidate["filing_directory"],
            }
        )
        lines.append(
            f"- {candidate['company']} — {candidate['form']}; filed {candidate['filing_date']}; "
            f"accession {candidate['accession']}. <!-- evidence:{evidence_id} -->"
        )
    lines.extend(["", "Ranking status: ready." if factors_complete(factors) else "Ranking status: not run. The student-authored factor file is incomplete.", "", "Screens, not recommendations."])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report.with_suffix(".md.evidence.json").write_text(
        json.dumps({"evidence": evidence}, indent=2), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Inclusive start date, YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive end date")
    parser.add_argument("--output", type=Path, default=Path("week4/outputs/seeker"))
    parser.add_argument("--factors", type=Path, default=Path("week4/student_inputs/factors.json"))
    args = parser.parse_args()
    env = load_env(Path(__file__).with_name(".env"))
    user_agent = env.get("SEC_USER_AGENT", "")
    if not user_agent:
        raise SystemExit("SEC_USER_AGENT is required in .env.")
    candidates = search_candidates(args.start, args.end, user_agent)
    report = save_run(candidates, args.start, args.end, args.output, args.factors)
    print(report)
    print(f"SKILL_OUTPUT: {report.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
