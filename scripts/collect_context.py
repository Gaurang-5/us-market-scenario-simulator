"""Collect geopolitical risk, housing starts, and FDIC bank failures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import xlrd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
SOURCES = {
    "gpr": ("https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls", "gpr_export.xls"),
    "housing": ("https://www.census.gov/construction/nrc/xls/starts_cust.xlsx", "census_housing_starts.xlsx"),
    "fdic": ("https://www.fdic.gov/bank-failures/download-data.csv", "fdic_failed_banks.csv"),
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mini-project-dataset/0.1 (student research)"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        raise ValueError(f"No rows for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    dates = [str(row[fields[0]]) for row in rows]
    if dates != sorted(dates):
        raise ValueError(f"Dates are not ordered: {path.name}")
    return {"path": str(path.relative_to(ROOT)), "rows": len(rows), "first": dates[0], "last": dates[-1]}


def parse_gpr(path: Path) -> list[dict[str, object]]:
    book = xlrd.open_workbook(path)
    sheet = book.sheet_by_index(0)
    headers = [str(value).strip() for value in sheet.row_values(0)]
    columns = {name: headers.index(name) for name in ("GPR", "GPRT", "GPRA", "GPRH", "GPRHT", "GPRHA")}
    if sheet.cell_value(1, 0) != 1 or sheet.cell_value(2, 0) != 32:
        raise ValueError("GPR January/February 1900 serials changed")
    result = []
    for index in range(1, sheet.nrows):
        year, month = 1900 + (index - 1) // 12, (index - 1) % 12 + 1
        # Excel's January and February 1900 serials are ambiguous in xlrd.
        if index > 2:
            observed = xlrd.xldate.xldate_as_tuple(sheet.cell_value(index, 0), book.datemode)
            if observed[:2] != (year, month):
                raise ValueError(f"GPR date mismatch at row {index}")
        values = sheet.row_values(index)
        row: dict[str, object] = {"month": f"{year:04d}-{month:02d}"}
        for source, output in (("GPRH", "gpr_historical"), ("GPRHT", "gpr_historical_threats"),
                               ("GPRHA", "gpr_historical_acts"), ("GPR", "gpr_modern"),
                               ("GPRT", "gpr_modern_threats"), ("GPRA", "gpr_modern_acts")):
            value = values[columns[source]]
            row[output] = value if isinstance(value, (int, float)) else ""
        result.append(row)
    if result[0]["month"] != "1900-01" or result[0]["gpr_historical"] == "":
        raise ValueError("GPR historical series does not begin in January 1900")
    return result


def parse_housing(path: Path) -> list[dict[str, object]]:
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = (("Not Seasonally Adjusted", "starts_nsa_thousands"),
             ("Seasonally Adjusted", "starts_sa_annual_rate_thousands"))
    by_month: dict[str, dict[str, object]] = {}
    for sheet_name, field in names:
        sheet = book[sheet_name]
        for values in sheet.iter_rows(min_row=7, values_only=True):
            month, amount = values[:2]
            if not isinstance(month, datetime):
                continue
            key = month.strftime("%Y-%m")
            row = by_month.setdefault(key, {"month": key})
            row[field] = amount if isinstance(amount, (int, float)) else ""
    result = [by_month[month] for month in sorted(by_month)]
    if not result or result[0]["month"] != "1959-01":
        raise ValueError("Housing starts do not begin in January 1959")
    return result


def parse_fdic(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="cp1252") as handle:
        reader = csv.DictReader(handle)
        rows = [{key.strip().replace("\xa0", ""): value.strip() for key, value in row.items()}
                for row in reader]
    required = {"Bank Name", "City", "State", "Cert", "Acquiring Institution", "Closing Date", "Fund"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("FDIC columns changed")
    result = []
    for row in rows:
        day = datetime.strptime(row["Closing Date"], "%d-%b-%y").date()
        # The failed-bank list starts in 2000; this also guards 2-digit-year parsing.
        if day.year < 2000:
            raise ValueError(f"Unexpected FDIC year for {row['Bank Name']}")
        result.append({"closing_date": day.isoformat(), "bank_name": row["Bank Name"],
                       "city": row["City"], "state": row["State"], "fdic_cert": row["Cert"],
                       "acquiring_institution": row["Acquiring Institution"], "fund": row["Fund"]})
    result.sort(key=lambda row: (row["closing_date"], row["fdic_cert"]))
    if len({(row["closing_date"], row["fdic_cert"]) for row in result}) != len(result):
        raise ValueError("Duplicate FDIC closing date and certificate")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Parse existing data/raw files")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    raw_sources = {}
    for key, (url, filename) in SOURCES.items():
        path = RAW / filename
        if not args.offline:
            path.write_bytes(fetch(url))
        if not path.exists():
            raise FileNotFoundError(path)
        raw_sources[key] = {"url": url, "path": str(path.relative_to(ROOT)),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    gpr = parse_gpr(RAW / SOURCES["gpr"][1])
    housing = parse_housing(RAW / SOURCES["housing"][1])
    fdic = parse_fdic(RAW / SOURCES["fdic"][1])
    outputs = {
        "gpr": write_csv(PROCESSED / "gpr_monthly_1900_present.csv", list(gpr[0]), gpr),
        "housing": write_csv(PROCESSED / "housing_starts_monthly_1959_present.csv", list(housing[0]), housing),
        "fdic": write_csv(PROCESSED / "fdic_failed_banks_2000_present.csv", list(fdic[0]), fdic),
    }
    manifest = {"built_at_utc": datetime.now(timezone.utc).isoformat(), "raw_sources": raw_sources,
                "outputs": outputs,
                "notes": ["GPRH is the three-newspaper historical index; GPR is the modern ten-newspaper index.",
                          "Housing starts are observation-month values, not release-date-aligned daily features.",
                          "FDIC closing dates are not first-public-announcement timestamps."]}
    (PROCESSED / "context_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
