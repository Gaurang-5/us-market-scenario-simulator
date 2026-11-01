"""Build a source-linked event review queue without inventing announcement times."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "processed" / "fdic_failed_banks_2000_present.csv"
OUTPUT = ROOT / "data" / "drafts" / "event_catalog_draft.csv"
FDIC_URL = "https://www.fdic.gov/bank-failures/failed-bank-list"
FDIC_RELEASES = {
    "24735": "https://www.fdic.gov/news/press-releases/2023/pr23016.html",
    "57053": "https://www.fdic.gov/news/press-releases/2023/pr23018.html",
    "59017": "https://www.fdic.gov/news/press-releases/2023/pr23034.html",
}
CERTIFICATES = ("32633", "29730", "9609", "32247", "58302",
                "24735", "57053", "59017", "57488", "58590")
FIELDS = ("event_id", "event_type", "country", "event_date", "event_date_basis",
          "event_name", "bank_name", "fdic_cert", "source_url",
          "source_release_timestamp_utc", "source_time_basis",
          "first_public_timestamp_utc", "first_public_source_url",
          "historical_data_layer", "known_conditions", "assumed_channels",
          "review_status", "reviewer_notes")

# These source documents verify dates. Where stated, scheduled release times are
# converted from EDT (UTC-4). None proves the event's first public time.
DOCUMENTED_EVENTS = (
    ("WHO-2020-03-11", "pandemic", "US|global", "2020-03-11", "WHO speech date",
     "WHO characterizes COVID-19 as a pandemic",
     "https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020",
     "", "", "WHO pandemic characterization", "Speech page supplies date but no release time."),
    ("BLS-2020-04-03", "employment_release", "US", "2020-04-03", "BLS release date",
     "March 2020 Employment Situation release",
     "https://www.bls.gov/news.release/archives/empsit_04032020.htm",
     "2020-04-03T12:30:00Z", "embargo until 08:30 EDT",
     "March unemployment rate 4.4 percent; payroll employment fell by 701000",
     "Archived page notes a later reissue; use the original release for vintage values."),
    ("CENSUS-2020-05-19", "housing_release", "US", "2020-05-19", "Census release date",
     "April 2020 New Residential Construction release",
     "https://www.census.gov/construction/nrc/pdf/newresconst_202004.pdf",
     "2020-05-19T12:30:00Z", "for release at 08:30 EDT",
     "April housing starts preliminary SAAR 891000; 30.2 percent below revised March estimate",
     "The current monthly history is revised; the archived release is the event-time vintage."),
    ("UN-2022-02-24", "war", "US|Ukraine|Russia", "2022-02-24", "UN statement date",
     "UN statement on Russian military operations in Ukraine",
     "https://www.un.org/sg/en/content/sg/statements/2022-02-24/statement-the-secretary-general-ukraine",
     "", "", "UN describes Russian military operations inside Ukraine",
     "Statement date is not the invasion's first-public timestamp."),
    ("USTREASURY-2022-02-24", "sanctions", "US|Russia", "2022-02-24", "Treasury release date",
     "US Treasury announces expanded sanctions against Russia",
     "https://home.treasury.gov/news/press-releases/jy0608",
     "", "", "Treasury announces restrictions on Russian financial institutions",
     "Treasury page gives date, not a precise publication time; earlier sanctions also existed."),
    ("FOMC-2022-03-16", "monetary_policy", "US", "2022-03-16", "Fed statement date",
     "FOMC raises federal funds target range",
     "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm",
     "2022-03-16T18:00:00Z", "for release at 14:00 EDT",
     "Target range raised to 0.25-0.50 percent",
     "The source time is scheduled release time, not independent proof of first receipt."),
)


def build_events(fdic_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_cert = {row["fdic_cert"]: row for row in fdic_rows}
    missing = set(CERTIFICATES) - set(by_cert)
    if missing:
        raise ValueError(f"Missing FDIC certificates: {sorted(missing)}")
    events: list[dict[str, str]] = []
    for cert in CERTIFICATES:
        row = by_cert[cert]
        events.append({"event_id": f"FDIC-{cert}", "event_type": "bank_failure",
                       "country": "US", "event_date": row["closing_date"],
                       "event_date_basis": "FDIC closing date", "event_name": row["bank_name"],
                       "bank_name": row["bank_name"], "fdic_cert": cert,
                       "source_url": FDIC_RELEASES.get(cert, FDIC_URL),
                       "source_release_timestamp_utc": "",
                       "source_time_basis": "", "first_public_timestamp_utc": "",
                       "first_public_source_url": "", "historical_data_layer": "modern_etf",
                       "known_conditions": "FDIC records bank closure", "assumed_channels": "",
                       "review_status": "date_verified_time_unverified",
                       "reviewer_notes": "Closing date is verified; first public announcement time is not."})
    for (event_id, event_type, country, day, date_basis, name, url,
         release_time, time_basis, conditions, notes) in DOCUMENTED_EVENTS:
        events.append({"event_id": event_id, "event_type": event_type,
                       "country": country, "event_date": day,
                       "event_date_basis": date_basis, "event_name": name,
                       "bank_name": "", "fdic_cert": "", "source_url": url,
                       "source_release_timestamp_utc": release_time,
                       "source_time_basis": time_basis,
                       "first_public_timestamp_utc": "", "first_public_source_url": "",
                       "historical_data_layer": "modern_etf", "known_conditions": conditions,
                       "assumed_channels": "",
                       "review_status": "date_and_source_release_time_verified" if release_time
                       else "date_verified_time_unverified", "reviewer_notes": notes})
    events.sort(key=lambda row: (row["event_date"], row["event_id"]))
    return events


def main() -> None:
    with SOURCE.open(newline="", encoding="utf-8") as handle:
        events = build_events(list(csv.DictReader(handle)))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(events)
    print(f"Saved {len(events)} sourced event candidates to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
