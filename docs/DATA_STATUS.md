# Data status and team review

Checked on 2026-11-01. The local build covers three separate market histories: Shiller monthly data from 1900, Kenneth French US research returns from 1926, and six US ETFs from 1999. These histories have different units and market definitions. The ETF response table is ready for a narrow historical oil and 10-year Treasury yield association study. It is not a full war, sanctions, bank-failure, or housing scenario training set.

| Data part | Current state | Use now |
| --- | --- | --- |
| ETF returns and oil/yield conditions | 42,000 rows; six ETFs; 1999-01-04 to 2026-10-30 | Conditional historical analysis, subject to the timing rule below |
| Shiller and French histories | 1900 monthly and 1926 daily, respectively | Separate long-run context and research tests |
| GPR and housing starts | Monthly values collected; historical release dates absent | Context and case research only |
| FDIC bank closures | 578 sourced closing records; 10 selected for review | Event discovery, not market reaction timing |
| Other event documents | Six official records with date and URL; three state a release or embargo time | Case selection and source review |
| Scenario extraction examples | 20 hypothetical rows; explicit oil/yield fields pass automatic checks | Human labeling review, not fine-tuning yet |

## Timing and vintage rules

A monthly observation month is not a publication date. The collected housing file is a later, revised history. For April 2020 it now shows 936,000 housing starts at a seasonally adjusted annual rate, while the [Census release dated May 19, 2020](https://www.census.gov/construction/nrc/pdf/newresconst_202004.pdf) reported a preliminary 891,000. Using 936,000 as if traders knew it on May 19 would insert later information into a historical test. The Census [historical release archive](https://www.census.gov/construction/nrc/data/releases.html) provides vintage documents for many years, but the pipeline has not parsed them into a point-in-time series. GPR is also a retrospective index, so the month label alone is insufficient to establish when a value was available.

The daily oil and 10-year yield columns are dated to the same trading day as the ETF return. The full-day change may be known only after the close. Those rows describe conditional co-movements; they cannot establish a forecast made before that day's market response. Prior-day VIX is stored separately.

## Event evidence in the draft queue

The event queue lives in `data/drafts/event_catalog_draft.csv`. It includes 10 [FDIC failed-bank records](https://www.fdic.gov/bank-failures/failed-bank-list) and the six source documents below. The three 2023 bank cases also link to their specific [Silicon Valley Bank](https://www.fdic.gov/news/press-releases/2023/pr23016.html), [Signature Bank](https://www.fdic.gov/news/press-releases/2023/pr23018.html), and [First Republic Bank](https://www.fdic.gov/news/press-releases/2023/pr23034.html) FDIC releases. The date is the document's stated date or the bank's closing date. It is not automatically the first time the underlying situation became public.

| Event | Official source | Timing recorded |
| --- | --- | --- |
| WHO pandemic characterization, 2020-03-11 | [WHO speech](https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020) | Date only |
| March 2020 US employment report, released 2020-04-03 | [BLS archived release](https://www.bls.gov/news.release/archives/empsit_04032020.htm) | Embargo until 08:30 EDT, 12:30 UTC |
| April 2020 US housing report, released 2020-05-19 | [Census archived release](https://www.census.gov/construction/nrc/pdf/newresconst_202004.pdf) | For release at 08:30 EDT, 12:30 UTC |
| UN statement on Russian military operations, 2022-02-24 | [UN statement](https://www.un.org/sg/en/content/sg/statements/2022-02-24/statement-the-secretary-general-ukraine) | Date only |
| Expanded US sanctions against Russia, 2022-02-24 | [US Treasury release](https://home.treasury.gov/news/press-releases/jy0608) | Date only |
| FOMC rate decision, 2022-03-16 | [Federal Reserve statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm) | For release at 14:00 EDT, 18:00 UTC |

`source_release_timestamp_utc` stores a source's stated release or embargo time. `first_public_timestamp_utc` is blank for all 16 cases. The latter needs separate verification before an event-window test. The invasion and sanctions are on the same date; treating either as the sole cause of a market move would overstate what this catalogue can show.

## What the four team members should do next

1. **Data owner:** Freeze a research snapshot by keeping the raw files and their manifest hashes together. Choose a handful of housing vintages from the Census archive if housing will become a numerical input. Record observation month, publication time, the value as first released, and later revisions in separate columns.
2. **Numerical-model owner:** Define the forecast decision time for every proposed experiment. Keep the same-day oil/yield table as a conditional analysis unless the input shocks are supplied as hypothetical assumptions. Review missing values and split counts in `data/processed/final_data_audit.json`.
3. **Language-model owner:** Review all 20 rows in `data/drafts/scenario_examples.csv`. Confirm event types and affected sectors; keep unstated numbers blank. Only move reviewed examples into `data/templates/scenario_labels.csv` or a new labeled file.
4. **Event/evaluation owner:** Pick a small set of nonoverlapping events from the 16 candidates. Find the first public announcement timestamp and exact source, note what the market already knew, and define the first eligible ETF session. Record uncertainty rather than guessing a time.

Run `.venv/bin/python scripts/validate_drafts.py` and `.venv/bin/python scripts/audit_data.py` after changing drafts or rebuilding data. A passing check confirms file consistency, not that a scenario label or market explanation is correct.
