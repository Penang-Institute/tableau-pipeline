# Dashboard freshness report, 2026-11-22

STALE: 9 | NO ACCESS: 3 | UNTRACKED: 2

STALE = the data changed after the workbook was last published, so it needs a Refresh and Publish in Tableau Desktop.

| Dashboard | Verdict | Tableau published | Data last changed | Feed |
|---|---|---|---|---|
| Graduate Employability | **STALE** | 2024-10-22 | 2026-10-07 | manual |
| Household Income | **STALE** | 2024-10-22 | 2026-11-19 | opendosm |
| Residential Property | **STALE** | 2024-11-25 | 2026-11-11 | manual |
| Health Statistics | **STALE** | 2024-11-28 | 2026-11-19 | mixed |
| Gender in Penang | **STALE** | 2026-01-09 | 2026-10-07 | mixed |
| Gross Domestic Product | **STALE** | 2026-02-27 | 2026-11-19 | mixed |
| Population and Demographics | **STALE** | 2026-06-05 | 2026-11-19 | opendosm |
| Trade Statistics | **STALE** | 2026-10-26 | 2026-11-14 | manual |
| Consumer Price Index | **STALE** | 2026-11-13 | 2026-11-19 | opendosm |
| Maritime (archived) | **NO ACCESS** | 2024-11-11 | n/a | manual |
| Labour Force | **NO ACCESS** | 2024-12-02 | n/a | opendosm |
| Air Transport Statistics (archived) | **NO ACCESS** | 2024-12-02 | n/a | manual |
| State Finance | **UNTRACKED** | 2024-11-28 | n/a | untracked |
| Approved Manufacturing Investment | **UNTRACKED** | 2026-10-05 | n/a | untracked |

Newest full DOSM trade publication upstream (JAD 12): **2026-09**. Compare with the newest JAD12_inbox file under Trade below.

## Sources

### Graduate Employability (sector/grad)

- graduates: changed 2026-10-07, latest 2024

### Household Income (social/hhinc)

- gross_income: changed 2026-11-19, latest 2024

### Residential Property (sector/prop)

- transactions: changed 2026-11-11, latest Sep-20
- house_prices: changed 2026-11-11, latest 2023
- unsold: changed 2026-11-11, latest Sep-20
- newly_launched: changed 2026-11-11, latest Sep-20

### Health Statistics (sector/health)

- health tabs: changed 2026-11-19, latest 2025-05-31

### Gender in Penang (social/gender)

- salaries: changed 2026-03-04, latest 2024
- women_stats: changed 2026-10-07, latest 2024
- parliament file: NO ACCESS (HttpError)

### Gross Domestic Product (econ/gdp)

- gdp_econ_activity: changed 2026-11-19, latest 2024
- gdp_capita_states: changed 2026-11-19, latest 2025
- gdp_quarterly folder: changed 2026-11-19, latest 5 files, newest: gdp_qtr.csv
- GDP_inbox (Hajar): changed 2026-07-03, latest 2 files, newest: Jadual KDNK Malaysia dan Negeri tahun 2023-2025.xlsx

### Population and Demographics (social/pop)

- population_opendosm: changed 2026-11-19, latest 2026
- population_ethnicity: changed 2026-11-19, latest Row Labels
- demo_mukim: NO ACCESS (HttpError)
- population_by_state: changed 2026-11-19, latest 2026

### Trade Statistics (econ/trade)

- trade (exit/entry): changed 2026-11-14, latest 2026-09-01
- HS monthly folder: changed 2026-11-08, latest 6 files, newest: penang_monthly_exim_hs_country.csv
- JAD12_inbox (Hajar): changed 2026-11-03, latest 4 files, newest: trade_2026-09.xlsx
- METS HS inbox (Hajar): changed 2026-11-03, latest 6 files, newest: trade_by_channel__rm___multi_trade_flow__Sept 2026.csv

### Consumer Price Index (econ/cpi)

- CPI opendosm folder: changed 2026-11-19, latest 6 files, newest: cpi_5d.csv

### Maritime (archive/maritime)

- maritime_cargo: NO ACCESS (HttpError)

### Labour Force (econ/labour)

- principal: NO ACCESS (HttpError)
- lfpr: NO ACCESS (HttpError)
- age: NO ACCESS (HttpError)
- highest_cert: NO ACCESS (HttpError)
- marital: NO ACCESS (HttpError)
- occupation: NO ACCESS (HttpError)
- sector: NO ACCESS (HttpError)
- occupation_all_states: NO ACCESS (HttpError)
- labour_demographics: NO ACCESS (HttpError)

### Air Transport Statistics (archive/air)

- passengers: NO ACCESS (HttpError)
- aircraft: NO ACCESS (HttpError)
- airport_cargo: NO ACCESS (HttpError)

### State Finance (sector/finance)

- no source mapped yet

### Approved Manufacturing Investment (sector/manf)

- no source mapped yet

