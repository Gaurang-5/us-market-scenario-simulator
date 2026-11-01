# Free data sources and team setup

## Data to consider next

The project already has Shiller monthly market history, Kenneth French's US daily market and industry returns, modern ETF prices from Tiingo, three FRED series, geopolitical risk, Census housing starts, and FDIC bank failures. French is the researcher's surname; these files describe US stocks. Add a new source only when it answers a specific scenario question. Record its date range, units, release dates, and reuse conditions before merging it with the market outcomes.

| Question | Free source | What to collect | Important limit |
| --- | --- | --- | --- |
| What happened to oil? | [U.S. EIA Open Data](https://www.eia.gov/opendata/) | Daily WTI spot price | Use a direct EIA series and cite EIA. [EIA allows reuse of its government data](https://www.eia.gov/about/copyrights_reuse.php). |
| Did Treasury yields move? | [U.S. Treasury daily rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=2026&type=daily_treasury_yield_curve) and [CSV archive](https://home.treasury.gov/interest-rates-data-csv-archive/) | Daily 10-year Treasury par yield | The Treasury par yield and the Fed policy rate are different variables. |
| Was housing weak? | [Census historical housing series](https://www.census.gov/construction/nrc/data/series.html) | Monthly housing starts and permits | Align by publication date; the observation month was not known at its start. |
| Was inflation or employment changing? | [BLS data API](https://www.bls.gov/developers/) | CPI, unemployment, payroll employment | Align by release date. [BLS publishes its data as public domain](https://www.bls.gov/opub/copyright-information.htm). |
| Was geopolitical risk high? | [Caldara-Iacoviello GPR index](https://www.policyuncertainty.com/gpr.html) | Historical monthly index from 1900; modern index from 1985 | It measures news-based risk, not a verified list of wars. The site identifies a CC BY 4.0 license and requests citation. |
| Did a US bank fail? | [FDIC failed-bank list](https://www.fdic.gov/bank-failures/failed-bank-list) | Bank name and failure date | Add the first public announcement time separately when evaluating immediate market reactions. |
| Was there a Fed decision? | [Federal Reserve FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | Decision date, statement, and announced policy change | Record announcement time, not just meeting date. |
| Was the economy later classified as in recession? | [NBER business-cycle dates](https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions) | Peak and trough months | These labels are retrospective; do not use them as if they were known on the historical scenario date. |

Free access does not automatically permit sharing downloaded data. Tiingo's free plan is for personal internal use, so share the collection code and source links in GitHub while each teammate downloads data under their own permitted access. Do not put tokens or generated market-price files into the repository. See [Tiingo's license description](https://www.tiingo.com/about/pricing).

## Put the code on GitHub

This directory is already a local Git repository, but it has no commit or remote yet. Run these commands in the project directory after reviewing the staged files:

```sh
git add .gitignore README.md requirements.txt scripts tests docs data/templates data/drafts
git diff --cached --stat
git diff --cached --check
git commit -m "Add reproducible market dataset pipeline"
gh auth login
gh repo create us-market-scenario-simulator --private --source=. --remote=origin --push
```

`gh auth login` is needed only if GitHub CLI is not already authenticated. Choose a private repository while the team is organizing the project. GitHub Free supports collaborators on private repositories. On GitHub, open **Settings → Collaborators → Add people** and invite the other three GitHub usernames. Send them the repository link, not the data files. [GitHub collaborator instructions](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository).

## Each teammate's setup

```sh
git clone https://github.com/OWNER/us-market-scenario-simulator.git
cd us-market-scenario-simulator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_dataset.py
.venv/bin/python scripts/collect_context.py
.venv/bin/python scripts/collect_etfs.py coverage
```

Replace `OWNER` with the GitHub account that created the repository. Each teammate who uses Tiingo should set their own API token locally and run `scripts/collect_etfs.py download`. Then run `scripts/build_model_tables.py`, `scripts/evaluate_baseline.py`, `scripts/build_event_drafts.py`, `scripts/validate_drafts.py`, and `scripts/audit_data.py`. The `.gitignore` excludes `.venv/`, tokens in `.env` files, and `data/raw/` and `data/processed/`. Before every push, run `git status --short` and check that no downloaded data or secret is staged. Read [Data status](DATA_STATUS.md) before choosing new features or event tests.

## Work without overwriting each other

One person owns each piece of work: source collection, numerical labels/model, scenario labeling/Mistral, and CLI/evaluation. Create a branch for each change, then open a pull request for a teammate to review:

```sh
git switch -c data/eia-oil
# edit your assigned files
git add scripts docs
git commit -m "Add EIA oil collection"
git push -u origin data/eia-oil
```

Merge after checking the changed files and running the relevant command locally. Keep a source URL and units for every new data column.
