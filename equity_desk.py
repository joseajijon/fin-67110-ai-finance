#!/usr/bin/env python3
"""SEC-backed equity research desk for FIN 67110 Labs 02 and 03.

The data pipeline is deterministic. Model roles run only when --report is used.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/"

REVENUE_TAGS = (
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
)

CONCEPT_TAGS: dict[str, tuple[str, ...]] = {
    "total_revenue": REVENUE_TAGS,
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": (
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ),
    "diluted_eps": ("EarningsPerShareDiluted",),
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "long_term_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    ),
    "current_debt_portion": (
        "LongTermDebtCurrent",
        "CurrentPortionOfLongTermDebt",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
    ),
    "cash_from_operations": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditures": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
}

BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "dl", "dt",
    "dd", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "tfoot", "thead", "tr", "ul",
}


def load_env(path: Path) -> dict[str, str]:
    """Read a simple .env file without adding a package dependency."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Invalid .env line {line_number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class TextExtractor(HTMLParser):
    """Convert filing HTML into readable, line-oriented plain text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif not self.skip_depth and tag in {"td", "th"}:
            if self.parts and not self.parts[-1].endswith(("\n", " | ")):
                self.parts.append(" | ")
        elif not self.skip_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in {"td", "th"}:
            self.parts.append(" | ")
        elif not self.skip_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            clean = re.sub(r"\s+", " ", data)
            if not clean.strip():
                return
            if (
                self.parts
                and self.parts[-1]
                and not self.parts[-1].endswith((" ", "\n", "|", "$", "(", "/"))
                and clean[0].isalnum()
                and self.parts[-1][-1].isalnum()
            ):
                self.parts.append(" ")
            self.parts.append(clean)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts)).replace("\xa0", " ")
        lines: list[str] = []
        for line in raw.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            if clean:
                lines.append(clean)
        return "\n".join(lines) + "\n"


class IndexTableParser(HTMLParser):
    """Capture links and row text from an EDGAR filing index."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self.in_row = False
        self.row_text: list[str] = []
        self.row_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.lower() == "tr":
            self.in_row = True
            self.row_text = []
            self.row_links = []
        elif self.in_row and tag.lower() == "a" and attributes.get("href"):
            self.row_links.append(attributes["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "tr" and self.in_row:
            self.rows.append(
                {"text": re.sub(r"\s+", " ", " ".join(self.row_text)).strip(),
                 "links": list(self.row_links)}
            )
            self.in_row = False

    def handle_data(self, data: str) -> None:
        if self.in_row and data.strip():
            self.row_text.append(data.strip())


def html_to_text(document: bytes) -> str:
    parser = TextExtractor()
    parser.feed(document.decode("utf-8", errors="replace"))
    return parser.text()


@dataclass
class Filing:
    form: str
    accession: str
    filing_date: str
    report_date: str
    accepted: str
    primary_document: str
    items: str
    index_url: str
    document_url: str
    release_url: str | None = None


@dataclass
class FactValue:
    concept: str
    tag: str
    value: float
    unit: str
    start: str | None
    end: str
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    filing: str
    filed: str


class SecClient:
    """Small EDGAR client with a declared User-Agent and fair-access pacing."""

    def __init__(self, user_agent: str, delay_seconds: float = 0.12) -> None:
        if not user_agent or "your-purdue-email" in user_agent.lower():
            raise ValueError(
                "SEC_USER_AGENT is missing. Put your name and Purdue email in .env."
            )
        self.user_agent = user_agent
        self.delay_seconds = max(delay_seconds, 0.11)
        self._last_request = 0.0

    def get_bytes(self, url: str) -> bytes:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    payload = gzip.decompress(payload)
                self._last_request = time.monotonic()
                return payload
        except HTTPError as exc:
            raise RuntimeError(f"SEC returned HTTP {exc.code} for {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach SEC for {url}: {exc.reason}") from exc

    def get_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.get_bytes(url).decode("utf-8"))


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.-]{1,15}", ticker):
        raise ValueError(f"Invalid ticker: {value!r}")
    return ticker


def accession_path(accession: str) -> str:
    return accession.replace("-", "")


def filing_directory(cik: str, accession: str) -> str:
    return f"{ARCHIVES_BASE}{int(cik)}/{accession_path(accession)}/"


