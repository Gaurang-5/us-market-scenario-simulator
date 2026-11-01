"""Download and normalize the first historical market data layers."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import xlrd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
SHILLER_PAGE = "https://shillerdata.com/"
FRENCH_FACTORS = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
FRENCH_INDUSTRIES = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_daily_CSV.zip"
FRED_IDS = ("DGS10", "DCOILWTICO", "VIXCLS")


class LinkFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mini-project-dataset/0.1 (student research)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def shiller_url() -> str:
    finder = LinkFinder()
    finder.feed(download(SHILLER_PAGE).decode("utf-8"))
    matches = [urllib.parse.urljoin(SHILLER_PAGE, href) for href in finder.links if "ie_data.xls" in href]
    if len(matches) != 1:
        raise ValueError(f"Expected one Shiller workbook link; found {len(matches)}")
    return matches[0]


def write_raw(name: str, payload: bytes) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    path.write_bytes(payload)
    return path


def number(value: object) -> str:
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def percent_to_decimal(value: str) -> str:
    return str(Decimal(value) / Decimal(100))


def parse_shiller(path: Path) -> tuple[list[dict[str, str]], str]:
    sheet = xlrd.open_workbook(path).sheet_by_name("Data")
    records: list[dict[str, str]] = []
    for index in range(8, sheet.nrows):
        row = sheet.row_values(index)
        if not isinstance(row[0], (int, float)):
            continue
        year = int(row[0])
        month = round((row[0] - year) * 100)
        if not (1 <= month <= 12):
            continue
        if year < 1900:
            continue
        records.append({
            "month": f"{year:04d}-{month:02d}",
            "price_monthly_average": number(row[1]),
            "dividend_annualized": number(row[2]),
            "earnings_annualized": number(row[3]),
            "cpi_historical": number(row[4]),
            "long_interest_rate_percent": number(row[6]),
            "cape": number(row[12]),
        })
    if not records or records[0]["month"] != "1900-01":
        raise ValueError("Shiller history does not begin at 1900-01")
    # The workbook can include a partial latest month (as its source note says).
    excluded = records.pop()["month"]
    return records, excluded


def zip_csv(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {path.name}: {names}")
        content = archive.read(names[0]).decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(content)))


def french_rows(path: Path, header_token: str) -> tuple[list[str], list[list[str]]]:
    rows = zip_csv(path)
    start = next(i for i, row in enumerate(rows) if row and header_token in row)
    headers = [value.strip() for value in rows[start]]
    observations: list[list[str]] = []
    for row in rows[start + 1:]:
        if not row or not re.fullmatch(r"\d{8}", row[0].strip()):
            if observations:
                break
            continue
        observations.append([value.strip() for value in row])
    return headers, observations


def parse_french_factors(path: Path) -> list[dict[str, str]]:
    headers, observations = french_rows(path, "Mkt-RF")
    if headers[:5] != ["", "Mkt-RF", "SMB", "HML", "RF"]:
        raise ValueError(f"Unexpected French factor columns: {headers}")
    return [{
        "date": f"{row[0][:4]}-{row[0][4:6]}-{row[0][6:]}",
        "market_return_decimal": str((Decimal(row[1]) + Decimal(row[4])) / Decimal(100)),
        "market_excess_return_decimal": percent_to_decimal(row[1]),
        "risk_free_return_decimal": percent_to_decimal(row[4]),
        "smb_decimal": percent_to_decimal(row[2]),
        "hml_decimal": percent_to_decimal(row[3]),
    } for row in observations]


def parse_french_industries(path: Path) -> list[dict[str, str]]:
    headers, observations = french_rows(path, "NoDur")
    expected = ["", "NoDur", "Durbl", "Manuf", "Enrgy", "HiTec", "Telcm", "Shops", "Hlth", "Utils", "Other"]
    if headers != expected:
        raise ValueError(f"Unexpected French industry columns: {headers}")
    result = []
    for row in observations:
        record = {"date": f"{row[0][:4]}-{row[0][4:6]}-{row[0][6:]}"}
        for label, value in zip(headers[1:], row[1:]):
            numeric = Decimal(value)
            record[f"{label}_return_decimal"] = "" if numeric in (Decimal("-99.99"), Decimal("-999")) else percent_to_decimal(value)
        result.append(record)
    return result


def parse_fred(path: Path, series_id: str) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or series_id not in rows[0]:
        raise ValueError(f"Unexpected FRED file for {series_id}")
    return [{"date": row["observation_date"],
             "value": "" if row[series_id].strip() in ("", ".") else row[series_id].strip()}
            for row in rows]


def save_csv(name: str, rows: list[dict[str, str]]) -> dict[str, object]:
    if not rows:
        raise ValueError(f"No rows for {name}")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    path = PROCESSED / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    key = "month" if "month" in rows[0] else "date"
    dates = [row[key] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError(f"Dates are unsorted or duplicated in {name}")
    return {"path": str(path.relative_to(ROOT)), "rows": len(rows), "first": dates[0], "last": dates[-1]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Rebuild from existing data/raw files")
    args = parser.parse_args()
    previous_manifest = PROCESSED / "manifest.json"
    previous_shiller_url = SHILLER_PAGE
    if args.offline and previous_manifest.exists():
        previous_shiller_url = json.loads(previous_manifest.read_text(encoding="utf-8"))["raw_sources"]["shiller"]["url"]
    sources = {"shiller": shiller_url() if not args.offline else previous_shiller_url,
               "french_factors": FRENCH_FACTORS, "french_industries": FRENCH_INDUSTRIES}
    sources.update({key: f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={key}" for key in FRED_IDS})
    filenames = {"shiller": "shiller_ie_data.xls", "french_factors": "french_factors_daily.zip",
                 "french_industries": "french_10_industries_daily.zip"}
    filenames.update({key: f"fred_{key}.csv" for key in FRED_IDS})
    raw_files = {}
    for key, url in sources.items():
        path = RAW / filenames[key]
        if not args.offline:
            path = write_raw(filenames[key], download(url))
        if not path.exists():
            raise FileNotFoundError(path)
        raw_files[key] = {"url": url, "path": str(path.relative_to(ROOT)),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    shiller, excluded_month = parse_shiller(RAW / filenames["shiller"])
    factors = parse_french_factors(RAW / filenames["french_factors"])
    industries = parse_french_industries(RAW / filenames["french_industries"])
    if [r["date"] for r in factors] != [r["date"] for r in industries]:
        raise ValueError("French factors and industries have different date coverage")
    outputs = {
        "shiller": save_csv("shiller_monthly_1900_present.csv", shiller),
        "french_factors": save_csv("french_market_daily_1926_present.csv", factors),
        "french_industries": save_csv("french_10_industries_daily_1926_present.csv", industries),
    }
    for key in FRED_IDS:
        outputs[key] = save_csv(f"fred_{key}.csv", parse_fred(RAW / filenames[key], key))
    manifest = {"built_at_utc": datetime.now(timezone.utc).isoformat(), "raw_sources": raw_files,
                "outputs": outputs, "excluded_latest_shiller_month": excluded_month,
                "notes": ["Shiller values are monthly averages, not month-end closes.",
                          "French return fields are decimal fractions; source CSVs use percent.",
                          "FRED missing observations remain blank and are not forward-filled."]}
    (PROCESSED / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputs": outputs, "excluded_latest_shiller_month": excluded_month}, indent=2))


if __name__ == "__main__":
    main()
