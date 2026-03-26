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


def _resolve_drive_folder(
    service,
    shared_drive_id: str,
    folder_path: str,
    cache: dict[str, str],
) -> str:
    """Resolve a nested folder path within a shared drive, creating folders as needed.

    Walks the path segments (e.g. "3. Economy/CPI/DOSM/opendosm/") and returns
    the Google Drive folder ID of the leaf folder. Results are cached so
    repeated calls for the same destination avoid redundant API calls.

    Mirrors R's googledrive::drive_get(destination, shared_drive = ...).
    """
    folder_path = folder_path.strip().rstrip("/")
    if folder_path in cache:
        return cache[folder_path]

    parent_id = shared_drive_id
    segments = [s for s in folder_path.split("/") if s]

    # Walk each segment, caching intermediate paths
    for i, segment in enumerate(segments):
        partial = "/".join(segments[: i + 1])
        if partial in cache:
            parent_id = cache[partial]
            continue

        query = (
            f"name='{segment}' and '{parent_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="drive",
            driveId=shared_drive_id,
        ).execute()

        matches = results.get("files", [])
        if matches:
            parent_id = matches[0]["id"]
        else:
            # Create the missing folder
            metadata = {
                "name": segment,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            created = service.files().create(
                body=metadata,
                supportsAllDrives=True,
                fields="id",
            ).execute()
            parent_id = created["id"]
            logger.info("Created folder '%s' (id=%s)", partial, parent_id)

        cache[partial] = parent_id

    cache[folder_path] = parent_id
    return parent_id


def copy_to_gdrive(
    manifest: pd.DataFrame,
    skip_files: set[str] | None = None,
) -> None:
    """Upload downloaded files to Google Drive shared drive.

    Routes each file to the correct subfolder based on the 'destination'
    column in the manifest, mirroring the R behaviour of
    googledrive::drive_put(media, path = drive_get(destination)).

    Args:
        skip_files: Set of filenames to exclude from upload (e.g. on-hold files).
    """
    skip_files = skip_files or set()
    try:
        from googleapiclient.discovery import build
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

    # Cache resolved folder paths → IDs to avoid redundant API calls
    folder_cache: dict[str, str] = {}

    from pipeline.loaders.google_sheets import upload_to_drive

    for _, row in manifest[manifest["downloaded"]].iterrows():
        src = Path(row["local_path"])
        if not src.exists():
            continue
        if src.name in skip_files:
            logger.info("Skipping %s (on hold)", src.name)
            continue

        dest_folder_path = row["destination"]
        try:
            folder_id = _resolve_drive_folder(
                service, shared_drive_id, dest_folder_path, folder_cache
            )
            upload_to_drive(src, folder_id, file_name=src.name)
        except Exception as e:
            logger.warning("Failed to upload %s to '%s': %s", src.name, dest_folder_path, e)

    logger.info("Uploaded files to Google Drive shared drive")


def transform() -> dict[str, pd.DataFrame]:
    """Download all OpenDOSM files and return the manifest (no upload side effects).

    Returns dict with key 'manifest' containing the download results.
    """
    manifest = load_manifest()
    with tempfile.TemporaryDirectory(prefix="opendosm_") as tmp_dir:
        manifest = asyncio.run(download_all(manifest, Path(tmp_dir)))
    return {"manifest": manifest}


# Files on hold — do not overwrite on Drive until OpenDOSM publishes newer data.
SKIP_FILES: set[str] = {
    "lfs_qtr_state.csv",  # On hold: Drive has Q4 2025, OpenDOSM only Q3 2025
}


def main() -> pd.DataFrame:
    """Run the full copy_opendosm pipeline."""
    manifest = load_manifest()

    with tempfile.TemporaryDirectory(prefix="opendosm_") as tmp_dir:
        manifest = asyncio.run(download_all(manifest, Path(tmp_dir)))
        copy_to_gdrive(manifest, skip_files=SKIP_FILES)

    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
