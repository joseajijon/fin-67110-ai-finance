#!/usr/bin/env python3
"""Fixed-order FIN 67110 agent team built with the OpenAI Agents SDK."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from closes_reader import CloseRecord, last_close_before
from equity_desk import DeskRun, load_env, numbered_excerpt
from verifier import verify_report


NODE_ORDER = (
    "Steps",
    "Research Analyst",
    "Financial Analyst",
    "Investment Advisor",
    "Strategy Manager",
    "Verifier",
)
REQUIRED_SECTIONS = (
    "Overview",
    "Market Positioning and Growth Outlook",
    "Valuation Insights",
    "Future Developments and Strategic Recommendations",
    "Investment Recommendation",
)


def _save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _role_text(project_dir: Path, key: str) -> str:
    return (project_dir / "roles" / f"{key}.md").read_text(encoding="utf-8")


def _run_agent(name: str, instructions: str, state: dict[str, Any], model: str) -> str:
    try:
        from agents import Agent, Runner
    except ImportError as exc:
        raise RuntimeError(
            "The OpenAI Agents SDK is not installed. Run: "
            "UV_CACHE_DIR=\"$PWD/.uv-cache\" uv pip install --python .venv/bin/python -r requirements.txt"
        ) from exc
    agent = Agent(name=name, instructions=instructions, model=model)
    result = Runner.run_sync(agent, json.dumps(state, ensure_ascii=False))
    output = str(result.final_output or "").strip()
    if not output:
        raise RuntimeError(f"{name} returned an empty output")
    return output


def _node(
    run_dir: Path,
    index: int,
    name: str,
    instructions: str,
    state: dict[str, Any],
    model: str,
    emit: Callable[[str], None],
    attempt: int = 1,
) -> str:
    emit(name)
    stem = f"node_{index:02d}_{name.lower().replace(' ', '_')}"
    if attempt > 1:
        stem += f"_attempt_{attempt}"
    _save_json(run_dir / f"{stem}_input.json", state)
    output = _run_agent(name, instructions, state, model)
    (run_dir / f"{stem}_output.md").write_text(output + "\n", encoding="utf-8")
    return output


def _semantic_verifier(
    run_dir: Path,
    project_dir: Path,
    model: str,
    emit: Callable[[str], None],
) -> None:
    verified_path, rows = verify_report(run_dir)
    state = {
        "task": "Check the period and definition semantics of the deterministic verifier marks.",
        "context": {
            "deterministic_marks": rows,
            "verified_report": verified_path.read_text(encoding="utf-8"),
        },
        "expected_output": "Short notes. Keep exact code comparisons unchanged.",
    }
    try:
        notes = _node(
            run_dir, 6, "Verifier", _role_text(project_dir, "verifier"), state, model, emit
        )
    except Exception as exc:
        # The exact code checks remain the verifier's authoritative marks. Record a
        # provider or credit failure instead of losing the required seeded test.
        notes = (
            "Semantic model subcheck unavailable. The Verifier node still ran its "
            "exact XBRL, line, and arithmetic checks and saved their marks.\n\n"
            f"Provider error: {type(exc).__name__}: {exc}"
        )
        (run_dir / "node_06_verifier_output.md").write_text(notes + "\n", encoding="utf-8")
    (run_dir / "verifier_semantic_review.md").write_text(notes + "\n", encoding="utf-8")


def verify_only(
    run_dir: Path,
    project_dir: Path,
    api_key: str,
    model: str,
    emit: Callable[[str], None] = print,
) -> Path:
    if not api_key:
        raise RuntimeError("API_KEY is missing from .env")
    os.environ["OPENAI_API_KEY"] = api_key
    _semantic_verifier(run_dir, project_dir, model, emit)
    return run_dir / "verified_report.md"


def run_team(
    ticker: str,
    peers: str,
    filed: str | None,
    model: str,
    output_dir: str = "runs",
    emit: Callable[[str], None] = print,
) -> Path:
    project_dir = Path(__file__).resolve().parent
    env = load_env(project_dir / ".env")
    api_key = env.get("API_KEY", "")
    if not api_key:
        raise RuntimeError("API_KEY is missing from .env")
    os.environ["OPENAI_API_KEY"] = api_key

    emit("Steps")
    desk_args = argparse.Namespace(
        ticker=ticker,
        peers=peers,
        price=None,
        step=None,
        report=False,
        model=model,
        output_dir=output_dir,
    )
    desk = DeskRun(desk_args, env)
    desk.step1()
    desk.step2()
    filing_time = filed or desk.filings["8-K"].accepted.replace(" ", "T")
    close = last_close_before(ticker, filing_time, env)
    if isinstance(close, CloseRecord):
        desk.args.price = close.close
        emit(f"Market close: {close.close} on {close.date} from {close.source}")
        close_state: dict[str, Any] | str = {
            "ticker": close.ticker,
            "date": close.date,
            "close": close.close,
            "source": close.source,
        }
    else:
        emit("Market close: not available; the agent team will finish without P/E.")
        close_state = "not available"
    desk.step3()
    desk.step4()
    desk.step5()
    desk.step6()
    desk.step7()
    desk.finalize()
    steps_state = {
        "ticker": ticker,
        "peers": peers,
        "filing_time_eastern": filing_time,
        "market_close": close_state,
    }
    if desk.run_dir is None:
        raise RuntimeError("The steps did not create a run folder")
    run_dir = desk.run_dir
    desk.metadata["filing_time_eastern"] = filing_time
    desk.metadata["market_close"] = close_state
    _save_json(run_dir / "run_metadata.json", desk.metadata)
    _save_json(run_dir / "node_01_steps_input.json", steps_state)
    _save_json(run_dir / "node_01_steps_output.json", desk.metadata)

    ten_k = (run_dir / "10-K.txt").read_text(encoding="utf-8")
    release = (run_dir / "earnings_release_EX-99.1.txt").read_text(encoding="utf-8")
    research_state = {
        "task": "Write the business, position, catalyst, and recent-development analysis.",
        "context": {
            "10-K business section": numbered_excerpt(ten_k, r"item\s+1\.?\s+business", (r"item\s+1a",)),
            "10-K MD&A": numbered_excerpt(ten_k, r"item\s+7\.?(?:\s|$)", (r"item\s+7a", r"item\s+8")),
            "earnings release": "\n".join(
                f"L{i + 1}: {line}" for i, line in enumerate(release.splitlines()[:450])
            ),
        },
        "expected_output": "Sourced Markdown ending in one Insight line.",
    }
    research = _node(
        run_dir, 2, "Research Analyst", _role_text(project_dir, "research_analyst"),
        research_state, model, emit,
    )

    financial_state = {
        "task": "Write the financial and valuation analysis with all 11 fixed claims.",
        "context": {
            name: _read(run_dir / name)
            for name in ("facts.json", "ratios.json", "quarter_claims.json", "peers.json")
        },
        "release_claim_lines": (run_dir / "release_claim_lines.txt").read_text(encoding="utf-8"),
        "expected_output": "Sourced Markdown ending in one Insight line.",
    }
    financial = _node(
        run_dir, 3, "Financial Analyst", _role_text(project_dir, "financial_analyst"),
        financial_state, model, emit,
    )

    advisor_state = {
        "task": "Write the thesis and Buy, Hold, or Sell recommendation.",
        "context": {"research_analyst": research, "financial_analyst": financial},
        "expected_output": "Sourced Markdown ending in one Insight line.",
    }
    advisor = _node(
        run_dir, 4, "Investment Advisor", _role_text(project_dir, "investment_advisor"),
        advisor_state, model, emit,
    )

    manager_state = {
        "task": "Compile the complete five-section report. Preserve the three Insight lines.",
        "context": {
            "filings": desk.metadata["filings"],
            "research_analyst": research,
            "financial_analyst": financial,
            "investment_advisor": advisor,
        },
        "expected_output": "A complete Markdown report with exactly the five required H2 sections.",
    }
    report = _node(
        run_dir, 5, "Strategy Manager", _role_text(project_dir, "strategy_manager"),
        manager_state, model, emit,
    )
    missing = [section for section in REQUIRED_SECTIONS if f"## {section}" not in report]
    insight_count = len([line for line in report.splitlines() if line.strip().startswith("Insight:")])
    if missing or insight_count < 3:
        retry_state = dict(manager_state)
        retry_state["task"] = (
            "This is the one allowed retry. Fix only the failed report contract. "
            f"Missing sections: {missing}. Insight-line count: {insight_count}; required: 3."
        )
        report = _node(
            run_dir, 5, "Strategy Manager", _role_text(project_dir, "strategy_manager"),
            retry_state, model, emit, attempt=2,
        )
    if any(f"## {section}" not in report for section in REQUIRED_SECTIONS):
        raise RuntimeError("Strategy Manager did not return all five required sections after one retry")

    filing_line = "; ".join(
        f"{name} {filing['accession']}" for name, filing in desk.metadata["filings"].items()
    )
    report_path = run_dir / "equity_research_report.md"
    report_path.write_text(
        f"Filings read: {filing_line}\n\n{report}\n\n"
        "This is a learning exercise, not financial advice.\n\n"
        "AI assistance: OpenAI Agents SDK and Codex. I verified the sources myself; the judgments are mine.\n\n"
        "Any remaining errors are my own.\n",
        encoding="utf-8",
    )
    _semantic_verifier(run_dir, project_dir, model, emit)
    return run_dir


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_eps_error(source_run: Path, destination: Path) -> Path:
    """Copy a run and seed the Lab 04 one-dollar annual diluted-EPS error."""
    if destination.exists():
        raise RuntimeError(f"Destination already exists: {destination}")
    shutil.copytree(source_run, destination)
    facts = _read(destination / "facts.json")
    eps = float(facts["concepts"]["diluted_eps"]["current"]["value"])
    wrong = eps + 1.0
    report_path = destination / "equity_research_report.md"
    report = report_path.read_text(encoding="utf-8")
    report = re_sub_claim(report, "Annual diluted EPS, GAAP", wrong)
    report_path.write_text(report, encoding="utf-8")
    for stale in ("verified_report.md", "verifier_marks.json", "verifier_semantic_review.md"):
        path = destination / stale
        if path.exists():
            path.unlink()
    return destination


def re_sub_claim(report: str, label: str, value: float) -> str:
    import re
    replacement = (
        f"{label}: ${value:.2f}. Source claimed in seeded copy: "
        f"Diluted | $ | {value:.2f} |."
    )
    pattern = rf"^\s*[-*]?\s*{re.escape(label)}\s*:.*$"
    if re.search(pattern, report, flags=re.IGNORECASE | re.MULTILINE):
        return re.sub(pattern, replacement, report, count=1, flags=re.IGNORECASE | re.MULTILINE)
    return report.rstrip() + "\n\n" + replacement + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", help="SEC ticker for a complete agent-team run")
    parser.add_argument("--peers", default="", help="Comma-separated peer tickers")
    parser.add_argument(
        "--filed",
        help="Override the EDGAR acceptance time with YYYY-MM-DDTHH:MM:SS Eastern",
    )
    parser.add_argument("--model", default="gpt-5-mini", help="OpenAI model for role nodes")
    parser.add_argument("--output-dir", default="runs", help="Parent folder for saved runs")
    parser.add_argument("--verify-only", type=Path, help="Run only the Verifier on a saved run")
    parser.add_argument("--seed-eps-error", nargs=2, metavar=("SOURCE_RUN", "DESTINATION"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(__file__).resolve().parent
    env = load_env(project_dir / ".env")
    if args.seed_eps_error:
        path = seed_eps_error(Path(args.seed_eps_error[0]), Path(args.seed_eps_error[1]))
        print(path)
        return 0
    if args.verify_only:
        path = verify_only(args.verify_only, project_dir, env.get("API_KEY", ""), args.model)
        print(path)
        return 0
    if not args.ticker:
        raise SystemExit("Give a ticker, --verify-only RUN, or --seed-eps-error SOURCE DESTINATION")
    path = run_team(args.ticker, args.peers, args.filed, args.model, args.output_dir)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

