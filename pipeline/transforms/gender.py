"""Gender / Women empowerment statistics transform.

Migrated from: scripts/gender/gender.R (285 lines)

Multi-topic script covering:
  1. Literacy rates (from local Excel)
  2. Federal decision-making statistics (from Google Drive Excel)

Sources:
  - Google Drive: 1-taYcByjP6ntuYOX1jwoOZ5Qjz5JWAt0 (parliament data)
  - Local: women_stats_education.xlsx, gdrive/women_stats_decision.making.xlsx
Output:
  - Google Sheet 1TRZEheoDgFm7eXck6-VjZjxd5OfhA_LEb0srYwYFhcs (women stats)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import pandas as pd

from pipeline.config.registry import get_drive_id, get_sheet_id
from pipeline.fetchers.gdrive import download_file_from_drive
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent

WOMEN_SHEET_ID = get_sheet_id("gender", "women_stats")
PARLIAMENT_DRIVE_ID = get_drive_id("gender", "parliament")


def transform_literacy() -> pd.DataFrame | None:
    """Transform literacy rate data from local women empowerment publication.

    Reads historical data from local women_stats_education.xlsx and applies
    age group dash normalization.
    """
    edu_path = DATA_DIR / "women_stats_education.xlsx"
    if not edu_path.exists():
        logger.info("No literacy data available (women_stats_education.xlsx not found) — skipping")
        return None

    try:
        result = pd.read_excel(edu_path, sheet_name="Literacy_rate")
    except Exception as e:
        logger.warning("Failed to read literacy historical data: %s", e)
        return None

    if result.empty:
        logger.info("No literacy data available — skipping")
        return None

    # Fix age group delimiters (R: str_replace(`Age group`, '[\u002D|\u2212]', "-"))
    if "Age group" in result.columns:
        result["Age group"] = result["Age group"].astype(str).str.replace(
            r"[\u002D\u2212]", "-", regex=True
        )

    logger.info("Literacy transform: %d rows", len(result))
    return result


def transform_decision_making() -> pd.DataFrame | None:
    """Transform federal decision-making (parliament) statistics."""
    try:
        tmp_path = download_file_from_drive(PARLIAMENT_DRIVE_ID)
        parliament = pd.read_excel(tmp_path, sheet_name="parliament")
        os.unlink(tmp_path)
    except Exception as e:
        logger.warning("Failed to download parliament data: %s", e)
        return None

    # Standardize position names
    def fix_position(pos):
        if pd.isna(pos):
            return pos
        pos = str(pos)
        if "Dewan Negara" in pos:
            return "Dewan Negara"
        if "Dewan Rakyat" in pos:
            return "Dewan Rakyat"
        if re.search(r"[CK]abinet", pos):
            return "Cabinet Minister"
        if re.search(r"(Timbalan)|(Deputy)", pos):
            return "Deputy Minister"
        return pos

    parliament["Position"] = parliament["Position"].apply(fix_position)

    # Standardize gender
    gender_map = {"Female": "Women", "Male": "Men"}
    if "Gender" in parliament.columns:
        parliament["Gender"] = parliament["Gender"].map(
            lambda x: gender_map.get(x, x)
        )

    logger.info("Decision-making transform: %d rows", len(parliament))
    return parliament


def transform() -> dict[str, pd.DataFrame | None]:
    """Run all gender transforms and return results (no side effects)."""
    return {
        "literacy": transform_literacy(),
        "decision_making": transform_decision_making(),
    }


def load(literacy: pd.DataFrame | None,
         decision_making: pd.DataFrame | None) -> None:
    """Write gender statistics to Google Sheets."""
    if literacy is not None and not literacy.empty:
        write_sheet(literacy, WOMEN_SHEET_ID, "Education")

    if decision_making is not None and not decision_making.empty:
        write_sheet(decision_making, WOMEN_SHEET_ID, "federalDM")


def main() -> dict[str, pd.DataFrame | None]:
    """Run full gender statistics pipeline."""
    results = transform()
    load(
        results["literacy"],
        results["decision_making"],
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
