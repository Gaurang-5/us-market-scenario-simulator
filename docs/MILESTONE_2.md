# Milestone 2: Build daily scenario-response rows

The data script, conditional-quantile baseline, 20 scenario drafts, 16 sourced event candidates, and automated audit are now present. The scenario drafts still need human review, and the event candidates still need verified first-public timestamps.

## Goal

Turn the six ETF price histories into a table that can test a narrow question: when oil and the 10-year Treasury yield move on a trading day, how do the broad US market and five sectors move over 1, 5, and 20 trading days? This first table measures historical associations. It is not yet a simulator or a forecast.

## One row

Use one row per ETF and shock date `t`. Sort each ETF by its own trading dates. Let `P` be Tiingo's `adj_close`.

| Column | Definition |
| --- | --- |
| `shock_date` | ETF trading date `t` |
| `ticker` | SPY, XLF, XLE, XLK, XLV, or XLY |
| `oil_change_percent` | `100 * (WTI_t / WTI_previous_observation - 1)` when both prices are positive |
| `treasury_10y_change_basis_points` | `100 * (DGS10_t - DGS10_previous_observation)` because yields are recorded in percent |
| `return_1d` | `P_t / P_(t-1) - 1` |
| `return_5d` | `P_(t+4) / P_(t-1) - 1` |
| `return_20d` | `P_(t+19) / P_(t-1) - 1` |

The return window includes the shock day. For example, the 5-day outcome covers `t` and the following four ETF trading days. Index `t+4` and `t+19` by trading rows, not calendar days. These are decimal returns: `0.02` means 2%.

A hand check from the downloaded files: on 1999-01-05, SPY's adjusted close rose from `76.0235666918` to `76.8925509212`, giving `return_1d = 0.011430` (about 1.143%). WTI moved from `$12.42` to `$12.04`, or about `-3.06%`; the 10-year yield moved from `4.69%` to `4.74%`, or `+5` basis points.

Keep the original WTI and yield values beside their changes so the calculation can be checked. Use the previous *available observation* for each factor only when it is at most seven calendar days old, and record that observation date. If the factor has no value on `t`, leave its change blank; do not fill it with a future value. Do not compute an oil percentage change across zero or a negative WTI price; leave it blank and record the dollar change separately. The current local WTI file ends on 2026-10-27, while ETF prices end on 2026-10-30, so later rows will have missing oil inputs.

These same-day oil and yield changes are scenario conditions. Their exact values may only be known after the day's trading. A model using them to explain `return_1d` is a conditional-response model, not a before-the-event prediction. For historical event tests, retain the first public event timestamp and check which inputs were actually available then.

## Team tasks

1. **Data owner:** Review `scripts/build_model_tables.py`, `scenario_response_quality.json`, and the three hand-checked return rows in `final_data_audit.json`.
2. **Numerical-model owner:** Review `scripts/evaluate_baseline.py` and compare its held-out errors with the zero-return benchmark in `baseline_metrics.csv`.
3. **Mistral owner:** Review and correct the 20 examples in `data/drafts/scenario_examples.csv` before moving any into the labeled training set. Missing numeric assumptions stay blank.
4. **CLI/evaluation owner:** Review `data/drafts/event_catalog_draft.csv`. A scheduled release time is recorded for three documents, but no first-public timestamp is verified. Select a small, clean set of cases and verify its exact announcement times before event-window evaluation.

## Acceptance checks

- Every `(shock_date, ticker)` pair is unique; every ticker's dates are ordered.
- The 1, 5, and 20-day labels use adjusted closes and the stated trading-day windows.
- The first ETF date has no prior close. The last 19 ETF dates have no 20-day outcome.
- Blank oil/yield observations remain blank in the joined table; no future observation is used to fill them.
- Validate three hand-calculated rows, including a dividend or split date, against the source prices.
- Split dates chronologically for later modeling. Keep at least 20 trading days between training and validation/test boundaries so overlapping outcome windows do not cross them.

Do not fine-tune Mistral on numeric market rows. Its later job is to turn text into the structured scenario fields; the numerical model handles return ranges.
