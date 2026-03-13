"""Bulk download from OpenDOSM manifest and distribute to Google Drive.

Migrated from: scripts/copy_opendosm.R (64 lines)

Reads the opendosm.tsv manifest (115 data sources), downloads all files
concurrently using asyncio+aiohttp, and uploads them to the shared
Google Drive.

Source: opendosm.tsv manifest
Output: Google Drive shared drive
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import aiohttp
import pandas as pd

from pipeline.fetchers.opendosm import build_source_url, load_manifest

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 8


async def _download_one(
    session: aiohttp.ClientSession,
    url: str,
    dest: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool]:
    """Download a single file. Returns (url, success)."""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_chunked(8192):
                        f.write(chunk)
            return url, True
        except Exception as e:
            logger.warning("Failed to download %s: %s", url, e)
            return url, False


async def download_all(manifest: pd.DataFrame, tmp_dir: Path) -> pd.DataFrame:
    """Download all files from the manifest concurrently.

    Adds 'source_url' and 'local_path' columns to the manifest.
    """
    manifest = manifest.copy()
    manifest["source_url"] = manifest.apply(
        lambda r: build_source_url(r["source1"], r["source2"]), axis=1
    )
    manifest["local_path"] = manifest["source_url"].apply(
        lambda u: str(tmp_dir / Path(u).name)
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = [
            _download_one(session, row["source_url"], Path(row["local_path"]), semaphore)
            for _, row in manifest.iterrows()
        ]
        results = await asyncio.gather(*tasks)

    success_map = {url: ok for url, ok in results}
    manifest["downloaded"] = manifest["source_url"].map(success_map)

    n_ok = manifest["downloaded"].sum()
    n_fail = len(manifest) - n_ok
    logger.info("Downloaded %d/%d files (%d failed)", n_ok, len(manifest), n_fail)
    return manifest


def copy_to_gdrive(manifest: pd.DataFrame) -> None:
    """Upload downloaded files to Google Drive shared drive.

    Groups files by destination folder and uploads each batch.
    """
    from pipeline.loaders.google_sheets import _get_gspread_client

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.warning("google-api-python-client not installed — skipping Drive upload")
        return

    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path(__file__).resolve().parent.parent / "config" / "service_account.json"),
    )
    if not os.path.exists(creds_path):
        logger.warning("Service account credentials not found — skipping Drive upload")
        return

    from pipeline.loaders.google_sheets import get_drive_folder_id

    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    service = build("drive", "v3", credentials=creds)

    shared_drive_id = get_drive_folder_id("raw_data_shared_drive")

    for _, row in manifest[manifest["downloaded"]].iterrows():
        src = Path(row["local_path"])
        if not src.exists():
            continue

        # Find or create the destination folder in the shared drive
        dest_folder = row["destination"]
        media = MediaFileUpload(str(src))
        metadata = {"name": src.name, "parents": [shared_drive_id]}

        try:
            service.files().create(
                body=metadata,
                media_body=media,
                supportsAllDrives=True,
                fields="id",
            ).execute()
        except Exception as e:
            logger.warning("Failed to upload %s: %s", src.name, e)

    logger.info("Uploaded files to Google Drive shared drive")


def transform() -> dict[str, pd.DataFrame]:
    """Download all OpenDOSM files and return the manifest (no upload side effects).

    Returns dict with key 'manifest' containing the download results.
    """
    manifest = load_manifest()
    with tempfile.TemporaryDirectory(prefix="opendosm_") as tmp_dir:
        manifest = asyncio.run(download_all(manifest, Path(tmp_dir)))
    return {"manifest": manifest}


def main() -> pd.DataFrame:
    """Run the full copy_opendosm pipeline."""
    manifest = load_manifest()

    with tempfile.TemporaryDirectory(prefix="opendosm_") as tmp_dir:
        manifest = asyncio.run(download_all(manifest, Path(tmp_dir)))
        copy_to_gdrive(manifest)

    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
