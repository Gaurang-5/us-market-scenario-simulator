"""Run final checks across historical, context, response, and draft tables."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from build_model_tables import PROCESSED, TICKERS, load_etfs
from validate_drafts import validate_events, validate_scenarios


ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "data" / "drafts"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def check_months(name: str, first: str) -> dict[str, object]:
    data = rows(PROCESSED / name)
    months = [row["month"] for row in data]
    if not data or months[0] != first or months != sorted(set(months)):
        raise ValueError(f"Invalid month order in {name}")
    for previous, current in zip(months, months[1:]):
        previous_index = int(previous[:4]) * 12 + int(previous[5:7])
        current_index = int(current[:4]) * 12 + int(current[5:7])
        if current_index != previous_index + 1:
            raise ValueError(f"Month gap in {name}: {previous} to {current}")
    return {"rows": len(data), "first": months[0], "last": months[-1]}


def check_date_table(name: str, first: str) -> dict[str, object]:
    data = rows(PROCESSED / name)
    dates = [row["date"] for row in data]
    if not data or dates[0] != first or dates != sorted(set(dates)):
        raise ValueError(f"Invalid dates in {name}")
    for day in dates:
        date.fromisoformat(day)
    return {"rows": len(data), "first": dates[0], "last": dates[-1]}


def main() -> None:
    report = {"layers": {
        "shiller": check_months("shiller_monthly_1900_present.csv", "1900-01"),
        "french_market": check_date_table("french_market_daily_1926_present.csv", "1926-07-01"),
        "french_industries": check_date_table("french_10_industries_daily_1926_present.csv", "1926-07-01"),
        "gpr": check_months("gpr_monthly_1900_present.csv", "1900-01"),
        "housing": check_months("housing_starts_monthly_1959_present.csv", "1959-01"),
    }}
    market_dates = [row["date"] for row in rows(PROCESSED / "french_market_daily_1926_present.csv")]
    industry_dates = [row["date"] for row in rows(PROCESSED / "french_10_industries_daily_1926_present.csv")]
    if market_dates != industry_dates:
        raise ValueError("French market and industry calendars differ")
    gpr = rows(PROCESSED / "gpr_monthly_1900_present.csv")
    if any(not row["gpr_historical"] for row in gpr):
        raise ValueError("Historical GPR has missing months")
    first_modern = next(row["month"] for row in gpr if row["gpr_modern"])
    if first_modern != "1985-01":
        raise ValueError(f"Modern GPR begins unexpectedly at {first_modern}")
    housing = rows(PROCESSED / "housing_starts_monthly_1959_present.csv")
    if any(not row["starts_nsa_thousands"] or not row["starts_sa_annual_rate_thousands"]
           for row in housing):
        raise ValueError("Housing starts has missing months")
    etfs, calendar = load_etfs()
    report["layers"]["etfs"] = {"rows": sum(len(items) for items in etfs.values()),
                                   "dates_per_ticker": len(calendar),
                                   "first": calendar[0], "last": calendar[-1]}
    response = rows(PROCESSED / "scenario_response_daily.csv")
    if len(response) != 6 * len(calendar):
        raise ValueError("Response table has an unexpected row count")
    lookup = {(row["shock_date"], row["ticker"]): row for row in response}
    if len(lookup) != len(response):
        raise ValueError("Duplicate response rows")
    if set(ticker for _, ticker in lookup) != set(TICKERS):
        raise ValueError("Missing response ticker")
    for key, row in lookup.items():
        if row["split"] in ("train", "validation", "test"):
            if any(not row[field] for field in ("oil_change_percent", "treasury_10y_change_basis_points",
                                                "return_1d", "return_5d", "return_20d")):
                raise ValueError(f"Model row has missing data: {key}")
        if row["split"] == "train" and row["outcome_end_date_20d"] > "2018-12-31":
            raise ValueError(f"Train outcome crosses boundary: {key}")
        if row["split"] == "validation" and row["outcome_end_date_20d"] > "2022-12-31":
            raise ValueError(f"Validation outcome crosses boundary: {key}")
        for field in ("return_1d", "return_5d", "return_20d"):
            if row[field] and not math.isfinite(float(row[field])):
                raise ValueError(f"Nonfinite outcome: {key}")
    sample_dates = (("SPY", "1999-01-05"), ("SPY", "1999-03-19"),
                    ("XLE", "2025-12-05"))
    checks = []
    positions = {day: index for index, day in enumerate(calendar)}
    for ticker, day in sample_dates:
        index = positions[day]
        expected = float(etfs[ticker][index]["adj_close"]) / float(etfs[ticker][index - 1]["adj_close"]) - 1
        actual = float(lookup[(day, ticker)]["return_1d"])
        if abs(expected - actual) > 1e-12:
            raise ValueError(f"Return mismatch for {ticker} {day}")
        checks.append({"ticker": ticker, "date": day, "return_1d": actual})
    fdic = rows(PROCESSED / "fdic_failed_banks_2000_present.csv")
    if len({(row["closing_date"], row["fdic_cert"]) for row in fdic}) != len(fdic):
        raise ValueError("Duplicate FDIC event")
    scenarios = rows(DRAFTS / "scenario_examples.csv")
    events = rows(DRAFTS / "event_catalog_draft.csv")
    scenario_audit = validate_scenarios(scenarios)
    event_audit = validate_events(events)
    report["response"] = {"rows": len(response), "split_rows": dict(Counter(row["split"] for row in response)),
                          "hand_checked": checks}
    report["fdic"] = {"rows": len(fdic), "first": fdic[0]["closing_date"],
                      "last": fdic[-1]["closing_date"]}
    report["drafts"] = {"scenarios": scenario_audit, "events": event_audit}
    metrics = rows(PROCESSED / "baseline_metrics.csv")
    if len(metrics) != 36 or any(not 0 <= float(row["p10_p90_coverage"]) <= 1 for row in metrics):
        raise ValueError("Invalid baseline metrics")
    report["baseline"] = {"metric_rows": len(metrics), "test_spy": [row for row in metrics
                           if row["split"] == "test" and row["ticker"] == "SPY"]}
    (PROCESSED / "final_data_audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"layers": report["layers"], "response": report["response"],
                      "fdic": report["fdic"], "drafts": report["drafts"]}, indent=2))


if __name__ == "__main__":
    main()
