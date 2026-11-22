#!/usr/bin/env python3
"""Weekly freshness check: is every site dashboard as new as its data?

For each dashboard in freshness/dashboards.yaml this compares
  - when the data behind it last CHANGED (content fingerprint of the Google
    Sheets / Drive files, remembered in freshness/state.json), against
  - when the Tableau Public workbook was last PUBLISHED.
Tableau Public bakes a static extract at publish time, so data that changed
after the last publish means the public dashboard is stale: STALE.

Writes freshness/report.md and freshness/screenshots/*.png, and exits 1 when
a live (non-archived) dashboard is stale or could not be verified, so the scheduled run emails.

    python freshness_check.py            # full run
    python freshness_check.py --no-save  # report only, leave state.json alone
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "freshness"
CONFIG = OUT / "dashboards.yaml"
STATE = OUT / "state.json"
REPORT = OUT / "report.md"
SHOTS = OUT / "screenshots"

TABLEAU_API = "https://public.tableau.com/profile/api/single_workbook/"
TABLEAU_IMG = "https://public.tableau.com/static/images/{prefix}/{wb}/{view}/1.png"
DOSM_TRADE = "https://storage.dosm.gov.my/trade/trade_{ym}.xlsx"
DOSM_LOOKBACK_MONTHS = 8
PERIOD_COL = re.compile(r"^(date|year|month|quarter|period|tahun)$", re.I)


# ---------- pure logic (covered by tests/test_freshness.py) ----------

def next_state_entry(old: dict | None, new_hash: str, modified: str, today: str) -> dict:
    """State for one source. changed_at only moves when the content changes.

    First sighting is seeded from Drive's modifiedTime: the content cannot
    have changed later than that, so it is the honest upper bound.
    """
    if old is None:
        return {"hash": new_hash, "changed_at": modified}
    if old["hash"] != new_hash:
        # Drive's modifiedTime is the real change date when it is known; using
        # the run date would flag a dashboard republished since the change.
        return {"hash": new_hash, "changed_at": min(today, modified) if modified else today}
    return dict(old)


def verdict(source_count: int, error_count: int, changed_at: str | None, published: str) -> str:
    if source_count == 0:
        return "UNTRACKED"
    if changed_at and changed_at > published:  # ISO dates compare as strings
        return "STALE"
    if error_count:
        return "NO ACCESS"
    return "OK"


def latest_period(tabs: list[list[list]]) -> str:
    """Best-effort newest value in any date/year-like column. Display only."""
    found = [
        str(row[i])
        for rows in tabs if rows
        for i, header in enumerate(rows[0]) if PERIOD_COL.match(str(header).strip())
        for row in rows[1:] if len(row) > i and str(row[i]).strip()
    ]
    return max(found, default="")


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ---------- I/O ----------

def curl(*args: str) -> str:
    # curl, not urllib/requests: Tableau's edge rejects Python's TLS fingerprint
    # (same reason as pistats/scripts/fetch_view_counts.py)
    return subprocess.run(
        ["curl", "-sfL", "--max-time", "30", "-H", "User-Agent: Mozilla/5.0", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def google_services():
    from googleapiclient.discovery import build
    from pipeline.fetchers.gdrive import _get_credentials  # read-only scopes

    creds = _get_credentials()
    return build("drive", "v3", credentials=creds), build("sheets", "v4", credentials=creds)


def read_source(drive, sheets, src: dict) -> dict:
    """Return {key, hash, modified, detail} for one sheet / folder / file."""
    if "sheet" in src:
        sid = src["sheet"]
        meta = drive.files().get(fileId=sid, fields="modifiedTime", supportsAllDrives=True).execute()
        tabs = src.get("tabs") or [
            s["properties"]["title"]
            for s in sheets.spreadsheets().get(
                spreadsheetId=sid, fields="sheets.properties.title").execute()["sheets"]
        ]
        ranges = ["'" + t.replace("'", "''") + "'" for t in tabs]
        values = [
            v.get("values", [])
            for v in sheets.spreadsheets().values().batchGet(
                spreadsheetId=sid, ranges=ranges).execute()["valueRanges"]
        ]
        return {"key": f"sheet:{sid}:{','.join(src.get('tabs', []))}", "hash": sha(values),
                "modified": meta["modifiedTime"][:10], "detail": latest_period(values)}
    if "folder" in src:
        # ponytail: single page of 1000 files; add paging if a folder outgrows that
        files = drive.files().list(
            q=f"'{src['folder']}' in parents and trashed = false", pageSize=1000,
            fields="files(name,md5Checksum,modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        newest = max(files, key=lambda f: f["modifiedTime"], default=None)
        marks = sorted((f["name"], f.get("md5Checksum") or f["modifiedTime"]) for f in files)
        return {"key": f"folder:{src['folder']}", "hash": sha(marks),
                "modified": newest["modifiedTime"][:10] if newest else "",
                "detail": f"{len(files)} files, newest: {newest['name']}" if newest else "empty"}
    meta = drive.files().get(
        fileId=src["file"], fields="name,md5Checksum,modifiedTime", supportsAllDrives=True).execute()
    return {"key": f"file:{src['file']}", "hash": meta.get("md5Checksum") or meta["modifiedTime"],
            "modified": meta["modifiedTime"][:10], "detail": meta["name"]}


def tableau_published(workbook: str) -> str:
    ms = json.loads(curl(TABLEAU_API + workbook))["lastPublishDate"]
    # UTC, to match Drive's modifiedTime and the dates in state.json
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date().isoformat()


def save_screenshot(dash: dict) -> None:
    url = TABLEAU_IMG.format(prefix=dash["workbook"][:2], wb=dash["workbook"], view=dash["view"])
    curl("-o", str(SHOTS / (dash["page"].replace("/", "_") + ".png")), url)


def newest_dosm_trade(today: date) -> str:
    """Newest full DOSM trade publication (carries JAD 12) that exists upstream."""
    y, m = today.year, today.month
    for _ in range(DOSM_LOOKBACK_MONTHS):
        ym = f"{y}-{m:02d}"
        if subprocess.run(["curl", "-sfIL", "--max-time", "30", "-o", "/dev/null",
                           DOSM_TRADE.format(ym=ym)]).returncode == 0:
            return ym
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return "not found"


# ---------- run ----------

def check_dashboard(dash: dict, drive, sheets, old_state: dict, today: str) -> tuple[dict, dict]:
    """Return (report row, state entries for this dashboard's sources)."""
    entries, lines, errors = {}, [], 0
    for src in dash["sources"]:
        try:
            got = read_source(drive, sheets, src)
        except Exception as e:  # unshared / deleted source: report it, keep going
            errors += 1
            lines.append(f"{src['name']}: NO ACCESS ({type(e).__name__})")
            continue
        entry = next_state_entry(old_state.get(got["key"]), got["hash"], got["modified"], today)
        entries[got["key"]] = entry
        lines.append(f"{src['name']}: changed {entry['changed_at']}"
                     + (f", latest {got['detail']}" if got["detail"] else ""))
    try:
        published = tableau_published(dash["workbook"])
    except Exception as e:
        return ({**dash, "verdict": "TABLEAU ERROR", "published": "?", "changed_at": "",
                 "lines": lines + [f"Tableau API failed: {e}"]}, entries)
    try:
        save_screenshot(dash)
    except Exception:  # a missing image must not hide the verdict
        lines.append("screenshot unavailable")
    changed_at = max((e["changed_at"] for e in entries.values()), default=None)
    return ({**dash, "verdict": verdict(len(dash["sources"]), errors, changed_at, published),
             "published": published, "changed_at": changed_at or "", "lines": lines}, entries)


def render(rows: list[dict], today: str, dosm_trade: str) -> str:
    order = {"STALE": 0, "TABLEAU ERROR": 1, "NO ACCESS": 2, "UNTRACKED": 3, "OK": 4}
    rows = sorted(rows, key=lambda r: (order[r["verdict"]], r["published"]))
    counts = {v: sum(r["verdict"] == v for r in rows) for v in order}
    out = [
        f"# Dashboard freshness report, {today}", "",
        " | ".join(f"{v}: {n}" for v, n in counts.items() if n), "",
        "STALE = the data changed after the workbook was last published, so it needs "
        "a Refresh and Publish in Tableau Desktop.", "",
        "| Dashboard | Verdict | Tableau published | Data last changed | Feed |",
        "|---|---|---|---|---|",
    ]
    out += [
        f"| {r['title']}{' (archived)' if r.get('archived') else ''} | **{r['verdict']}** "
        f"| {r['published']} | {r['changed_at'] or 'n/a'} | {r['feed']} |"
        for r in rows
    ]
    out += ["", f"Newest full DOSM trade publication upstream (JAD 12): **{dosm_trade}**. "
            "Compare with the newest JAD12_inbox file under Trade below.", "", "## Sources", ""]
    for r in rows:
        out += [f"### {r['title']} ({r['page']})", ""]
        out += [f"- {line}" for line in r["lines"]] or ["- no source mapped yet"]
        out += [""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-save", action="store_true", help="do not update state.json")
    args = ap.parse_args()

    today = datetime.now(timezone.utc).date().isoformat()
    dashboards = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["dashboards"]
    old_state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    SHOTS.mkdir(parents=True, exist_ok=True)
    drive, sheets = google_services()

    results = [check_dashboard(d, drive, sheets, old_state, today) for d in dashboards]
    rows = [row for row, _ in results]
    # keep entries for sources we could not read this week, so one outage
    # does not reset their history
    new_state = {**old_state, **{k: v for _, entries in results for k, v in entries.items()}}

    if not args.no_save:  # state first, so a report failure cannot lose a week of history
        STATE.write_text(json.dumps(new_state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(render(rows, today, newest_dosm_trade(date.today())) + "\n", encoding="utf-8")

    for r in rows:
        print(f"{r['verdict']:<14}{r['published']:<12}{r['title']}")
    print(f"\nreport: {REPORT}")
    # anything unverified on a live page fails the run, so a revoked service
    # account or a blocked Tableau API cannot pass as a quiet green week
    needs_attention = {"STALE", "NO ACCESS", "TABLEAU ERROR"}
    return 1 if any(r["verdict"] in needs_attention and not r.get("archived") for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
