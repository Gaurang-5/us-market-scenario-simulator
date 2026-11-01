# US market scenario dataset

This repository holds the data pipeline for a US market scenario simulator. It keeps three market histories separate: Shiller monthly observations from 1900, Kenneth French's US daily market and industry returns from 1926, and six ETF price histories from 1999. "French" is the researcher's surname, not a reference to France. It also collects oil, Treasury yield, VIX, geopolitical risk, housing starts, and FDIC bank-failure records.

## Build the data

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_dataset.py
.venv/bin/python scripts/collect_context.py
.venv/bin/python scripts/collect_etfs.py coverage
```

Tiingo prices need each user's own API token. Follow the instructions in **Modern ETF data** below. Once ETF prices exist locally, build the response table, baseline, event drafts, and audit:

```sh
.venv/bin/python scripts/build_model_tables.py
.venv/bin/python scripts/evaluate_baseline.py
.venv/bin/python scripts/build_event_drafts.py
.venv/bin/python scripts/validate_drafts.py
.venv/bin/python scripts/audit_data.py
.venv/bin/python -m unittest discover -s tests -v
```

To rebuild the historical and context CSVs from cached raw downloads without network calls:

```sh
.venv/bin/python scripts/build_dataset.py --offline
.venv/bin/python scripts/collect_context.py --offline
```

Source downloads are in `data/raw/`; generated tables and source manifests are in `data/processed/`. These folders are excluded from Git. Teammates can rebuild them under their own source access. Review each source's terms before sharing derived tables publicly.

## Columns and limits

- `shiller_monthly_1900_present.csv`: monthly average market price, annualized dividends and earnings, historical CPI, historical long interest rate, and CAPE. The script leaves out the latest workbook month because it can be incomplete. Before 1913, the CPI in this workbook is reconstructed from earlier price data.
- `french_market_daily_1926_present.csv`: US market return, excess return, risk-free return, SMB, and HML. Returns are decimal fractions: `0.01` means 1%.
- `french_10_industries_daily_1926_present.csv`: value-weighted returns for 10 portfolios of US stocks, also decimal fractions. The historical industries are not today's sector ETFs.
- `fred_*.csv`: original date and value for DGS10, DCOILWTICO, and VIXCLS. Missing values stay blank. WTI can cross zero; ordinary percent and log returns are not valid across that point.
- `gpr_monthly_1900_present.csv`: historical geopolitical risk index from 1900 and modern index from 1985. These are separate index definitions. [GPR source and CC BY 4.0 terms](https://www.policyuncertainty.com/gpr.html).
- `housing_starts_monthly_1959_present.csv`: US housing starts, in thousands of units, both not seasonally adjusted and seasonally adjusted annual rate. [Census source](https://www.census.gov/construction/nrc/data/series.html).
- `fdic_failed_banks_2000_present.csv`: FDIC bank closing dates, names, and certificate numbers. The closing date is not a verified first-public-announcement time. [FDIC source](https://www.fdic.gov/bank-failures/failed-bank-list).

The market histories have different definitions. Do not concatenate them into one price series. Monthly economic observations need release-date alignment before they can be used as features in a historical prediction exercise. GPR, housing, and bank failures remain separate context tables for that reason.

## Team labeling templates

`data/templates/scenario_labels.csv` and `data/templates/event_catalog.csv` contain headers for human-reviewed records. `data/drafts/scenario_examples.csv` contains 20 hypothetical extraction examples, all marked `unreviewed`. `data/drafts/event_catalog_draft.csv` contains 16 sourced candidates: 10 bank closures and six pandemic, employment, housing, war, sanctions, or monetary-policy records. Three source documents state a scheduled release or embargo time. These are stored separately from first-public timestamps, which remain blank. Do not train Mistral on unreviewed drafts. Leave unknown shock magnitudes blank.

## Modern ETF data

Check Tiingo's public ticker list without a key:

```sh
.venv/bin/python scripts/collect_etfs.py coverage
```

The list checked on 2026-11-01 reports SPY from 1993-01-29 and XLF, XLE, XLK, XLV, and XLY from 1998-12-22. All six list 2026-10-30 as their last date. This is a listing check, not a guarantee that a particular account can download every listed price. Tiingo says the public list can also contain reserved symbols. The script writes `tiingo_etf_public_coverage.csv` and a source manifest to `data/processed/`.

To download actual prices, get a [Tiingo API token](https://www.tiingo.com/account/api/token), set `TIINGO_API_KEY` in your local shell, and run:

```sh
read -s "TIINGO_API_KEY?Tiingo API key: "
echo
export TIINGO_API_KEY
.venv/bin/python scripts/collect_etfs.py download
```

You may use `--end-date YYYY-MM-DD` to stop at a fixed date for a reproducible experiment. The script checks authenticated ticker metadata, downloads 1999 onward, and writes `etf_prices_daily_1999_present.csv` plus actual per-ticker coverage. It keeps raw `close` and Tiingo's split- and dividend-adjusted `adj_close` in separate columns. Use `adj_close` consistently when computing return labels. Missing trading dates are not filled in. The local download checked on 2026-11-01 contains 7,000 rows per ticker from 1999-01-04 through 2026-10-30. Generated prices are not included in Git.

The Tiingo individual plan has internal-use restrictions, so keep raw downloads private. The project ignores `data/raw/`, `data/processed/`, `.env`, and `.env.local` in Git. Never commit or share the API token. See the [EOD field definitions](https://www.tiingo.com/documentation/end-of-day), [API connection guide](https://www.tiingo.com/documentation/general/connecting), and [Tiingo source and terms](https://www.tiingo.com/products/end-of-day-stock-price-data).

## Model-ready table and baseline

`scenario_response_daily.csv` has one row per ETF and trading day. It joins same-day WTI and Treasury-yield changes, a prior-day VIX value, and adjusted ETF returns over 1, 5, and 20 trading days. The return windows include the shock day. Oil percentage change is blank when either WTI price is nonpositive. The table retains rows with missing inputs, but only complete rows enter the baseline. Train rows end in 2018, validation covers 2019-2022, and test begins in 2023; outcome windows that cross boundaries are embargoed.

`baseline_predictions.csv`, `baseline_metrics.csv`, and `baseline_model.json` contain a transparent conditional-quantile benchmark. It bins oil and yield changes, then reports the training median and 10th/90th percentile ETF returns. It is an association benchmark, not a causal or pre-event forecast. On the held-out SPY test period, its 1-day median has higher absolute error than predicting zero return; see the metric file before using it as a model.

The local data audit checked on 2026-11-01 found 42,000 ETF response rows, 26,928 training rows, 5,856 validation rows, 5,616 test rows, 216 embargoed rows, and 3,384 incomplete rows. It also checked a dividend date and a split date. Read [Data dictionary](docs/DATA_DICTIONARY.md) for exact columns and limitations, [Milestone 2](docs/MILESTONE_2.md) for formulas, and `data/processed/final_data_audit.json` for the current machine-readable audit.

Source pages: [Shiller](https://shillerdata.com/), [Ken French](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html), [FRED](https://fred.stlouisfed.org/).

For other free sources and the four-person GitHub workflow, see [Team setup](docs/TEAM_SETUP.md).

Read [Data status and team review](docs/DATA_STATUS.md) for the current data boundary and the remaining human checks.
