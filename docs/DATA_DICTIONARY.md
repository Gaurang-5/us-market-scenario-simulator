# Data dictionary and evaluation boundaries

## Files

| File in `data/processed/` | Rows in the 2026-11-01 local build | Meaning |
| --- | ---: | --- |
| `shiller_monthly_1900_present.csv` | 1,521 | Monthly US market history, 1900-01 to 2026-09 |
| `french_market_daily_1926_present.csv` | 26,338 | US research market and factor returns, 1926-07-01 to 2026-09-30 |
| `french_10_industries_daily_1926_present.csv` | 26,338 | Ten US industry-portfolio returns on the same dates |
| `gpr_monthly_1900_present.csv` | 1,521 | Historical geopolitical risk from 1900; modern index from 1985 |
| `housing_starts_monthly_1959_present.csv` | 813 | Monthly US housing starts, 1959-01 to 2026-09 |
| `fdic_failed_banks_2000_present.csv` | 578 | FDIC failed-bank closing records, 2000-10-13 to 2026-09-25 |
| `etf_prices_daily_1999_present.csv` | 42,000 | Six ETFs on 7,000 common trading dates, 1999-01-04 to 2026-10-30 |
| `scenario_response_daily.csv` | 42,000 | Joined oil and yield shocks with ETF return labels |
| `baseline_predictions.csv` | 34,416 | Validation and test predictions across three horizons |
| `baseline_metrics.csv` | 36 | One metric row per split, ETF, and horizon |

The ETF price file contains both `close` and `adj_close`. Return labels use `adj_close`, which Tiingo adjusts for splits and dividends. French returns are decimal fractions after conversion from the source's percentages. Shiller's market prices are monthly averages, not daily closes.

## Daily response table

Each row is identified by `shock_date` and `ticker`. The same six tickers appear on every ETF trading date: SPY, XLF, XLE, XLK, XLV, and XLY.

| Column | Unit and calculation |
| --- | --- |
| `oil_price_usd`, `oil_previous_price_usd` | WTI dollars per barrel on the shock date and previous available oil observation |
| `oil_previous_date` | Date of the previous available observation; changes remain blank if it is over seven calendar days earlier |
| `oil_change_usd` | Current WTI minus previous WTI |
| `oil_change_percent` | `100 * (current / previous - 1)` only when both prices are positive |
| `treasury_10y_percent`, `treasury_10y_previous_percent` | Quoted yield in percent |
| `treasury_10y_previous_date` | Previous available yield observation date; changes remain blank if it is over seven calendar days earlier |
| `treasury_10y_change_basis_points` | `100 * (current yield - previous yield)`, rounded to six decimal places |
| `vix_prior_date`, `vix_prior_level` | Latest available VIX observation strictly before `shock_date`, at most seven calendar days old |
| `previous_etf_date` | ETF trading session before the shock date |
| `return_1d` | `adjusted_close[t] / adjusted_close[t-1] - 1` |
| `return_5d` | `adjusted_close[t+4] / adjusted_close[t-1] - 1` |
| `return_20d` | `adjusted_close[t+19] / adjusted_close[t-1] - 1` |
| `outcome_end_date_5d`, `outcome_end_date_20d` | Actual ETF trading dates used by the longer labels |
| `split` | `train`, `validation`, `test`, `embargo`, or `incomplete` |

The outcome windows include the shock date. All returns are decimal fractions, so `0.02` means 2%. The first ETF day has no prior-close label. The last 19 ETF days cannot have a 20-day label. When oil or yield is missing on the ETF date, that input stays blank; no future observation fills it. A prior factor observation more than seven calendar days old is not used to calculate a daily shock. WTI was negative on 2020-04-20, so the oil percentage field is blank there and on the following observation whose previous WTI was negative. The dollar change is retained for those two days.

`train` contains complete rows whose 20-day label ends by 2018-12-31. `validation` contains complete rows from 2019-01-01 through 2022-12-31 whose 20-day label ends by 2022-12-31. `test` contains complete rows from 2023 onward. `embargo` excludes rows whose 20-day outcome would cross the next split boundary. `incomplete` means a required shock or 20-day outcome is missing.

## Baseline

The baseline uses only training rows. It places oil changes in five bins with edges at -3%, -1%, +1%, and +3%, and yield changes in three bins with edges at -5 and +5 basis points. For each ETF and horizon it stores the 10th percentile, median, and 90th percentile of training returns in that bin. Bins with fewer than 30 training rows fall back to that ETF's unconditional training quantiles. `baseline_metrics.csv` reports median absolute error, zero-return absolute error, interval coverage, average interval width, and fallback row count.

This benchmark describes historical associations. Oil and yield changes dated `t` may only become known after trading on `t`; the 1-day ETF outcome includes that same trading day. Do not present the baseline as a forecast made before the event or as a causal estimate of an oil or rate shock.

## Context and events

The GPR historical series and modern series use different newspaper sets. Keep both columns; do not splice them without a documented adjustment. Housing starts are observation-month values and can be revised. Their release dates are not in the current file. Neither monthly series is included as a daily model feature yet. FDIC's closing date does not establish when the market first learned of a failure.

The 20 scenario examples and 16 event candidates in `data/drafts/` are drafts. The scenario validator checks whether explicit oil and yield numbers match the text and whether unstated values remain blank. It does not check whether a label is conceptually sound. Every scenario needs human review before use in Mistral training.

The event queue has 10 FDIC closures and six other source documents. `event_date_basis` says what the recorded date means. `source_release_timestamp_utc` contains a stated release or embargo time for three documents; it is not a verified first-public timestamp. `first_public_timestamp_utc` remains blank for all 16 events. Some cases overlap in time, especially the February 2022 invasion and sanctions, so a market move cannot be attributed to one of them from these dates alone. The event queue is not ready for event-window scoring.

## Provenance

`manifest.json`, `context_manifest.json`, `tiingo_etf_prices_manifest.json`, and `scenario_response_quality.json` in `data/processed/` record source URLs, checksums, coverage, or build details. Rebuilding from revised upstream files can change historical values. Use cached raw files and record their hashes for a fixed experiment. The raw and processed files stay outside Git; the scripts, templates, and reviewed labels are the shareable project materials.
