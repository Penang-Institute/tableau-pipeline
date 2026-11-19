# Pipeline Maintenance Guide — Keeping Data in Sync

**Created:** 12 June 2026, after the June 2026 incident.
**Author:** Subashanan Nair · Data Scientist

This guide explains how to prevent the two failure modes that caused the
dashboard and Google Drive to fall behind in April–June 2026:

1. **Dashboard sync broke silently** — the keyPenangMetrics → pistats bridge
   workflow used a personal access token (`PRIVATE_TOKEN_GITHUB`) that expired
   ~1 June 2026. Failures showed only in the Actions tab; nobody was notified.
2. **Google Drive went stale through inaction** — this tableau-pipeline is run
   manually, and no one ran it between 30 March and 12 June while DOSM
   published its April/May releases.

---

## Part 1 — One-time setup (do once, ~15 minutes)

### Step 1: Turn on GitHub failure notifications

Silent failure was the core problem. Make GitHub email you when any
workflow fails:

1. Go to <https://github.com/settings/notifications>
2. Under **System → Actions**, enable **Email** for failed workflows
   ("Only notify for failed workflows" checked).
3. **Watch** the three repos so notifications cover scheduled runs too:
   - <https://github.com/Penang-Institute/keyPenangMetrics> → Watch → All activity
   - <https://github.com/Penang-Institute/pistats> → Watch → All activity
   - (optional) Penang-Institute/tableau-pipeline

### Step 2: Bump `actions/checkout` to v5 (deadline: 16 June 2026)

GitHub forces actions onto Node 24 from **16 June 2026**; `checkout@v4` is
deprecated and may break. Update it in:

- `pistats/.github/workflows/update-submodules.yml`
- `pistats/.github/workflows/quarto-publish.yml`
- `keyPenangMetrics/.github/workflows/*.yaml` (all files using checkout@v4)

Change `uses: actions/checkout@v4` → `uses: actions/checkout@v5`, commit, push.

### Step 3: Never reintroduce a PAT into workflows

The permanent fix (12 Jun 2026) was `pistats/.github/workflows/update-submodules.yml`,
which pulls submodule updates **from inside pistats** using the ephemeral
`GITHUB_TOKEN`. That token is issued per-run and cannot expire.

Rule of thumb: if a workflow needs to write to **its own repo**, use
`GITHUB_TOKEN` with a `permissions:` block — never a stored PAT. Only
cross-repo pushes need stored credentials, and the design should be inverted
(have the target repo pull) to avoid them.

The old `update-parent.yaml` workflow in keyPenangMetrics is **disabled** —
do not re-enable it.

---

## Part 2 — Recurring routine (monthly, ~10 minutes)

DOSM publishes on a predictable calendar:

| Release | When | Affects |
|---|---|---|
| CPI (monthly) | ~3rd week of month | cpi, cpi_national, cpi_core transforms |
| PPI (monthly) | ~4th week of month | ppi transform |
| LFS labour force (monthly) | ~2nd week of month | bulk manifest files |
| GDP (quarterly) | mid Feb / May / Aug / Nov | gdp_quarterly transform |
| IPI / IOWRT (monthly) | ~2nd week of month | bulk manifest files |

**Run the pipeline near the end of each month** (after CPI + PPI are out).
Quarterly months (Feb/May/Aug/Nov) matter most — they also carry GDP.

### Step 1: Check what's new upstream (optional, 1 minute)

```bash
cd ~/Documents/02_projects/PENANG_INSTITUTE/tableau-pipeline
curl -sI https://storage.dosm.gov.my/cpi/cpi_2d_state.parquet | grep -i last-modified
curl -sI https://storage.dosm.gov.my/ppi/ppi.parquet          | grep -i last-modified
curl -sI https://storage.dosm.gov.my/gdp/gdp_qtr_nominal_supply.parquet | grep -i last-modified
```

