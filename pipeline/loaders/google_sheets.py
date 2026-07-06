"""Write DataFrames to Google Sheets via gspread + service account.

Replaces the per-script googledrive/googlesheets4 OAuth pattern in R
with a single service account that works in CI/CD without interactive auth.

Setup:
  1. Create a service account in Google Cloud Console
  2. Download the JSON key file
  3. Share each target Google Sheet with the service account email
  4. Set GOOGLE_APPLICATION_CREDENTIALS env var to the key file path,
     or place the key at pipeline/config/service_account.json
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# Retry defaults for Google API calls
_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 2  # seconds

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_sheets_registry() -> dict:
    with open(_CONFIG_DIR / "google_sheets_registry.yaml") as f:
        return yaml.safe_load(f)


def _get_gspread_client():
    """Authenticate with Google Sheets using a service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)


def dataframe_to_rows(df: pd.DataFrame) -> list[list[str]]:
    """Sheet-safe cell values: NaN/NaT/None -> '' and everything else -> str.

    pandas 3's astype(str) keeps missing values as float NaN (pandas 2 turned
    them into the literal string 'nan'), and raw NaN/inf floats break the
    Sheets API's JSON body. Blanking missing values first is correct on both
    versions — and empty cells beat literal 'nan' text in the sheet anyway.
    """
    out = df.astype(object)
    return out.where(pd.notna(out), "").astype(str).values.tolist()


def write_sheet(
    df: pd.DataFrame,
    spreadsheet_id: str,
    sheet_name: str,
    retries: int = _DEFAULT_RETRIES,
) -> None:
    """Write a DataFrame to a specific sheet tab, replacing all content.

    Equivalent to R's googlesheets4::sheet_write().
    Retries with exponential backoff on transient failures.
    """
    for attempt in range(retries):
        try:
            gc = _get_gspread_client()
            spreadsheet = gc.open_by_key(spreadsheet_id)

            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except Exception as e:
                logger.info("Worksheet '%s' not found, creating new: %s", sheet_name, e)
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1, cols=1)

            worksheet.clear()

            # Convert all values AND headers to strings to avoid JSON errors
            # (a NaN column name from a read sheet is a non-JSON-compliant float).
            header = [str(c) for c in df.columns]
            values = dataframe_to_rows(df)
            worksheet.update([header] + values)

            logger.info(
                "Wrote %d rows to sheet '%s' in %s", len(df), sheet_name, spreadsheet_id
            )
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed writing sheet '%s' in %s: %s — retrying in %ds",
                attempt + 1, sheet_name, spreadsheet_id, e, wait,
            )
            time.sleep(wait)


def append_new_months_to_sheet(
    df_new: pd.DataFrame,
    spreadsheet_id: str,
    sheet_name: str,
    date_col: str = "Date",
    retries: int = _DEFAULT_RETRIES,
) -> None:
    """Append only the months not already present in the sheet tab, in place.

    Preserves existing rows and their formatting (never rewrites history).
    New rows are matched to the existing date style and column order, and
    written with USER_ENTERED so dates/numbers land as the same cell types
    already in the sheet. NaN values become blank cells.

    Used for accumulating sources where a full overwrite would be unsafe
    (e.g. trade — the sheet carries history back to 2018 that a single
    monthly drop must not clobber).
    """
    from pipeline.loaders.drive_merge import select_new_period_rows

    for attempt in range(retries):
        try:
            gc = _get_gspread_client()
            ws = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
            values = ws.get_all_values()
            if not values:  # empty tab — seed it with header + all rows
                write_sheet(df_new, spreadsheet_id, sheet_name)
                return
            header = values[0]
            cur = pd.DataFrame(values[1:], columns=header)
            add = select_new_period_rows(cur, df_new, date_col)
            if add.empty:
                logger.info("Sheet '%s' already current (%d rows)", sheet_name, len(cur))
                return
            rows = [
                ["" if pd.isna(v) else v for v in row]
                for row in add[header].itertuples(index=False, name=None)
            ]
            ws.append_rows(rows, value_input_option="USER_ENTERED")
            logger.info(
                "Appended %d rows to sheet '%s' in %s (%d -> %d)",
                len(rows), sheet_name, spreadsheet_id, len(cur), len(cur) + len(rows),
            )
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed appending to '%s' in %s: %s — retrying in %ds",
                attempt + 1, sheet_name, spreadsheet_id, e, wait,
            )
            time.sleep(wait)


