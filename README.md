# Tableau Data Pipeline

Python pipeline that fetches public data from OpenDOSM and other Malaysian government APIs, transforms it, and uploads to Google Drive for use in Penang Institute's Tableau dashboards.

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
| gdp_quarterly | OpenDOSM | Quarterly GDP by state |
| gdp_capita_states | OpenDOSM | GDP per capita by state |
| gdp_econ_activity | OpenDOSM | GDP by economic activity |
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
| trade | OpenDOSM | External trade statistics |
| trade_hs | OpenDOSM | Trade by HS classification |
| airports | OpenDOSM | Airport passengers, aircraft, cargo |
| demo_mukim | OpenDOSM | Demographics by mukim (subdistrict) |
| copy_opendosm | OpenDOSM | Bulk download from opendosm.tsv manifest |
| inferred_population | Derived | Inferred population from GDP data |

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
