"""One-time sync: upload only changed files from dry run to Google Drive.

Compares local file sizes against Drive and only uploads where they differ.
Skips files in the on-hold list.

Run:
    python sync_approved.py --dry-run   # preview what would be uploaded
    python sync_approved.py             # actually upload
"""

import logging
import os
from pathlib import Path

import pandas as pd

from pipeline.fetchers.opendosm import build_source_url, load_manifest
from pipeline.transforms.copy_opendosm import SKIP_FILES, _resolve_drive_folder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

LOCAL_DIR = Path("output/dry_run_2026-03-26")
CONFIG_DIR = Path(__file__).resolve().parent / "pipeline" / "config"


def get_drive_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(CONFIG_DIR / "service_account.json"),
    )
    creds = Credentials.from_service_account_file(
        creds_path, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def get_drive_file_size(service, shared_drive_id, folder_id, filename):
    """Get size of an existing file on Drive, or None if not found."""
    query = (
        f"name='{filename}' and '{folder_id}' in parents "
        f"and trashed=false"
    )
    resp = service.files().list(
        q=query,
        fields="files(id, name, size)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="drive",
        driveId=shared_drive_id,
    ).execute()
    files = resp.get("files", [])
    if files:
        return int(files[0].get("size", 0))
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no uploads")
    args = parser.parse_args()

    from pipeline.loaders.google_sheets import get_drive_folder_id, upload_to_drive

    manifest = load_manifest()
    manifest["source_url"] = manifest.apply(
        lambda r: build_source_url(r["source1"], r["source2"]), axis=1
    )
    manifest["local_path"] = manifest["source_url"].apply(
        lambda u: str(LOCAL_DIR / Path(u).name)
    )

    service = get_drive_service()
    shared_drive_id = get_drive_folder_id("raw_data_shared_drive")
    folder_cache: dict[str, str] = {}

    to_upload = []
    skipped_hold = []
    skipped_identical = []
    skipped_missing = []

    for _, row in manifest.iterrows():
        src = Path(row["local_path"])
        if not src.exists():
            skipped_missing.append(src.name)
            continue
        if src.name in SKIP_FILES:
            skipped_hold.append(src.name)
            continue

        dest_folder_path = row["destination"]
        folder_id = _resolve_drive_folder(
            service, shared_drive_id, dest_folder_path, folder_cache
        )

        local_size = src.stat().st_size
        drive_size = get_drive_file_size(service, shared_drive_id, folder_id, src.name)

        if drive_size is not None and drive_size == local_size:
            skipped_identical.append(src.name)
            continue

        to_upload.append((src, folder_id, dest_folder_path, local_size, drive_size))

    # Report
    print()
    print("=" * 60)
    print("SYNC SUMMARY" if not args.dry_run else "DRY RUN — NO UPLOADS")
    print("=" * 60)
    print(f"Total in manifest:    {len(manifest)}")
    print(f"On hold (skip):       {len(skipped_hold)}  {skipped_hold}")
    print(f"Identical (skip):     {len(skipped_identical)}")
    print(f"Not downloaded:       {len(skipped_missing)}")
    print(f"To upload (changed):  {len(to_upload)}")
    print()

    if to_upload:
        print("FILES TO UPLOAD:")
        for src, _, dest, local_sz, drive_sz in to_upload:
            drive_str = f"{drive_sz:,}B" if drive_sz is not None else "NEW"
            print(f"  {src.name:45s} {local_sz:>12,}B  (Drive: {drive_str})  -> {dest}")
        print()

    if args.dry_run:
        print("Dry run complete. Run without --dry-run to upload.")
        return

    # Upload
    uploaded = 0
    failed = 0
    for src, folder_id, dest, _, _ in to_upload:
        try:
            upload_to_drive(src, folder_id, file_name=src.name)
            logger.info("Uploaded %s -> %s", src.name, dest)
            uploaded += 1
        except Exception as e:
            logger.warning("Failed to upload %s: %s", src.name, e)
            failed += 1

    print()
    print(f"Done: {uploaded} uploaded, {failed} failed")


if __name__ == "__main__":
    main()
