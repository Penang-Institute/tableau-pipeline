"""Append-merge a transform's output into an existing Drive CSV.

Some live files (CPI, PPI) carry history OpenDOSM no longer serves — e.g. the
CPI files go back to 1980, but OpenDOSM's parquet starts at 2010. A plain
overwrite would delete the pre-2010 tail. This loader instead appends only the
months not already present, preserving history and the existing date format,
and overwrites the file in place (same id → Tableau link intact).

ponytail: read-modify-write, fine for a weekly batch job (no concurrency). The
'never shrink' guard + Drive revision history are the safety net.
"""

from __future__ import annotations

import io
import logging
import os
import re
import tempfile
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _period(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, format="mixed", dayfirst=True).dt.to_period("M")


def merge_new_periods(
    cur: pd.DataFrame, new: pd.DataFrame, date_col: str = "date",
) -> pd.DataFrame:
    """Return cur plus only the rows of new whose month isn't already in cur.

    New rows are reformatted to match cur's date style (ISO vs dd/mm/yyyy).
    Pure function — no I/O — so the merge logic is unit-testable.
    """
    if cur.empty:
        return new.copy()
    sample = str(cur[date_col].iloc[0])
    iso = bool(re.match(r"\d{4}-\d{2}-\d{2}", sample))
    out_fmt = "%Y-%m-%d" if iso else "%d/%m/%Y"

    new = new.copy()
    new[date_col] = pd.to_datetime(
        new[date_col], format="mixed", dayfirst=True
    ).dt.strftime(out_fmt)

    existing_periods = set(_period(cur[date_col]))
    add = new[~_period(new[date_col]).isin(existing_periods)]
    if add.empty:
        return cur.copy()
    return pd.concat([cur, add[cur.columns]], ignore_index=True)


def _drive_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def append_periods_to_drive_csv(
    df_new: pd.DataFrame, folder_id: str, file_name: str, date_col: str = "date",
) -> None:
    """Append new months from df_new into the live Drive CSV, in place.

    If the file doesn't exist yet, creates it from df_new. Refuses to write a
    result smaller than what's already there (guards against history loss).
    """
    from googleapiclient.http import MediaFileUpload

    service = _drive_service()
    query = f"name='{file_name}' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(
        q=query, fields="files(id)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute().get("files", [])

    if existing:
        fid = existing[0]["id"]
        cur = pd.read_csv(
            io.BytesIO(service.files().get_media(
                fileId=fid, supportsAllDrives=True).execute()),
            dtype={date_col: str},
        )
        merged = merge_new_periods(cur, df_new, date_col)
        if len(merged) < len(cur):
            raise RuntimeError(
                f"Refusing to shrink {file_name}: {len(cur)} -> {len(merged)} rows"
            )
        if len(merged) == len(cur):
            logger.info("%s already current (%d rows)", file_name, len(cur))
            return
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        merged.to_csv(tmp.name, index=False)
        tmp.close()
        service.files().update(
            fileId=fid, media_body=MediaFileUpload(tmp.name, mimetype="text/csv"),
            supportsAllDrives=True,
        ).execute()
        logger.info("Appended into %s: %d -> %d rows", file_name, len(cur), len(merged))
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df_new.to_csv(tmp.name, index=False)
        tmp.close()
        service.files().create(
            body={"name": file_name, "parents": [folder_id]},
            media_body=MediaFileUpload(tmp.name, mimetype="text/csv"),
            fields="id", supportsAllDrives=True,
        ).execute()
        logger.info("Created %s in folder %s (%d rows)", file_name, folder_id, len(df_new))
