# Tableau Data Pipeline

Python pipeline that fetches public data from OpenDOSM and other Malaysian government APIs, transforms it, and uploads to Google Drive for use in Penang Institute's Tableau dashboards.

## How it works

Two kinds of source feed the same pipeline, which reshapes each dataset into the
exact format its Tableau dashboard needs and delivers it to Google Drive.

```mermaid
flowchart TD
    A["OpenDOSM open data<br/>(CPI, PPI, GDP quarterly, …)"] -->|pipeline fetches automatically| P
    H["Hajar downloads a publication<br/>(JAD 12 trade · GDP table · METS commodity)"] -->|drops the file| BOX["Google Drive<br/>inbox folder"]
    BOX -->|pipeline lists & reads| P
    P["PIPELINE — GitHub Actions, weekly<br/>fetch → reshape → deliver"]
    P -->|append / upsert<br/>(history preserved, no orphan files)| D["Google Drive<br/>Sheet or CSV the dashboard reads"]
    D -.->|MANUAL: open workbook → Refresh → Republish| T["Tableau dashboards"]
```

- **(A) Automatic** — pulled straight from OpenDOSM each run (no human step).
- **(B) Semi-automatic ("inbox")** — Hajar downloads a publication that has no API
  and drops it into a shared Drive **inbox folder**; the pipeline reshapes it.
- **Delivery is append/upsert**, never a blind overwrite — older history a new
  publication no longer covers is preserved.
- **The last step is manual**: Tableau reads a baked-in extract, so a person must
  open each workbook, **Refresh**, and **Republish** for new data to appear.

Plain-text version of the same flow:

```
(A) OpenDOSM ──fetch──┐
                      ▼
Hajar ─download─► Drive inbox ─►  PIPELINE (weekly)  ─append/upsert─► Drive Sheet/CSV ┄┄(manual refresh)┄┄► Tableau
(B)                              fetch → reshape → deliver
```

## Setup

### Requirements

- Python 3.11+
- Google service account with Drive API access

### Installation

```bash
pip install -r requirements.txt
```

### Google Service Account

Place your service account JSON at:

```
pipeline/config/service_account.json
```

This file is gitignored and should never be committed.

## Usage

### Run all transforms

```bash
python -m pipeline.orchestrator
```

### Run specific transforms

```bash
python -m pipeline.orchestrator cpi ppi
```

### List available transforms

```bash
python -m pipeline.orchestrator --list
```

### Dry run (show what would execute)

```bash
python -m pipeline.orchestrator --dry-run
```

### Local CSV only (no Google Drive upload)

```bash
python run_csv_only.py cpi ppi
```

Output saved to `csv_output/YYYY-MM-DD/`.

## Transforms

| Transform | Source | Description |
|-----------|--------|-------------|
| cpi | OpenDOSM | Consumer Price Index by state and division |
| ppi | OpenDOSM | Producer Price Index (headline, absolute) |
| gdp_quarterly | OpenDOSM | Quarterly GDP (6 OpenDOSM files → `gdp_qtr.csv`) |
| gdp_capita_states | **Drive inbox** (`GDP_inbox`) | GDP per capita by state (DOSM "Table of GDP by State", Jad 44) |
| gdp_econ_activity | Drive (DOSM Excel) | GDP by economic activity |
| utilisation | OpenDOSM | Hospital bed utilisation by state |
| population | OpenDOSM | Population by state |
| population_opendosm | OpenDOSM | Population by state, age, ethnicity, sex |
| population_ethnicity | OpenDOSM | Population by ethnicity |
| hospitals | MOH GitHub | Hospital facilities and bed utilisation |
| labour | OpenDOSM | Labour force statistics |
| labour_demographics | OpenDOSM | Labour force by demographics |
| gender | OpenDOSM | Gender statistics (salaries, parliament) |
| graduates | OpenDOSM | Graduate output statistics |
| gross_income | OpenDOSM | Household gross income |
| property | OpenDOSM | Property transactions, prices, unsold units |
| trade | **Drive inbox** (`JAD12_inbox`) | External trade by exit/entry point (DOSM JAD 12) |
| trade_hs | **Drive inbox** (`METS_inbox`) | Trade by commodity, HS × country (METS Online) |
| airports | OpenDOSM | Airport passengers, aircraft, cargo |
| demo_mukim | OpenDOSM | Demographics by mukim (subdistrict) |
| copy_opendosm | OpenDOSM | Bulk download from opendosm.tsv manifest |
| inferred_population | Derived | Inferred population from GDP data |

## Inbox datasets (semi-automated)

These have no API — someone downloads the publication and drops it into a Drive
inbox folder (a member of the *Raw data* shared drive, so the pipeline already
has access). Folder IDs live in `google_sheets_registry.yaml`. Already-loaded
periods are skipped, so old files can stay in the folder.

| Dataset | Inbox folder | File Hajar drops | Pipeline output |
|---|---|---|---|
| Trade — exit/entry | `JAD12_inbox` | `05 JADUAL_TABLES_*.xlsx` | trade Sheet (append by month) |
| Trade — commodity | `METS_inbox` | `trade_by_channel…` (csv/xlsx) | `penang_monthly_exim_hs_country.csv` |
| GDP per capita by state | `GDP_inbox` | `Table of GDP by State, YYYY-YYYY.xlsx` | by-state Sheet (upsert by year) |

## Project Structure

```
pipeline/
  config/          # Data source URLs, Google Sheet/Drive IDs
  fetchers/        # Data fetching (OpenDOSM, GitHub, Google Drive)
  loaders/         # Output writers (CSV, Google Sheets, Google Drive)
  transforms/      # Individual data transforms
  utils/           # Shared helper functions
  orchestrator.py  # CLI entry point
tests/             # Unit tests
run_csv_only.py    # Local CSV runner (no auth needed)
```

## Configuration

- `pipeline/config/data_sources.yaml` -- API URLs and data source paths
- `pipeline/config/google_sheets_registry.yaml` -- Google Sheet IDs and Drive folder IDs

## What changed (2026 refresh)

- Fixed delivery so the canonical files update in place instead of writing dated
  orphans (CPI, PPI, National GDP `gdp_qtr.csv`).
- Append/upsert loaders that preserve history (CPI back to 1980, GDP to 2005) —
  see `loaders/drive_merge.py` and `append_new_months_to_sheet` /
  `upsert_rows_to_sheet` in `loaders/google_sheets.py`.
- Added the semi-automated **inbox** pattern for the no-API datasets (trade
  exit/entry, trade commodity, GDP by state).
- Corrected scrambled GDP-by-state values; brought trade exit/entry to May 2026.
