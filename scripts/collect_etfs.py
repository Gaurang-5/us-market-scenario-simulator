"""Check public ETF coverage and collect Tiingo end-of-day prices."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
TICKERS = ("SPY", "XLF", "XLE", "XLK", "XLV", "XLY")
START_DATE = date(1999, 1, 1)
LIST_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
API_BASE = "https://api.tiingo.com/tiingo/daily"
PRICE_FIELDS = ("date", "ticker", "close", "adj_close", "volume", "adj_volume", "div_cash", "split_factor")


def get_bytes(url: str, token: str | None = None) -> bytes:
    headers = {"User-Agent": "mini-project-dataset/0.1 (student research)"}
    if token:
        headers["Authorization"] = f"Token {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        # Never include a token, response body, or full request URL in errors.
        raise RuntimeError(f"Tiingo request failed with HTTP {error.code}") from None


def save_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def coverage(offline: bool) -> None:
    path = RAW / "tiingo_supported_tickers.zip"
    if not offline:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get_bytes(LIST_URL))
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run coverage without --offline first")
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV inside {path.name}")
        rows = list(csv.DictReader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8-sig")))
    selected = {row["ticker"].upper(): row for row in rows if row["ticker"].upper() in TICKERS}
    if set(selected) != set(TICKERS):
        raise ValueError(f"Missing tickers: {sorted(set(TICKERS) - set(selected))}")
    fields = ("ticker", "exchange", "asset_type", "currency", "listed_start", "listed_end")
    output = [{"ticker": ticker, "exchange": selected[ticker]["exchange"],
               "asset_type": selected[ticker]["assetType"],
               "currency": selected[ticker]["priceCurrency"],
               "listed_start": selected[ticker]["startDate"],
               "listed_end": selected[ticker]["endDate"]} for ticker in TICKERS]
    save_csv(PROCESSED / "tiingo_etf_public_coverage.csv", output, fields)
    manifest = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_url": LIST_URL, "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "note": "The public symbol list can include reservations. Dates are not proof of authenticated price access."}
    (PROCESSED / "tiingo_etf_public_coverage_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for row in output:
        print(f'{row["ticker"]}: {row["listed_start"]} to {row["listed_end"]} ({row["asset_type"]})')


def api_json(url: str, token: str) -> object:
    return json.loads(get_bytes(url, token))


def download_prices(end_date: date | None) -> None:
    token = os.environ.get("TIINGO_API_KEY", "").strip()
    if not token:
        raise SystemExit("Set TIINGO_API_KEY locally before running download. Do not paste the key into chat or Git.")
    prices: list[dict[str, object]] = []
    metadata_rows: list[dict[str, object]] = []
    raw_payloads: dict[str, bytes] = {}
    for ticker in TICKERS:
        metadata = api_json(f"{API_BASE}/{ticker}", token)
        if not isinstance(metadata, dict) or metadata.get("ticker", "").upper() != ticker:
            raise ValueError(f"Invalid metadata for {ticker}")
        first = metadata.get("startDate")
        last = metadata.get("endDate")
        if not first or not last:
            raise ValueError(f"{ticker} has no current price coverage in authenticated metadata")
        last_date = date.fromisoformat(last[:10])
        target_end = min(end_date, last_date) if end_date else last_date
        if target_end < START_DATE:
            raise ValueError(f"{ticker} ends before {START_DATE}")
        query = urllib.parse.urlencode({"startDate": START_DATE.isoformat(),
                                        "endDate": target_end.isoformat(), "format": "json"})
        payload = get_bytes(f"{API_BASE}/{ticker}/prices?{query}", token)
        observations = json.loads(payload)
        if not isinstance(observations, list) or not observations:
            raise ValueError(f"No price observations for {ticker}")
        seen: set[str] = set()
        ticker_prices: list[dict[str, object]] = []
        for item in observations:
            if not isinstance(item, dict):
                raise ValueError(f"Malformed price observation for {ticker}")
            day = date.fromisoformat(item["date"][:10]).isoformat()
            if day in seen or not (START_DATE.isoformat() <= day <= target_end.isoformat()):
                raise ValueError(f"Duplicate or out-of-range date for {ticker}: {day}")
            seen.add(day)
            for required in ("close", "adjClose", "volume"):
                if item.get(required) is None:
                    raise ValueError(f"Missing {required} for {ticker} on {day}")
            ticker_prices.append({"date": day, "ticker": ticker, "close": item["close"],
                                  "adj_close": item["adjClose"], "volume": item["volume"],
                                  "adj_volume": item.get("adjVolume", ""),
                                  "div_cash": item.get("divCash", ""),
                                  "split_factor": item.get("splitFactor", "")})
        ticker_prices.sort(key=lambda row: row["date"])
        prices.extend(ticker_prices)
        metadata_rows.append({"ticker": ticker, "name": metadata.get("name", ""),
                              "metadata_start": first[:10], "metadata_end": last[:10],
                              "downloaded_first": ticker_prices[0]["date"],
                              "downloaded_last": ticker_prices[-1]["date"],
                              "rows": len(ticker_prices)})
        raw_payloads[ticker] = payload
        print(f'{ticker}: {len(ticker_prices)} rows, {ticker_prices[0]["date"]} to {ticker_prices[-1]["date"]}')
    # Save only after every ticker is fetched and checked, so partial runs cannot look complete.
    RAW.mkdir(parents=True, exist_ok=True)
    for ticker, payload in raw_payloads.items():
        (RAW / f"tiingo_{ticker}_prices.json").write_bytes(payload)
    prices.sort(key=lambda row: (row["date"], row["ticker"]))
    save_csv(PROCESSED / "etf_prices_daily_1999_present.csv", prices, PRICE_FIELDS)
    save_csv(PROCESSED / "tiingo_etf_download_coverage.csv", metadata_rows,
             ("ticker", "name", "metadata_start", "metadata_end", "downloaded_first", "downloaded_last", "rows"))
    manifest = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_url_template": f"{API_BASE}/<ticker>/prices",
                "requested_start_date": START_DATE.isoformat(),
                "requested_end_date": end_date.isoformat() if end_date else None,
                "rows": len(prices),
                "raw_sha256": {ticker: hashlib.sha256(payload).hexdigest() for ticker, payload in raw_payloads.items()},
                "note": "adj_close is Tiingo's split- and dividend-adjusted close; do not mix it with raw close."}
    (PROCESSED / "tiingo_etf_prices_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(prices)} observations across {len(TICKERS)} ETFs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    coverage_parser = commands.add_parser("coverage", help="Check Tiingo's public symbol list; no API key needed")
    coverage_parser.add_argument("--offline", action="store_true", help="Use the cached ZIP")
    download_parser = commands.add_parser("download", help="Download prices using TIINGO_API_KEY")
    download_parser.add_argument("--end-date", type=date.fromisoformat, help="Latest date to request (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.command == "coverage":
        coverage(args.offline)
    else:
        download_prices(args.end_date)


if __name__ == "__main__":
    main()