def filing_from_row(cik: str, row: dict[str, Any]) -> Filing:
    directory = filing_directory(cik, row["accessionNumber"])
    accession = row["accessionNumber"]
    primary = row.get("primaryDocument", "")
    return Filing(
        form=row.get("form", ""),
        accession=accession,
        filing_date=row.get("filingDate", ""),
        report_date=row.get("reportDate", ""),
        accepted=row.get("acceptanceDateTime", ""),
        primary_document=primary,
        items=row.get("items", "") or "",
        index_url=urljoin(directory, f"{accession}-index.html"),
        document_url=urljoin(directory, primary),
    )


def recent_rows(submissions: dict[str, Any]) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return []
    keys = list(recent)
    row_count = max((len(recent.get(key, [])) for key in keys), default=0)
    return [
        {key: recent.get(key, [""] * row_count)[index] for key in keys}
        for index in range(row_count)
    ]


def select_filings(cik: str, rows: list[dict[str, Any]]) -> dict[str, Filing]:
    """Select the latest 10-K, 10-Q, and earnings 8-K (Item 2.02)."""
    ordered = sorted(
        rows,
        key=lambda row: (row.get("acceptanceDateTime", ""), row.get("filingDate", "")),
        reverse=True,
    )

    def first(predicate: Any, label: str) -> Filing:
        for row in ordered:
            if predicate(row):
                return filing_from_row(cik, row)
        raise RuntimeError(f"No {label} found in the recent submissions history")

    return {
        "10-K": first(lambda row: row.get("form") == "10-K", "10-K"),
        "10-Q": first(lambda row: row.get("form") == "10-Q", "10-Q"),
        "8-K": first(
            lambda row: row.get("form") == "8-K"
            and "2.02" in str(row.get("items", "")),
            "earnings 8-K reporting Item 2.02",
        ),
    }


