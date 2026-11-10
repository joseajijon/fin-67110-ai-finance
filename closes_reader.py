#!/usr/bin/env python3
"""Read official daily closes from LSEG Workspace or a user export."""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from equity_desk import load_env, normalize_ticker


EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CloseRecord:
    ticker: str
    date: str
    close: float
    source: str


def _parse_date(value: str) -> date:
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned).date()
    except ValueError:
        for pattern in ("%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y"):
            try:
                return datetime.strptime(cleaned, pattern).date()
            except ValueError:
                continue
    raise ValueError(f"Unsupported date: {value!r}")


def parse_eastern_datetime(value: str) -> datetime:
    cleaned = value.strip().replace(" ", "T", 1).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=EASTERN)
    return parsed.astimezone(EASTERN)


def _column(fieldnames: Iterable[str], choices: tuple[str, ...]) -> str | None:
    by_normalized = {
        "".join(character for character in name.lower() if character.isalnum()): name
        for name in fieldnames
    }
    for choice in choices:
        normalized = "".join(character for character in choice.lower() if character.isalnum())
        if normalized in by_normalized:
            return by_normalized[normalized]
    return None


def _export_closes(path: Path, ticker: str, start: date, end: date) -> list[CloseRecord]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        reader = csv.DictReader(handle, dialect=dialect)
        fields = reader.fieldnames or []
        date_field = _column(fields, ("date", "trade date", "pricing date", "datetime"))
        close_field = _column(
            fields,
            ("close", "close price", "price close", "TR.PriceClose", "TR.ClosePrice"),
        )
        ticker_field = _column(fields, ("ticker", "symbol", "instrument", "ric"))
        if not date_field or not close_field:
            raise ValueError("The export needs a date column and a close-price column.")
        records: list[CloseRecord] = []
        for row in reader:
            if ticker_field and row.get(ticker_field, "").strip().upper() != ticker:
                continue
            day = _parse_date(row.get(date_field, ""))
            if not start <= day <= end:
                continue
            raw_close = row.get(close_field, "").replace(",", "").replace("$", "").strip()
            if not raw_close:
                continue
            records.append(
                CloseRecord(ticker=ticker, date=day.isoformat(), close=float(raw_close), source=f"export:{path}")
            )
    return sorted(records, key=lambda record: record.date)


def _ric_for(ticker: str, env: dict[str, str]) -> str:
    raw = env.get("LSEG_RIC_MAP", "").strip()
    if not raw:
        return ticker
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LSEG_RIC_MAP must be a JSON object, for example {\"MSFT\":\"MSFT.O\"}.") from exc
    return str(mapping.get(ticker, ticker))


def _lseg_closes(env: dict[str, str], ticker: str, start: date, end: date) -> list[CloseRecord]:
    app_key = env.get("LSEG_APP_KEY", "").strip()
    if not app_key:
        return []
    try:
        import lseg.data as ld
    except ImportError as exc:
        raise RuntimeError("lseg-data is not installed. Install the project requirements.") from exc

    ric = _ric_for(ticker, env)
    session = ld.session.desktop.Definition(app_key=app_key).get_session()
    try:
        session.open()
        ld.session.set_default(session)
        frame = ld.get_history(
            universe=ric,
            fields=["TR.ClosePrice"],
            interval="1D",
            start=start.isoformat(),
            end=end.isoformat(),
        )
    finally:
        session.close()
    if frame is None or frame.empty:
        return []
    flat = frame.reset_index()
    date_column = next(
        (column for column in flat.columns if "date" in str(column).lower() or "time" in str(column).lower()),
        flat.columns[0],
    )
    close_column = next(
        (column for column in flat.columns if "close" in str(column).lower()),
        None,
    )
    if close_column is None:
        return []
    records: list[CloseRecord] = []
    for _, row in flat.iterrows():
        if row[close_column] is None:
            continue
        day = _parse_date(str(row[date_column]))
        records.append(
            CloseRecord(ticker=ticker, date=day.isoformat(), close=float(row[close_column]), source=f"LSEG:{ric}:TR.ClosePrice")
        )
    return sorted(records, key=lambda record: record.date)


def official_daily_closes(
    ticker: str,
    start: str | date,
    end: str | date,
    env: dict[str, str] | None = None,
) -> list[CloseRecord] | str:
    """Return official daily closes between two inclusive dates, or 'not available'."""
    symbol = normalize_ticker(ticker)
    start_date = _parse_date(start) if isinstance(start, str) else start
    end_date = _parse_date(end) if isinstance(end, str) else end
    if start_date > end_date:
        raise ValueError("The start date must not be after the end date.")
    values = dict(env or os.environ)
    export_path = values.get("LSEG_EXPORT_PATH", "").strip()
    records = _export_closes(Path(export_path).expanduser(), symbol, start_date, end_date) if export_path else []
    if not records:
        records = _lseg_closes(values, symbol, start_date, end_date)
    return records if records else "not available"


def last_close_before(
    ticker: str,
    filed_at: str | datetime,
    env: dict[str, str] | None = None,
) -> CloseRecord | str:
    """Return the last official close before a filing time; a close occurs at 4:00 PM Eastern."""
    filed = parse_eastern_datetime(filed_at) if isinstance(filed_at, str) else filed_at.astimezone(EASTERN)
    eligible_day = filed.date() if filed.timetz().replace(tzinfo=None) > time(16, 0) else date.fromordinal(filed.date().toordinal() - 1)
    start = date.fromordinal(eligible_day.toordinal() - 14)
    records = official_daily_closes(ticker, start, eligible_day, env)
    if records == "not available":
        return "not available"
    eligible = [record for record in records if _parse_date(record.date) <= eligible_day]
    return max(eligible, key=lambda record: record.date) if eligible else "not available"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--filed", help="Filing time in YYYY-MM-DDTHH:MM:SS Eastern")
    args = parser.parse_args()
    env = load_env(Path(__file__).with_name(".env"))
    if args.filed:
        result = last_close_before(args.ticker, args.filed, env)
        print("not available" if result == "not available" else json.dumps(asdict(result), indent=2))
        return 0
    if not args.start or not args.end:
        parser.error("Give --filed, or give both --start and --end.")
    result = official_daily_closes(args.ticker, args.start, args.end, env)
    print("not available" if result == "not available" else json.dumps([asdict(item) for item in result], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

