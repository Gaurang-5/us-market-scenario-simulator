"""Check draft labels and event timing without claiming human review."""

from __future__ import annotations

import csv
import math
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "data" / "drafts"
HORIZONS = {1, 5, 20}
TICKERS = {"SPY", "XLF", "XLE", "XLK", "XLV", "XLY"}
OIL_PATTERN = re.compile(r"WTI oil (rises|falls) (\d+(?:\.\d+)?) percent", re.I)
YIELD_PATTERN = re.compile(r"US 10-year Treasury yield (rises|falls) (\d+(?:\.\d+)?) basis points", re.I)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def stated_change(text: str, pattern: re.Pattern[str], unchanged: str) -> float | None:
    match = pattern.search(text)
    if match:
        magnitude = float(match.group(2))
        return magnitude if match.group(1).lower() == "rises" else -magnitude
    if unchanged.lower() in text.lower():
        return 0.0
    return None


def validate_scenarios(scenarios: list[dict[str, str]]) -> dict[str, int]:
    ids = [row["scenario_id"] for row in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate scenario IDs")
    explicit = incomplete = reviewed = 0
    for row in scenarios:
        scenario_id = row["scenario_id"]
        if row["review_status"] not in {"unreviewed", "reviewed"}:
            raise ValueError(f"Invalid review status: {scenario_id}")
        reviewed += row["review_status"] == "reviewed"
        if not set(row["affected_sectors"].split("|")) <= TICKERS:
            raise ValueError(f"Unknown ticker: {scenario_id}")
        if int(row["time_horizon_trading_days"]) not in HORIZONS:
            raise ValueError(f"Unsupported horizon: {scenario_id}")
        missing = set(filter(None, row["missing_assumptions"].split("|")))
        expected = (
            ("oil_change_percent", "oil_change", stated_change(
                row["scenario_text"], OIL_PATTERN, "WTI oil is unchanged")),
            ("treasury_10y_change_basis_points", "treasury_yield_change", stated_change(
                row["scenario_text"], YIELD_PATTERN,
                "US 10-year Treasury yield is unchanged")),
        )
        for field, missing_name, stated in expected:
            value = row[field]
            if stated is None:
                if value or missing_name not in missing:
                    raise ValueError(f"Missing shock must stay blank and be listed: {scenario_id} {field}")
                incomplete += 1
            else:
                if not value or not math.isclose(float(value), stated, abs_tol=1e-9):
                    raise ValueError(f"Stated shock disagrees with label: {scenario_id} {field}")
                if missing_name in missing:
                    raise ValueError(f"Given shock listed as missing: {scenario_id} {field}")
                explicit += 1
    return {"rows": len(scenarios), "explicit_numeric_fields_checked": explicit,
            "missing_numeric_fields_checked": incomplete, "reviewed_rows": reviewed}


def validate_events(events: list[dict[str, str]]) -> dict[str, int]:
    ids = [row["event_id"] for row in events]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate event IDs")
    release_times = first_public_times = 0
    for row in events:
        event_id = row["event_id"]
        day = date.fromisoformat(row["event_date"])
        parsed_url = urlparse(row["source_url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc or not row["event_date_basis"]:
            raise ValueError(f"Event has no verifiable date source: {event_id}")
        release = row["source_release_timestamp_utc"]
        if release:
            when = datetime.fromisoformat(release.replace("Z", "+00:00"))
            if when.date() != day or not row["source_time_basis"]:
                raise ValueError(f"Release time/date mismatch: {event_id}")
            release_times += 1
        elif row["source_time_basis"]:
            raise ValueError(f"Time basis without time: {event_id}")
        first_public = row["first_public_timestamp_utc"]
        if first_public:
            datetime.fromisoformat(first_public.replace("Z", "+00:00"))
            if not row["first_public_source_url"]:
                raise ValueError(f"First-public time has no source: {event_id}")
            first_public_times += 1
        elif row["first_public_source_url"]:
            raise ValueError(f"First-public source without time: {event_id}")
        expected_status = ("date_and_source_release_time_verified" if release
                           else "date_verified_time_unverified")
        if not first_public and row["review_status"] != expected_status:
            raise ValueError(f"Review status disagrees with timing fields: {event_id}")
        if row["assumed_channels"]:
            raise ValueError(f"Draft has unsupported assumed channel: {event_id}")
    return {"rows": len(events), "source_release_times": release_times,
            "first_public_times": first_public_times}


def main() -> None:
    scenarios = validate_scenarios(read_rows(DRAFTS / "scenario_examples.csv"))
    events = validate_events(read_rows(DRAFTS / "event_catalog_draft.csv"))
    print(f"Scenario drafts: {scenarios}")
    print(f"Event drafts: {events}")


if __name__ == "__main__":
    main()
