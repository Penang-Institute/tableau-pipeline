"""Centralized access to Google Sheet IDs and Drive file/folder IDs.

All IDs are stored in google_sheets_registry.yaml. This module provides
typed helpers so transforms never need to hardcode IDs.

Usage:
    from pipeline.config.registry import get_sheet_id, get_drive_id

    sheet_id = get_sheet_id("labour", "principal")
    drive_id = get_drive_id("gross_income", "abs_poverty_05")
"""

import functools
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def _load_registry() -> dict:
    """Load and cache the sheets registry YAML."""
    with open(_CONFIG_DIR / "google_sheets_registry.yaml") as f:
        return yaml.safe_load(f)


def get_sheet_id(transform: str, key: str) -> str:
    """Look up a Google Sheet ID for a given transform and key.

    Args:
        transform: Transform name (e.g. "labour", "gender", "graduates").
        key: Sheet key within that transform (e.g. "principal", "output").

    Returns:
        The Google Sheet ID string.

    Raises:
        KeyError: If the transform or key is not found in the registry.
    """
    registry = _load_registry()
    try:
        return registry["transforms"][transform]["sheets"][key]
    except KeyError:
        available = list(registry.get("transforms", {}).keys())
        raise KeyError(
            f"Sheet ID not found: transforms.{transform}.sheets.{key}. "
            f"Available transforms: {available}"
        )


def get_drive_id(transform: str, key: str) -> str:
    """Look up a Google Drive file ID for a given transform and key.

    Args:
        transform: Transform name (e.g. "gross_income", "gdp_econ_activity").
        key: Drive file key within that transform (e.g. "abs_poverty_05").

    Returns:
        The Google Drive file ID string.

    Raises:
        KeyError: If the transform or key is not found in the registry.
    """
    registry = _load_registry()
    try:
        return registry["transforms"][transform]["drive_files"][key]
    except KeyError:
        available = list(registry.get("transforms", {}).keys())
        raise KeyError(
            f"Drive ID not found: transforms.{transform}.drive_files.{key}. "
            f"Available transforms: {available}"
        )


def get_drive_folder_id(key: str) -> str:
    """Look up a Google Drive folder ID from the top-level drive_folders section.

    Args:
        key: Folder key (e.g. "gdp_quarterly", "bed_utilisation").

    Returns:
        The Google Drive folder ID string.

    Raises:
        KeyError: If the key is not found.
    """
    registry = _load_registry()
    try:
        return registry["drive_folders"][key]
    except KeyError:
        available = list(registry.get("drive_folders", {}).keys())
        raise KeyError(
            f"Drive folder ID not found: drive_folders.{key}. "
            f"Available keys: {available}"
        )


def get_main_workbook_id() -> str:
    """Return the main dashboard workbook Google Sheet ID."""
    registry = _load_registry()
    return registry["main_workbook"]["id"]


def get_main_workbook_sheet(key: str) -> str:
    """Look up a sheet/tab name within the main dashboard workbook.

    Args:
        key: Sheet key (e.g. "cpi_by_state", "utilisation_opendosm").

    Returns:
        The sheet tab name string.
    """
    registry = _load_registry()
    return registry["main_workbook"]["sheets"][key]
