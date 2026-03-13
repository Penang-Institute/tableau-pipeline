"""Fetch files from Google Drive and read Google Sheets.

Many R scripts use googledrive::drive_download() and googlesheets4::read_sheet()
to fetch Excel files and read historical data from Sheets. This module provides
equivalent Python helpers using the service account credentials.
"""

import io
import logging
import os
import tempfile
import time
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Retry defaults for Google API calls
_DEFAULT_RETRIES = 3
_DEFAULT_BACKOFF_BASE = 2  # seconds

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _get_credentials():
    """Get Google service account credentials."""
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    return Credentials.from_service_account_file(creds_path, scopes=scopes)


def download_excel_from_drive(
    file_id: str, retries: int = _DEFAULT_RETRIES,
) -> pd.ExcelFile:
    """Download an Excel file from Google Drive by file ID.

    Returns an ExcelFile object that can be used with pd.read_excel().
    Equivalent to R's googledrive::drive_download().
    Retries with exponential backoff on transient failures.
    """
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)

    for attempt in range(retries):
        try:
            request = service.files().get_media(fileId=file_id)
            content = request.execute()
            logger.info("Downloaded file %s from Google Drive", file_id)
            return pd.ExcelFile(io.BytesIO(content))
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed downloading %s: %s — retrying in %ds",
                attempt + 1, file_id, e, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Failed to download {file_id} after {retries} retries")


def download_file_from_drive(
    file_id: str, suffix: str = ".xlsx", retries: int = _DEFAULT_RETRIES,
) -> Path:
    """Download a file from Google Drive to a temporary path.

    Returns the path to the temporary file.
    Retries with exponential backoff on transient failures.
    """
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("drive", "v3", credentials=creds)

    for attempt in range(retries):
        try:
            request = service.files().get_media(fileId=file_id)
            content = request.execute()

            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(content)
            tmp.close()

            logger.info("Downloaded file %s to %s", file_id, tmp.name)
            return Path(tmp.name)
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed downloading %s: %s — retrying in %ds",
                attempt + 1, file_id, e, wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Failed to download {file_id} after {retries} retries")


def read_google_sheet(
    spreadsheet_id: str,
    sheet_name: str,
    retries: int = _DEFAULT_RETRIES,
    **kwargs,
) -> pd.DataFrame:
    """Read a Google Sheet tab into a DataFrame.

    Equivalent to R's googlesheets4::read_sheet().
    Retries with exponential backoff on transient failures.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ]
    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(_CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)

    for attempt in range(retries):
        try:
            spreadsheet = gc.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            data = worksheet.get_all_records()

            df = pd.DataFrame(data)
            logger.info(
                "Read %d rows from sheet '%s' in %s",
                len(df), sheet_name, spreadsheet_id,
            )
            return df
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = _DEFAULT_BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Attempt %d failed reading sheet '%s' in %s: %s — retrying in %ds",
                attempt + 1, sheet_name, spreadsheet_id, e, wait,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"Failed to read sheet '{sheet_name}' in {spreadsheet_id} after {retries} retries"
    )