If the dates are newer than your last run, there's new data.
(DOSM's storage server supports `HEAD` requests — no download needed.)

### Step 2: Run the pipeline

```bash
cd ~/Documents/02_projects/PENANG_INSTITUTE/tableau-pipeline

# Preview what would run
python3 -m pipeline.orchestrator --dry-run cpi cpi_national cpi_core ppi gdp_quarterly copy_opendosm

# Real run (~4 minutes; uploads only changed files)
python3 -m pipeline.orchestrator cpi cpi_national cpi_core ppi gdp_quarterly copy_opendosm
```

Expected final lines:

```
Drive sync complete: N uploaded, M unchanged, 2 on hold
Pipeline complete: 6/6 succeeded
```

The 2 on-hold files are intentional (`lfs_qtr_state.csv`, `ppi.csv` — see
`SKIP_FILES` in `pipeline/transforms/copy_opendosm.py`).

### Step 3: Trigger the Drive → PI Server robocopy

Today's Drive uploads reach the PI Server (`\\192.168.0.2`) only via the
robocopy job on the Windows machine. Run it (or confirm its schedule fired)
after each pipeline run. Logs land in `docs/logs/sync_*.log`.

### Step 4: Spot-check the dashboard (30 seconds)

Open <https://statistics.penanginstitute.org/> — the CPI card's period should
match the latest DOSM release. The site self-updates every **Thursday 12:00
UTC** via `pistats/update-submodules.yml`; if the period looks stale, check
<https://github.com/Penang-Institute/pistats/actions> for a red run.

---

## Part 3 — Optional: automate the pipeline run (kills failure mode #2)

The Drive pipeline still relies on a human remembering Part 2. Two options:

### Option A: launchd job on this Mac (no admin rights needed)

Create `~/Library/LaunchAgents/org.penanginstitute.tableau-pipeline.plist`
that runs the orchestrator weekly (e.g. Friday 10:00). Caveats:

- Mac must be awake at the scheduled time (launchd skips if powered off;
  it coalesces if asleep).
- `service_account.json` must remain at `pipeline/config/`.
- Check `/tmp/tableau-pipeline-cron.log` occasionally.

### Option B: GitHub Actions schedule (needs repo admin — ask the org owner)

A scheduled workflow in tableau-pipeline running the same orchestrator
command. Requires adding the service-account JSON as a repo secret
(`GOOGLE_SERVICE_ACCOUNT_JSON`), which only a repo **admin** can do.
This is the most robust option — runs regardless of any laptop being on —
but blocked until someone with admin access adds the secret.

---

## Part 4 — External Trade: drop raw files in the Drive inbox (Hajar)

External Trade is **semi-automated**: you no longer reshape anything by hand.
Your only job each month is to **download the raw publication and drop it into a
Google Drive inbox folder**. The pipeline (Part 2 Step 2, or the weekly run)
reshapes every file it finds into the exact format Tableau needs.

There are two datasets, each with its own inbox folder. The folder IDs live in
`pipeline/config/google_sheets_registry.yaml` under `trade.drive_files.inbox`
(JAD 12) and `trade_hs.drive_files.inbox` (METS). A repo admin creates the two
folders in the shared "Raw Data" drive once and pastes their IDs there
(they currently read `REPLACE_WITH_...`).

### a) Trade by exit/entry — DOSM JAD 12

1. Download the monthly **Monthly External Trade Statistics, Malaysia** Excel
   from eStatistik (the publication containing the **JAD 12** sheet).
2. No renaming needed — the data month is read from the JAD 12 sheet header
   (e.g. "APR 2026"). A `YYYY_MM` / Malay-month name in the file name is only a
   fallback if the header can't be read.
3. Drop it into the **JAD 12 inbox** folder. Leave older months in place —
   the pipeline rebuilds the full dataset from everything in the folder.

### b) Trade by commodity — METS Online

1. On **METS Online** (no login needed) follow:
   *Trade Statistics → Channel → State (Pulau Pinang) → Trade flow
   (Exports & Imports) → Frequency (Monthly) → the month/year **after** the
   latest you already have → Classification (HS2 Digit) → Product (Select all)
   → Partner country (Select all)*, then download.
2. You get one CSV for **exports** and one for **imports**. Keep the words
   `exports` / `imports` in each file name (e.g. `2026_02_exports.csv`) — the
   trade direction is read from the name.
3. Drop both into the **METS inbox** folder.

### When it takes effect

The next pipeline run (`python3 -m pipeline.orchestrator trade trade_hs`, or
the weekly GitHub Actions run) picks up the new files automatically. Output:
the `trade` Google Sheet `data` tab and
`output/<date>/penang_monthly_exim_hs_country.csv`. If a folder ID is still
`REPLACE_WITH_...`, the transform logs a warning and is skipped — ask the admin
to set the folder IDs.

> Note: METS column wording can change between releases. After the first real
> run, spot-check that `hs`, `country`, and the month columns came through; if a
> METS file produces zero rows, the log will say so — send the file for a quick
> mapping fix.

---

## Part 5 — The live master CSV: never open it in Excel

`Online Stats > Penang > Monthly > penang_monthly_exim_hs_country.csv` is the
file the External Trade dashboard reads. It holds about **2.2 million rows**
(Jan 2000 onward) — more than **twice Excel's hard ceiling of 1,048,575 rows**.

Opening it in Excel and saving does three things, silently and irreversibly:

1. **Truncates it** at 1,048,575 rows, discarding roughly 1.1 million.
2. **Strips leading zeros** from HS chapters — `01` becomes `1`.
3. **Destroys trade values** in rows that do survive (observed, mechanism not
   fully established).

Excel's "file not fully loaded" warning appears on open, not on save, and is
easy to click past. Nothing downstream flags the damage.

**The pipeline cannot repair this.** The Drive append is period-based: it skips
any month already present. A damaged month looks present, so it stays damaged
indefinitely, no matter how many times the pipeline runs.

**Only the pipeline writes to this file.** To look at the data, use any of:

- the `.parquet` copy in the same folder (opens in seconds, no row limit)
- `pandas.read_csv(...)` in Python
- the Tableau extract

If someone needs a subset, filter it in Python and export *that*, never the
master itself.

> The same applies to any pipeline-maintained CSV that has outgrown a
> spreadsheet. Check the row count before opening anything in Excel.

---

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---|---|---|
| `Bad credentials` in Actions log | A stored token expired | Replace design with `GITHUB_TOKEN` (see Part 1 Step 3); never just rotate the PAT |
| Dashboard stale but keyPenangMetrics renders green | pistats update-submodules.yml failing | Check pistats Actions tab; re-run with `gh workflow run update-submodules.yml --repo Penang-Institute/pistats` |
| Drive stale | Pipeline not run | Run Part 2 Step 2 |
| PI Server stale but Drive current | Robocopy not run / robocopy exit ≥ 8 | Re-run robocopy on Windows box; check `docs/logs/` |
| `Pipeline complete: N/6 succeeded` with N < 6 | A transform failed (network, schema change) | Re-run the failed transform alone: `python3 -m pipeline.orchestrator <name>`; check log |
| Upload count = 0 but upstream has new data | Size-match false negative (rare) | Delete the stale file on Drive and re-run |
| `trade`/`trade_hs` logs "inbox folder not configured" | Folder ID still `REPLACE_WITH_...` | Admin pastes the real Drive folder IDs into `google_sheets_registry.yaml` (Part 4) |
| Trade output missing recent months | Raw file not in the inbox, or name lacks `YYYY_MM` / `exports`/`imports` | Drop/rename the file per Part 4 and re-run `trade trade_hs` |
| Master CSV row count is **exactly 1,048,575** | Someone opened and saved it in Excel (Part 5) | Restore the last good version from Drive **File → Version history**. Do **not** append on top of a truncated file — the pipeline will skip the damaged months forever |
| Dashboard shows RM 0 for a whole trade direction across many months | Values wiped by an Excel save, or a month only partially present | Compare monthly totals against the METS source before trusting any of it; rebuild the affected span rather than appending |
| A country appears twice in the Trading Partner list, or its history stops abruptly | METS relabelled it (e.g. TURKEY → TURKIYE) | Add the mapping to `_COUNTRY_ALIASES` in `pipeline/transforms/trade_hs.py`. The dashboard control is a Tableau *parameter* with a hard-coded list, so an unmapped label is unselectable |

---

## Incident log

- **Jul 2026:** External Trade commodity dashboard showed **RM 0 exports for
  every month before Jul 2025**, and only ~10% of historical imports. Cause:
  the live master CSV was opened and saved in Excel on **5 Nov 2025** (Drive
  revision history), truncating it to exactly 1,048,575 rows, stripping HS
  leading zeros and wiping 24 years of export values. The pipeline could not
  self-heal it because the append skips months already present — the same
  reason a partially-truncated Jul 2025 survived a separate repair on 30 Jul.
  Rebuilt 31 Jul 2026 to **2,201,711 rows (Jan 2000 – May 2026, no gaps)** from
  the 2024-12-31 Drive revision plus fresh METS downloads for Dec 2024 – Jun
  2025. Verified against four independent sources: the published Tableau
  extract, the website parquet, the METS source and the pre-damage revision.
  Pipeline hardened in #11 (HS chapters stay padded; METS country labels
  normalised via `_COUNTRY_ALIASES`). `TURKEY` was merged into `TURKIYE`, which
  also required editing the workbook's country **parameter** — renaming in the
  data alone would have made that selection return nothing. See Part 5.

- **Jun 2026:** `PRIVATE_TOKEN_GITHUB` PAT expired ~1 Jun → pistats site
  stale 28 May–12 Jun. Fixed permanently via in-repo `update-submodules.yml`
  with ephemeral token. Drive also stale 30 Mar–12 Jun (pipeline simply not
  run); cleared with a full run on 12 Jun (32 files uploaded, 6/6 transforms).