def upsert_rows_to_sheet(
    df_new: pd.DataFrame,
    spreadsheet_id: str,
    sheet_name: str,
    key_cols: list[str],
    retries: int = _DEFAULT_RETRIES,
) -> None:
    """Replace existing rows whose key matches df_new, keep the rest, write back.

    Unlike append (which only adds new periods), this is an upsert: rows whose
    key (e.g. State+Year) appears in df_new are replaced with the new values
    (revisions), rows whose key is NOT in df_new are preserved (older history a
    newer publication no longer covers), and brand-new keys are added. Full-tab
    rewrite. Used for annual GDP, where each publication revises recent years
    but only spans the last ~10.
    """
    for attempt in range(retries):
        try:
            gc = _get_gspread_client()
            ws = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
            values = ws.get_all_values()
            if not values:
                write_sheet(df_new, spreadsheet_id, sheet_name)
                return
            header = values[0]
            cur = pd.DataFrame(values[1:], columns=header)
            new = pd.DataFrame(dataframe_to_rows(df_new[header]), columns=header)

            def _key(df: pd.DataFrame):
                return df[key_cols].astype(str).agg("␟".join, axis=1)

            new_keys = set(_key(new))
            kept = cur[~_key(cur).isin(new_keys)]
            out = pd.concat([kept, new], ignore_index=True)
            ws.clear()
            ws.update([header] + out.values.tolist())
            logger.info(
                "Upserted %d rows into '%s' (%d kept + %d new = %d)",
                len(new), sheet_name, len(kept), len(new), len(out),
            )
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed upserting '%s' in %s: %s — retrying in %ds",
                attempt + 1, sheet_name, spreadsheet_id, e, wait,
            )
            time.sleep(wait)


def write_to_main_workbook(df: pd.DataFrame, sheet_key: str) -> None:
    """Write a DataFrame to a named sheet in the main dashboard workbook.

    Uses the google_sheets_registry.yaml to look up sheet names.
    Example: write_to_main_workbook(cpi_df, "cpi_by_state")
    """
    from pipeline.config.registry import get_main_workbook_id, get_main_workbook_sheet

    workbook_id = get_main_workbook_id()
    sheet_name = get_main_workbook_sheet(sheet_key)
    write_sheet(df, workbook_id, sheet_name)


def get_drive_folder_id(key: str) -> str:
    """Look up a Google Drive folder ID from the registry.

    Delegates to pipeline.config.registry for the actual lookup.
    """
    from pipeline.config.registry import get_drive_folder_id as _get_folder_id

    return _get_folder_id(key)


def update_drive_file(
    file_id: str,
    file_path: str | Path,
    retries: int = _DEFAULT_RETRIES,
) -> None:
    """Replace an existing Drive file's content in place, by ID.

    The Python equivalent of R's googledrive::drive_update(as_id(id), media=path):
    keeps the same file ID/name (so any Tableau link stays intact) and only
    swaps the bytes. Use when the target is a known file, not a folder.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.service_account import Credentials

    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)

    for attempt in range(retries):
        try:
            service.files().update(
                fileId=file_id,
                media_body=MediaFileUpload(str(file_path), mimetype="text/csv"),
                supportsAllDrives=True,
            ).execute()
            logger.info("Updated Drive file %s from %s", file_id, file_path)
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed updating file %s: %s — retrying in %ds",
                attempt + 1, file_id, e, wait,
            )
            time.sleep(wait)


def upload_to_drive(
    file_path: str | Path,
    folder_id: str,
    file_name: str | None = None,
    retries: int = _DEFAULT_RETRIES,
    date_tag: bool = False,
) -> None:
    """Upload a file to a Google Drive folder.

    Equivalent to R's googledrive::drive_put().
    If date_tag is True, appends today's date to the filename so a new
    file is created instead of overwriting the existing one.
    Retries with exponential backoff on transient failures.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/drive",
    ]
    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    service = build("drive", "v3", credentials=creds)

    file_path = Path(file_path)
    name = file_name or file_path.name

    if date_tag:
        from pipeline.loaders.datestamp import dated_filename
        name = dated_filename(name)

    for attempt in range(retries):
        try:
            # Check if file already exists in folder
            query = f"name='{name}' and '{folder_id}' in parents and trashed=false"
            results = service.files().list(
                q=query, fields="files(id)",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            existing = results.get("files", [])

            media = MediaFileUpload(str(file_path))

            if existing:
                # Update existing file
                service.files().update(
                    fileId=existing[0]["id"], media_body=media,
                    supportsAllDrives=True,
                ).execute()
                logger.info("Updated '%s' in Drive folder %s", name, folder_id)
            else:
                # Create new file
                metadata = {"name": name, "parents": [folder_id]}
                service.files().create(
                    body=metadata, media_body=media, fields="id",
                    supportsAllDrives=True,
                ).execute()
                logger.info("Uploaded '%s' to Drive folder %s", name, folder_id)
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed uploading '%s' to %s: %s — retrying in %ds",
                attempt + 1, name, folder_id, e, wait,
            )
            time.sleep(wait)