def parse_index(index_bytes: bytes, index_url: str) -> tuple[str | None, str | None]:
    decoded = index_bytes.decode("utf-8", errors="replace")
    parser = IndexTableParser()
    parser.feed(decoded)
    release_url: str | None = None
    for row in parser.rows:
        upper = row["text"].upper()
        if "EX-99.1" in upper or "EXHIBIT 99.1" in upper:
            candidates = [link for link in row["links"] if not link.startswith("#")]
            if candidates:
                release_url = urljoin(index_url, candidates[-1])
                break
    text = html_to_text(index_bytes)
    accepted_match = re.search(
        r"Accepted\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    accepted = accepted_match.group(1) if accepted_match else None
    return accepted, release_url


def annual_records(company_facts: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    concept = company_facts.get("facts", {}).get("us-gaap", {}).get(tag, {})
    records: list[dict[str, Any]] = []
    for unit, values in concept.get("units", {}).items():
        for value in values:
            if value.get("form") in {"10-K", "10-K/A"}:
                record = dict(value)
                record["unit"] = unit
                records.append(record)
    return records


def latest_tag_end(company_facts: dict[str, Any], tag: str) -> str:
    ends = [record.get("end", "") for record in annual_records(company_facts, tag)]
    return max(ends, default="")


def select_concept_tag(company_facts: dict[str, Any], candidates: Iterable[str]) -> str | None:
    """Choose the candidate whose newest annual period is newest; order breaks ties."""
    scored: list[tuple[str, int, str]] = []
    for index, tag in enumerate(candidates):
        latest_end = latest_tag_end(company_facts, tag)
        if latest_end:
            scored.append((latest_end, -index, tag))
    return max(scored)[2] if scored else None


def record_for_end(records: list[dict[str, Any]], end: str) -> dict[str, Any] | None:
    matches = [record for record in records if record.get("end") == end]
    if not matches:
        return None
    fy_matches = [record for record in matches if record.get("fp") == "FY"]
    pool = fy_matches or matches
    return max(pool, key=lambda record: (record.get("filed", ""), record.get("accn", "")))


def fact_value(
    concept: str,
    tag: str,
    company_facts: dict[str, Any],
    end: str,
) -> FactValue | None:
    record = record_for_end(annual_records(company_facts, tag), end)
    if record is None:
        return None
    return FactValue(
        concept=concept,
        tag=tag,
        value=float(record["val"]),
        unit=record["unit"],
        start=record.get("start"),
        end=record["end"],
        fiscal_year=record.get("fy"),
        fiscal_period=record.get("fp"),
        form=record.get("form", ""),
        filing=record.get("accn", ""),
        filed=record.get("filed", ""),
    )


def previous_period_end(company_facts: dict[str, Any], revenue_tag: str, current_end: str) -> str:
    older = {
        record.get("end", "")
        for record in annual_records(company_facts, revenue_tag)
        if record.get("end", "") < current_end
    }
    if not older:
        raise RuntimeError(f"No prior annual period found for {revenue_tag}")
    return max(older)


def extract_facts(company_facts: dict[str, Any], fiscal_year_end: str) -> dict[str, Any]:
    revenue_tag = select_concept_tag(company_facts, REVENUE_TAGS)
    if revenue_tag is None:
        raise RuntimeError("No supported total-revenue XBRL tag was found")
    revenue_ends = {
        record.get("end", "") for record in annual_records(company_facts, revenue_tag)
    }
    if fiscal_year_end not in revenue_ends:
        latest = max(revenue_ends, default="")
        raise RuntimeError(
            f"Revenue tag {revenue_tag} has newest annual period {latest}, "
            f"not the latest 10-K fiscal year end {fiscal_year_end}."
        )
    prior_end = previous_period_end(company_facts, revenue_tag, fiscal_year_end)
    result: dict[str, Any] = {
        "company": company_facts.get("entityName", ""),
        "cik": str(company_facts.get("cik", "")).zfill(10),
        "fiscal_year_end": fiscal_year_end,
        "prior_year_end": prior_end,
        "revenue_definition": "total revenue",
        "concepts": {},
    }
    for concept, candidates in CONCEPT_TAGS.items():
        tag = revenue_tag if concept == "total_revenue" else select_concept_tag(
            company_facts, candidates
        )
        current = fact_value(concept, tag, company_facts, fiscal_year_end) if tag else None
        prior = fact_value(concept, tag, company_facts, prior_end) if tag else None
        result["concepts"][concept] = {
            "tag": tag,
            "current": asdict(current) if current else None,
            "prior": asdict(prior) if prior else None,
        }
    return result


def value_of(facts: dict[str, Any], concept: str, period: str = "current") -> float | None:
    record = facts["concepts"].get(concept, {}).get(period)
    return float(record["value"]) if record else None


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in {None, 0}:
        return None
    return numerator / denominator


def calculate_ratios(facts: dict[str, Any], price: float | None) -> dict[str, Any]:
    revenue = value_of(facts, "total_revenue")
    prior_revenue = value_of(facts, "total_revenue", "prior")
    operating_income = value_of(facts, "operating_income")
    net_income = value_of(facts, "net_income")
    equity = value_of(facts, "stockholders_equity")
    prior_equity = value_of(facts, "stockholders_equity", "prior")
    debt = value_of(facts, "long_term_debt")
    current_debt = value_of(facts, "current_debt_portion") or 0.0
    cfo = value_of(facts, "cash_from_operations")
    capex = value_of(facts, "capital_expenditures")
    eps = value_of(facts, "diluted_eps")
    average_equity = None
    if equity is not None and prior_equity is not None:
        average_equity = (equity + prior_equity) / 2
    free_cash_flow = None if cfo is None or capex is None else cfo - capex

    def item(value: float | None, arithmetic: str, definition: str) -> dict[str, Any]:
        return {"value": value, "arithmetic": arithmetic, "definition": definition}

    return {
        "revenue_growth": item(
            safe_ratio(None if revenue is None or prior_revenue is None else revenue - prior_revenue,
                       prior_revenue),
            f"({revenue} - {prior_revenue}) / {prior_revenue}",
            "Growth in total revenue",
        ),
        "operating_margin": item(
            safe_ratio(operating_income, revenue),
            f"{operating_income} / {revenue}",
            "Operating income divided by total revenue",
        ),
        "return_on_average_equity": item(
            safe_ratio(net_income, average_equity),
            f"{net_income} / (({equity} + {prior_equity}) / 2)",
            "Net income divided by average stockholders' equity",
        ),
        "debt_to_equity": item(
            safe_ratio(None if debt is None else debt + current_debt, equity),
            f"({debt} + {current_debt}) / {equity}",
            "Long-term debt plus its current portion, divided by stockholders' equity",
        ),
        "free_cash_flow": item(
            free_cash_flow,
            f"{cfo} - {capex}",
            "Cash from operations minus additions to property and equipment",
        ),
        "price_to_earnings": item(
            safe_ratio(price, eps),
            f"{price} / {eps}",
            "Given share price divided by annual diluted EPS",
        ),
    }


def format_number(value: float | None) -> str:
    if value is None:
        return "MISSING"
    if abs(value) >= 1_000_000:
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def print_facts(facts: dict[str, Any]) -> None:
    print(f"Fiscal year end: {facts['fiscal_year_end']}; prior: {facts['prior_year_end']}")
    for concept, data in facts["concepts"].items():
        current = data["current"]
        prior = data["prior"]
        if current:
            print(
                f"  {concept}: {format_number(current['value'])} {current['unit']} | "
                f"tag={current['tag']} end={current['end']} filing={current['filing']}"
            )
        else:
            print(f"  {concept}: MISSING | tag={data['tag']} end={facts['fiscal_year_end']}")
        if prior:
            print(
                f"    prior: {format_number(prior['value'])} {prior['unit']} | "
                f"tag={prior['tag']} end={prior['end']} filing={prior['filing']}"
            )


def print_ratios(ratios: dict[str, Any]) -> None:
    for name, detail in ratios.items():
        value = detail["value"]
        if name == "free_cash_flow":
            display = format_number(value)
        else:
            display = "MISSING" if value is None else f"{value:.4%}" if name != "price_to_earnings" else f"{value:.2f}x"
        print(f"  {name}: {display}")
        print(f"    arithmetic: {detail['arithmetic']}")
        print(f"    definition: {detail['definition']}")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug or "company"


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def numbered_excerpt(text: str, start_pattern: str, end_patterns: tuple[str, ...], limit: int = 350) -> str:
    lines = text.splitlines()
    start = 0
    pattern = re.compile(start_pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if pattern.search(line):
            start = index
            break
    end = min(len(lines), start + limit)
    for index in range(start + 5, min(len(lines), start + limit)):
        if any(re.search(candidate, lines[index], re.IGNORECASE) for candidate in end_patterns):
            end = index
            break
    return "\n".join(f"L{index + 1}: {lines[index]}" for index in range(start, end))


def release_claim_lines(text: str) -> list[str]:
    lines = text.splitlines()
    claims: list[str] = []
    patterns = (
        re.compile(r"\b(total\s+revenue|net\s+sales|revenue)\b", re.IGNORECASE),
        re.compile(r"\b(diluted.*(?:earnings|net income).*share|earnings.*diluted share)\b", re.IGNORECASE),
    )
    for pattern in patterns:
        matches = [f"L{index + 1}: {line}" for index, line in enumerate(lines) if pattern.search(line)]
        claims.extend(matches[:3])
    return claims


def release_quarter_claims(text: str) -> dict[str, Any]:
    """Read the quarter columns from release table rows and calculate growth in code."""
    rows = text.splitlines()
    revenue_row = next(
        (row for row in rows if re.search(r"\btotal\s+revenue\b", row, re.IGNORECASE)),
        "",
    )
    diluted_row = next(
        (row for row in rows if re.match(r"\s*diluted\b", row, re.IGNORECASE)),
        "",
    )

    def numbers(row: str) -> list[float]:
        values: list[float] = []
        for raw in re.findall(r"(?<![A-Za-z])\(?\d[\d,]*(?:\.\d+)?\)?", row):
            negative = raw.startswith("(") and raw.endswith(")")
            value = float(raw.strip("()").replace(",", ""))
            values.append(-value if negative else value)
        return values

    revenue_values = numbers(revenue_row)
    diluted_values = numbers(diluted_row)
    current_revenue = revenue_values[0] if len(revenue_values) >= 2 else None
    prior_revenue = revenue_values[1] if len(revenue_values) >= 2 else None
    growth = safe_ratio(
        None if current_revenue is None or prior_revenue is None else current_revenue - prior_revenue,
        prior_revenue,
    )
    current_eps = diluted_values[0] if len(diluted_values) >= 2 else None
    return {
        "latest_quarter_total_revenue": current_revenue,
        "prior_year_quarter_total_revenue": prior_revenue,
        "quarter_revenue_growth": growth,
        "quarter_revenue_growth_arithmetic": f"({current_revenue} - {prior_revenue}) / {prior_revenue}",
        "quarter_diluted_eps_gaap": current_eps,
        "total_revenue_release_line": revenue_row or None,
        "diluted_eps_release_line": diluted_row or None,
    }


def ensure_run_dir(base: Path, company: str) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%Z")
    run_dir = base / f"{slugify(company)}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def manager_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise RuntimeError("Strategy Manager did not return valid JSON")
        return json.loads(match.group(0))


def call_model(client: Any, model: str, role: str, instructions: str, handoff: dict[str, Any]) -> str:
    print(role)
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=json.dumps(handoff, ensure_ascii=False),
        max_output_tokens=5000,
    )
    output = response.output_text.strip()
    if not output:
        raise RuntimeError(f"{role} returned an empty response")
    return output


ROLE_INSTRUCTIONS = {
    "research_analyst": """You are the Research Analyst in an equity-research desk. Use only the JSON context you receive. Discuss the business model, competitive position, catalysts, and recent developments. Every factual claim must quote a supplied line number. Do not invent facts or numbers. Return concise Markdown under clear subheadings.""",
    "financial_analyst": """You are the Financial Analyst in an equity-research desk. Use only the supplied deterministic facts, ratios, release lines, and peer facts. You must state all eleven audit claims when the supplied evidence contains them: latest-fiscal-year total revenue; revenue growth; operating income and operating margin; net income attributable to the company; GAAP diluted EPS; return on average equity; debt to equity including the current portion; free cash flow; latest-quarter total revenue; latest-quarter total-revenue growth versus the same quarter last year; and latest-quarter GAAP diluted EPS. Every number must show its XBRL tag, period end, and filing accession, or a quoted release line. Repeat the supplied arithmetic for every ratio. State the definition wherever alternatives exist. Never calculate inside the model and never invent a missing number. Mark an unavailable claim as missing. Return concise Markdown.""",
    "investment_advisor": """You are the Investment Advisor. Use only the Research Analyst and Financial Analyst outputs supplied in JSON. State a thesis and one of Buy, Hold, or Sell. Identify the single sourced number that most affects the recommendation. Do not add outside facts or calculate a number. Return concise Markdown.""",
    "strategy_manager": """You are the Strategy Manager. Use only the role outputs and filing metadata supplied in JSON. Check that the report is internally consistent and contains exactly these five Markdown sections: Overview; Market Positioning and Growth Outlook; Valuation Insights; Future Developments and Strategic Recommendations; Investment Recommendation. Also check that the Financial Analyst states all eleven required audit claims or explicitly marks a claim missing: annual total revenue; revenue growth; operating income and operating margin; net income; GAAP diluted EPS; return on average equity; debt to equity; free cash flow; quarter total revenue; quarter total-revenue growth; and quarter GAAP diluted EPS. Respond as one JSON object with keys status (pass or revise), responsible_role (research_analyst, financial_analyst, investment_advisor, or none), feedback, and report. If revision is required, report may be an empty string. If it passes, report must be the complete five-part Markdown report. Do not invent facts.""",
}


def write_audit_template(path: Path, report_name: str) -> None:
    rows = [
        "1. Total revenue, latest fiscal year",
        "2. Revenue growth versus the prior year",
        "3. Operating income and operating margin",
        "4. Net income attributable to the company",
        "5. Diluted earnings per share, GAAP",
        "6. Return on average equity",
        "7. Debt to equity",
        "8. Free cash flow",
        "9. Latest quarter's revenue",
        "10. Quarter's growth versus the same quarter last year",
        "11. Quarter's diluted EPS, GAAP",
    ]
    body = [
        f"# Human report audit: {report_name}", "", "Errors (wrong + unsupported): ",
        "Missing claims: ", "", "Complete this table by hand from the filings. Do not use AI for the marks.", "",
        "| Core claim | Report value | Filing value | Source line/tag and period | Mark: correct/wrong/unsupported/missing |",
        "|---|---:|---:|---|---|",
    ]
    body.extend(f"| {row} |  |  |  |  |" for row in rows)
    body.extend([
        "", "## Other Financial Analyst numbers", "",
        "| Number | Report value | Filing value | Source | Mark |", "|---|---:|---:|---|---|",
        "|  |  |  |  |  |", "", "## Template and recommendation", "",
        "| Check | Mark | Notes |", "|---|---|---|",
        "| All five required sections are present |  |  |",
        "| Recommendation is Buy, Hold, or Sell |  |  |",
        "| Recommendation names one deciding sourced number |  |  |",
        "| Definitions are consistent across company and peers |  |  |", "",
        "Partner-checked claim 1 and mark: ", "", "Partner-checked claim 2 and mark: ", "",
    ])
    path.write_text("\n".join(body), encoding="utf-8")


def run_roles(
    run_dir: Path,
    api_key: str,
    model: str,
    metadata: dict[str, Any],
) -> Path:
    if not api_key or api_key == "paste-here":
        raise ValueError("API_KEY is missing. Put a developer API key in .env.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "OpenAI SDK is not installed. Run: "
            "UV_CACHE_DIR=\"$PWD/.uv-cache\" uv pip install --python .venv/bin/python -r requirements.txt"
        ) from exc

    client = OpenAI(api_key=api_key)
    ten_k = (run_dir / "10-K.txt").read_text(encoding="utf-8")
    release = (run_dir / "earnings_release_EX-99.1.txt").read_text(encoding="utf-8")
    facts = json.loads((run_dir / "facts.json").read_text(encoding="utf-8"))
    ratios = json.loads((run_dir / "ratios.json").read_text(encoding="utf-8"))
    peers = json.loads((run_dir / "peers.json").read_text(encoding="utf-8"))
    release_lines = (run_dir / "release_claim_lines.txt").read_text(encoding="utf-8")
    quarter_claims_path = run_dir / "quarter_claims.json"
    quarter_claims = json.loads(quarter_claims_path.read_text(encoding="utf-8"))

    research_context = {
        "task": "Analyze the business, competitive position, catalysts, and recent developments.",
        "context": {
            "business_section": numbered_excerpt(ten_k, r"item\s+1\.?\s+business", (r"item\s+1a",)),
            "mda_section": numbered_excerpt(ten_k, r"item\s+7\.?", (r"item\s+7a", r"item\s+8")),
            "earnings_release": "\n".join(
                f"L{index + 1}: {line}" for index, line in enumerate(release.splitlines()[:450])
            ),
        },
        "expected_output": "Markdown with cited line numbers and no outside facts",
    }
    research = call_model(
        client, model, "Research Analyst", ROLE_INSTRUCTIONS["research_analyst"], research_context
    )

    financial_context = {
        "task": "Perform statement, ratio, quarter, valuation, and peer analysis. State every one of the eleven course audit claims, or mark it missing when the supplied evidence does not contain it.",
        "context": {
            "facts": facts,
            "ratios": ratios,
            "quarter_claims": quarter_claims,
            "release_lines": release_lines,
            "peers": peers,
        },
        "expected_output": "Markdown; every number sourced; every ratio repeats supplied arithmetic",
    }
    financial = call_model(
        client, model, "Financial Analyst", ROLE_INSTRUCTIONS["financial_analyst"], financial_context
    )

    advisor_context = {
        "task": "Create the thesis and Buy, Hold, or Sell recommendation.",
        "context": {"research_analyst": research, "financial_analyst": financial},
        "expected_output": "Markdown with one deciding sourced number",
    }
    advisor = call_model(
        client, model, "Investment Advisor", ROLE_INSTRUCTIONS["investment_advisor"], advisor_context
    )

    drafts = {
        "research_analyst": research,
        "financial_analyst": financial,
        "investment_advisor": advisor,
    }
    manager_context = {
        "task": "Check and compile the five-part report.",
        "context": {"filings": metadata["filings"], "role_outputs": drafts},
        "expected_output": "JSON with status, responsible_role, feedback, and report",
    }
    manager_output = call_model(
        client, model, "Strategy Manager", ROLE_INSTRUCTIONS["strategy_manager"], manager_context
    )
    review = manager_json(manager_output)

    if review.get("status") == "revise" and review.get("responsible_role") in drafts:
        role_key = review["responsible_role"]
        revision_handoff = {
            "task": "Revise your prior output once using the Strategy Manager feedback.",
            "context": {"prior_output": drafts[role_key], "feedback": review.get("feedback", "")},
            "expected_output": "Corrected Markdown using only the original supplied evidence",
        }
        role_label = role_key.replace("_", " ").title() + " Revision"
        drafts[role_key] = call_model(
            client, model, role_label, ROLE_INSTRUCTIONS[role_key], revision_handoff
        )
        final_context = {
            "task": "Compile the final five-part report after the one allowed revision.",
            "context": {"filings": metadata["filings"], "role_outputs": drafts},
            "expected_output": "JSON with status, responsible_role, feedback, and complete report",
        }
        manager_output = call_model(
            client, model, "Strategy Manager Final Check", ROLE_INSTRUCTIONS["strategy_manager"], final_context
        )
        review = manager_json(manager_output)

    report = str(review.get("report", "")).strip()
    if not report:
        raise RuntimeError(f"Strategy Manager did not compile a report: {review.get('feedback', '')}")
    filing_line = "; ".join(
        f"{name} {filing['accession']}" for name, filing in metadata["filings"].items()
    )
    run_time = metadata["run_time"]
    report_path = run_dir / "equity_research_report.md"
    report_path.write_text(
        f"Filings read: {filing_line}\nRun time: {run_time}\n\n{report}\n\n"
        "This is a learning exercise, not financial advice.\n\n"
        "AI assistance: OpenAI API and Codex. I verified the sources myself; the judgments are mine.\n\n"
        "Any remaining errors are my own.\n",
        encoding="utf-8",
    )
    save_json(run_dir / "role_outputs.json", {**drafts, "manager_review": review})
    write_audit_template(run_dir / "report_audit.md", report_path.name)
    return report_path


class DeskRun:
    def __init__(self, args: argparse.Namespace, env: dict[str, str]) -> None:
        self.args = args
        self.ticker = normalize_ticker(args.ticker)
        self.client = SecClient(env.get("SEC_USER_AGENT", ""))
        self.api_key = env.get("API_KEY", "")
        self.cik = ""
        self.company = ""
        self.submissions: dict[str, Any] = {}
        self.filings: dict[str, Filing] = {}
        self.company_facts: dict[str, Any] = {}
        self.facts: dict[str, Any] = {}
        self.ratios: dict[str, Any] = {}
        self.peers: dict[str, Any] = {}
        self.run_dir: Path | None = None
        self.saved_texts: dict[str, str] = {}
        self.metadata: dict[str, Any] = {}

    def heading(self, step: int, text: str) -> None:
        if self.args.step in {None, step}:
            print(f"\nSTEP {step} - {text}")

    def step1(self, quiet: bool = False) -> None:
        if not quiet:
            self.heading(1, "Resolve ticker to CIK")
        data = self.client.get_json(TICKERS_URL)
        match = next(
            (entry for entry in data.values() if str(entry.get("ticker", "")).upper() == self.ticker),
            None,
        )
        if match is None:
            raise RuntimeError(f"Ticker {self.ticker} not found in SEC company_tickers.json")
        self.cik = str(match["cik_str"]).zfill(10)
        self.company = match["title"]
        if not quiet:
            print(f"  {self.ticker} -> CIK {self.cik} -> {self.company}")

    def step2(self, quiet: bool = False) -> None:
        if not self.cik:
            self.step1(quiet=True)
        if not quiet:
            self.heading(2, "Select latest 10-K, 10-Q, and earnings 8-K")
        self.submissions = self.client.get_json(SUBMISSIONS_URL.format(cik=self.cik))
        self.company = self.submissions.get("name", self.company)
        self.filings = select_filings(self.cik, recent_rows(self.submissions))
        for label, filing in self.filings.items():
            index_bytes = self.client.get_bytes(filing.index_url)
            accepted, release_url = parse_index(index_bytes, filing.index_url)
            if accepted:
                filing.accepted = accepted
            if label == "8-K":
                filing.release_url = release_url
                if not release_url:
                    raise RuntimeError(
                        f"Could not find Exhibit 99.1 on earnings 8-K {filing.accession}"
                    )
            if not quiet:
                suffix = " (Item 2.02)" if label == "8-K" else ""
                print(f"  {label}{suffix}: {filing.accession} | Accepted {filing.accepted}")
                print(f"    {filing.index_url}")

    def step3(self) -> None:
        if not self.filings:
            self.step2(quiet=True)
        self.heading(3, "Download filings and Exhibit 99.1 as plain text")
        self.run_dir = ensure_run_dir(Path(self.args.output_dir), self.company)
        mapping = {"10-K": "10-K.txt", "10-Q": "10-Q.txt", "8-K": "8-K.txt"}
        for label, filename in mapping.items():
            filing = self.filings[label]
            text = html_to_text(self.client.get_bytes(filing.document_url))
            (self.run_dir / filename).write_text(text, encoding="utf-8")
            self.saved_texts[label] = text
            print(f"  saved {self.run_dir / filename}")
        release_url = self.filings["8-K"].release_url
        if not release_url:
            raise RuntimeError("Earnings release URL is missing")
        release = html_to_text(self.client.get_bytes(release_url))
        release_path = self.run_dir / "earnings_release_EX-99.1.txt"
        release_path.write_text(release, encoding="utf-8")
        self.saved_texts["release"] = release
        print(f"  saved {release_path}")

    def step4(self, quiet: bool = False) -> None:
        if not self.filings:
            self.step2(quiet=True)
        if not quiet:
            self.heading(4, "Fetch XBRL company facts for the latest 10-K fiscal year")
        self.company_facts = self.client.get_json(COMPANY_FACTS_URL.format(cik=self.cik))
        fiscal_end = self.filings["10-K"].report_date
        self.facts = extract_facts(self.company_facts, fiscal_end)
        if not quiet:
            print_facts(self.facts)
        if self.run_dir:
            save_json(self.run_dir / "facts.json", self.facts)

    def step5(self, quiet: bool = False) -> None:
        if not self.facts:
            self.step4(quiet=True)
        if not quiet:
            self.heading(5, "Calculate ratios in code")
        self.ratios = calculate_ratios(self.facts, self.args.price)
        if not quiet:
            print_ratios(self.ratios)
        if self.run_dir:
            save_json(self.run_dir / "ratios.json", self.ratios)

    def step6(self) -> None:
        if not self.saved_texts:
            self.step3()
        self.heading(6, "Find quarterly revenue and diluted-EPS lines in Exhibit 99.1")
        lines = release_claim_lines(self.saved_texts["release"])
        if not lines:
            print("  No matching release lines found; inspect the saved release manually.")
        else:
            for line in lines:
                print(f"  {line}")
        if self.run_dir:
            (self.run_dir / "release_claim_lines.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            quarter_claims = release_quarter_claims(self.saved_texts["release"])
            save_json(self.run_dir / "quarter_claims.json", quarter_claims)
            print(
                "  quarter total-revenue growth arithmetic: "
                f"{quarter_claims['quarter_revenue_growth_arithmetic']}"
            )

    def step7(self) -> None:
        self.heading(7, "Read peer facts and compute operating margin on total revenue")
        peers = [normalize_ticker(value) for value in self.args.peers.split(",") if value.strip()]
        results: dict[str, Any] = {}
        for ticker in peers:
            ticker_data = self.client.get_json(TICKERS_URL)
            match = next(
                (entry for entry in ticker_data.values() if str(entry.get("ticker", "")).upper() == ticker),
                None,
            )
            if not match:
                print(f"  {ticker}: ticker not found")
                continue
            cik = str(match["cik_str"]).zfill(10)
            submissions = self.client.get_json(SUBMISSIONS_URL.format(cik=cik))
            filings = select_filings(cik, recent_rows(submissions))
            peer_company_facts = self.client.get_json(COMPANY_FACTS_URL.format(cik=cik))
            peer_facts = extract_facts(peer_company_facts, filings["10-K"].report_date)
            peer_ratios = calculate_ratios(peer_facts, None)
            results[ticker] = {
                "company": submissions.get("name", match["title"]),
                "latest_10-K": asdict(filings["10-K"]),
                "facts": peer_facts,
                "operating_margin": peer_ratios["operating_margin"],
            }
            revenue = value_of(peer_facts, "total_revenue")
            operating_income = value_of(peer_facts, "operating_income")
            margin = peer_ratios["operating_margin"]["value"]
            print(
                f"  {ticker} | FY end {peer_facts['fiscal_year_end']} | "
                f"revenue={format_number(revenue)} | operating income={format_number(operating_income)} | "
                f"operating margin={'MISSING' if margin is None else f'{margin:.4%}'}"
            )
            print(f"    revenue tag={peer_facts['concepts']['total_revenue']['tag']} definition=total revenue")
        self.peers = results
        if self.run_dir:
            save_json(self.run_dir / "peers.json", results)

    def finalize(self) -> None:
        if not self.run_dir:
            return
        self.metadata = {
            "ticker": self.ticker,
            "company": self.company,
            "cik": self.cik,
            "run_time": datetime.now(timezone.utc).isoformat(),
            "price": self.args.price,
            "filings": {name: asdict(filing) for name, filing in self.filings.items()},
        }
        save_json(self.run_dir / "run_metadata.json", self.metadata)

    def run_all(self) -> None:
        self.step1()
        self.step2()
        self.step3()
        self.step4()
        self.step5()
        self.step6()
        self.step7()
        self.finalize()
        if not self.run_dir:
            raise RuntimeError("Run folder was not created")
        print(f"\nSaved run folder: {self.run_dir}")
        if self.args.report:
            report_path = run_roles(
                self.run_dir, self.api_key, self.args.model, self.metadata
            )
            print(f"Saved report: {report_path}")
            print(f"Human audit template: {self.run_dir / 'report_audit.md'}")

    def run_one(self, step: int) -> None:
        methods = {
            1: self.step1,
            2: self.step2,
            3: self.step3,
            4: self.step4,
            5: self.step5,
            6: self.step6,
            7: self.step7,
        }
        methods[step]()
        self.finalize()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", help="SEC ticker symbol")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers")
    parser.add_argument("--price", type=float, help="Share price used only for P/E")
    parser.add_argument("--step", type=int, choices=range(1, 8), help="Run one step only")
    parser.add_argument("--report", action="store_true", help="Run the four model roles")
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model for all roles")
    parser.add_argument("--output-dir", default="runs", help="Saved-run parent folder")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.step and args.report:
        raise SystemExit("--step and --report cannot be used together")
    project_dir = Path(__file__).resolve().parent
    env = load_env(project_dir / ".env")
    try:
        run = DeskRun(args, env)
        if args.step:
            run.run_one(args.step)
        else:
            run.run_all()
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
