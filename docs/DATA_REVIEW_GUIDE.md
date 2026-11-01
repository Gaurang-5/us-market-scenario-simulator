# Dataset review guide

Use this guide after building the data locally. The scripts check file structure and calculations; the team must still review source meaning, scenario labels, and event timing. The reference counts below come from the 2026-11-01 local build. If a later download has different coverage, record the dates and explain the change.

## 1. Reproduce the checks

Follow the build steps in [README](../README.md), including a Tiingo download under your own account. Then run:

```sh
.venv/bin/python scripts/validate_drafts.py
.venv/bin/python scripts/audit_data.py
.venv/bin/python -m unittest discover -s tests -v
```

The reference build has 42,000 ETF response rows, 20 scenario drafts, 16 event candidates, and six passing tests. Save the command output or summarize it in the review pull request. A passing script does not mean the market interpretation is correct.

## 2. Review sources and market rows

**Owners: data and numerical-model teammates.** Read `data/processed/manifest.json`, `context_manifest.json`, and `tiingo_etf_prices_manifest.json`. Check source URLs, raw-file hashes, date coverage, units, and missing-value notes. Keep the raw files and their manifests together for a fixed experiment.

Spot-check adjusted ETF returns against the downloaded prices. The audit already names three cases: SPY on 1999-01-05 and 1999-03-19, and XLE on 2025-12-05. For each, calculate `adj_close[current] / adj_close[previous trading day] - 1`. Also inspect the negative WTI observation on 2020-04-20, the train/validation and validation/test boundaries, and the final 19 ETF days that cannot have a 20-day outcome. Use the formulas and units in the [data dictionary](DATA_DICTIONARY.md).

Record each manual check in a copy of [`data/templates/data_review_log.csv`](../data/templates/data_review_log.csv). Include the record ID or date, what you checked, the source URL, the result, and your name. Do not commit downloaded prices or an API token.

## 3. Review the 20 scenario examples

**Owners: language-model teammate plus one second reader.** Open [`data/drafts/scenario_examples.csv`](../data/drafts/scenario_examples.csv). For each row, check that:

- `event_type`, `countries`, `affected_sectors`, and trading-day horizon match the sentence;
- any oil percentage or 10-year yield basis-point value appears explicitly in the sentence;
- unstated numbers stay blank and appear in `missing_assumptions`;
- the example is a useful question for the intended US-market scope.

The first ten rows state numerical shocks; the other ten contain missing assumptions. Discuss disagreements and record the decision in the pull request or review log. Change `review_status` to `reviewed` only after both readers agree. These are extraction examples, not observed market outcomes.

## 4. Review a small event set

**Owner: event/evaluation teammate.** Start with three to five events from [`data/drafts/event_catalog_draft.csv`](../data/drafts/event_catalog_draft.csv). For each, open the source and record the event definition, exact public announcement time and timezone, source URL, what was already known, and the first eligible US ETF session. If the public time cannot be verified, leave `first_public_timestamp_utc` blank.

`source_release_timestamp_utc` records a stated release or embargo time for three documents. Do not copy it into `first_public_timestamp_utc` without checking what was public earlier. Events close together, including the February 2022 invasion and sanctions, need a note about overlap. A market move alone does not identify which event caused it.

## 5. Keep monthly context separate until its timing is known

Housing starts are already collected from 1959, and the GPR history starts in 1900. Their observation months are not release dates. The housing history also contains later revisions. If you want either series as a historical model input, collect publication dates and first-release values first. The [data status page](DATA_STATUS.md) shows a housing revision example and links to the Census release archive.

## Review handoff

Open a pull request containing the review log, corrected draft labels, and any source notes. Have a teammate who did not make the changes check the evidence. State which files were reviewed, which checks passed, any unresolved cases, and whether the data is approved only for the narrow oil/yield experiment or for an additional scenario type.
