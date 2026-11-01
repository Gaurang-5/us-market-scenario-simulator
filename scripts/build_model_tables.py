"""Validate source tables and build reproducible daily ETF response rows."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TICKERS = ("SPY", "XLF", "XLE", "XLK", "XLV", "XLY")
TRAIN_END = "2018-12-31"
VALIDATION_END = "2022-12-31"
FIELDS = [
    "shock_date", "ticker", "previous_etf_date", "oil_previous_date", "oil_price_usd",
    "oil_previous_price_usd", "oil_change_usd", "oil_change_percent",
    "treasury_10y_previous_date", "treasury_10y_percent", "treasury_10y_previous_percent",
    "treasury_10y_change_basis_points", "vix_prior_date", "vix_prior_level",
    "return_1d", "return_5d", "return_20d", "outcome_end_date_5d",
    "outcome_end_date_20d", "split",
]


def read_csv(name: str) -> list[dict[str, str]]:
    path = PROCESSED / name
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Empty table: {name}")
    return rows


def finite(value: str, *, positive: bool = False) -> float:
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"Invalid numeric value: {value}")
    return result


def load_etfs() -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv("etf_prices_daily_1999_present.csv"):
        ticker, day = row["ticker"], row["date"]
        date.fromisoformat(day)
        if ticker not in TICKERS:
            raise ValueError(f"Unexpected ETF: {ticker}")
        finite(row["close"], positive=True)
        finite(row["adj_close"], positive=True)
        if finite(row["volume"]) < 0:
            raise ValueError(f"Negative volume: {ticker} {day}")
        grouped[ticker].append(row)
    if set(grouped) != set(TICKERS):
        raise ValueError(f"Expected six ETFs, got {sorted(grouped)}")
    calendar = [row["date"] for row in grouped["SPY"]]
    if calendar != sorted(set(calendar)):
        raise ValueError("SPY dates are duplicated or unsorted")
    for ticker in TICKERS:
        if [row["date"] for row in grouped[ticker]] != calendar:
            raise ValueError(f"{ticker} has a different trading calendar")
    return dict(grouped), calendar


def factor_changes(name: str) -> dict[str, tuple[str, float, str, float, bool]]:
    result: dict[str, tuple[str, float, str, float, bool]] = {}
    previous: tuple[str, float] | None = None
    seen: set[str] = set()
    last_day = ""
    for row in read_csv(name):
        day = row["date"]
        date.fromisoformat(day)
        if day in seen or day <= last_day:
            raise ValueError(f"Duplicate or unsorted {name} date: {day}")
        seen.add(day)
        last_day = day
        if not row["value"]:
            continue
        current = finite(row["value"])
        if previous:
            recent = (date.fromisoformat(day) - date.fromisoformat(previous[0])).days <= 7
            result[day] = (day, current, previous[0], previous[1], recent)
        previous = day, current
    return result


def prior_vix(calendar: list[str]) -> dict[str, tuple[str, float] | None]:
    values = [(row["date"], finite(row["value"])) for row in read_csv("fred_VIXCLS.csv") if row["value"]]
    if [day for day, _ in values] != sorted(set(day for day, _ in values)):
        raise ValueError("VIX dates are duplicated or unsorted")
    output: dict[str, tuple[str, float] | None] = {}
    cursor = 0
    latest: tuple[str, float] | None = None
    for day in calendar:
        while cursor < len(values) and values[cursor][0] < day:
            latest = values[cursor]
            cursor += 1
        age = (date.fromisoformat(day) - date.fromisoformat(latest[0])).days if latest else 999
        output[day] = latest if age <= 7 else None
    return output


def split_for(day: str, end_20d: str, complete: bool) -> str:
    if not complete:
        return "incomplete"
    if day <= TRAIN_END:
        return "train" if end_20d <= TRAIN_END else "embargo"
    if day <= VALIDATION_END:
        return "validation" if end_20d <= VALIDATION_END else "embargo"
    return "test"


def build_rows(etfs: dict[str, list[dict[str, str]]], calendar: list[str],
               oil: dict[str, tuple[str, float, str, float, bool]],
               yield_10y: dict[str, tuple[str, float, str, float, bool]],
               vix: dict[str, tuple[str, float] | None]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, day in enumerate(calendar):
        oil_record = oil.get(day)
        yield_record = yield_10y.get(day)
        vix_record = vix[day]
        oil_change = oil_record[1] - oil_record[3] if oil_record and oil_record[4] else None
        oil_pct = (100 * oil_change / oil_record[3]
                   if oil_change is not None and oil_record[1] > 0 and oil_record[3] > 0 else None)
        rate_bp = round(100 * (yield_record[1] - yield_record[3]), 6) if yield_record and yield_record[4] else None
        end_5d = calendar[index + 4] if index + 4 < len(calendar) else ""
        end_20d = calendar[index + 19] if index + 19 < len(calendar) else ""
        complete = index > 0 and bool(end_20d) and oil_pct is not None and rate_bp is not None
        split = split_for(day, end_20d, complete)
        for ticker in TICKERS:
            history = etfs[ticker]
            previous_close = finite(history[index - 1]["adj_close"]) if index > 0 else None
            returns = [
                (finite(history[index + offset]["adj_close"]) / previous_close - 1
                 if previous_close and index + offset < len(history) else "")
                for offset in (0, 4, 19)
            ]
            rows.append({
                "shock_date": day, "ticker": ticker,
                "previous_etf_date": calendar[index - 1] if index > 0 else "",
                "oil_previous_date": oil_record[2] if oil_record else "",
                "oil_price_usd": oil_record[1] if oil_record else "",
                "oil_previous_price_usd": oil_record[3] if oil_record else "",
                "oil_change_usd": oil_change if oil_change is not None else "",
                "oil_change_percent": oil_pct if oil_pct is not None else "",
                "treasury_10y_previous_date": yield_record[2] if yield_record else "",
                "treasury_10y_percent": yield_record[1] if yield_record else "",
                "treasury_10y_previous_percent": yield_record[3] if yield_record else "",
                "treasury_10y_change_basis_points": rate_bp if rate_bp is not None else "",
                "vix_prior_date": vix_record[0] if vix_record else "",
                "vix_prior_level": vix_record[1] if vix_record else "",
                "return_1d": returns[0], "return_5d": returns[1], "return_20d": returns[2],
                "outcome_end_date_5d": end_5d, "outcome_end_date_20d": end_20d,
                "split": split,
            })
    return rows


def main() -> None:
    etfs, calendar = load_etfs()
    oil = factor_changes("fred_DCOILWTICO.csv")
    yield_10y = factor_changes("fred_DGS10.csv")
    vix = prior_vix(calendar)
    rows = build_rows(etfs, calendar, oil, yield_10y, vix)
    output = PROCESSED / "scenario_response_daily.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    counts = Counter(row["split"] for row in rows)
    missing = {field: sum(row[field] == "" for row in rows)
               for field in ("oil_change_percent", "treasury_10y_change_basis_points",
                             "vix_prior_level", "return_1d", "return_5d", "return_20d")}
    source_names = ("etf_prices_daily_1999_present.csv", "fred_DCOILWTICO.csv",
                    "fred_DGS10.csv", "fred_VIXCLS.csv")
    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows), "trading_dates": len(calendar), "tickers": list(TICKERS),
        "first_date": calendar[0], "last_date": calendar[-1],
        "split_rows": dict(sorted(counts.items())), "missing_rows": missing,
        "input_sha256": {name: hashlib.sha256((PROCESSED / name).read_bytes()).hexdigest()
                         for name in source_names},
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "label_definition": "Adjusted ETF close before shock day to adjusted close at t, t+4, or t+19 trading rows.",
        "split_definition": "Train through 2018, validation 2019-2022, test 2023 onward; rows whose 20-day outcome crosses a split boundary are embargoed.",
        "notes": ["Same-day oil and yield changes describe a conditional response, not a pre-event forecast.",
                  "Monthly housing and GPR are not joined to daily rows without release-date alignment.",
                  "Oil percentage change is blank when either WTI price is nonpositive or the previous observation is over seven calendar days old."]}
    (PROCESSED / "scenario_response_quality.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("rows", "trading_dates", "first_date", "last_date", "split_rows", "missing_rows")}, indent=2))


if __name__ == "__main__":
    main()
