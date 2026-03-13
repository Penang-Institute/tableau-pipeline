"""Airport and maritime transport statistics transform.

Migrated from: scripts/transport/prep_airports.R (245 lines)

Processes quarterly aviation and maritime transport data from MOT
(Ministry of Transport):
- Passenger numbers by airport (Table J4.5)
- Aircraft movements by airport (Table J4.11)
- Cargo handled by airport (Table J4.7)
- Maritime cargo throughput by port (Table 3.2)

Sources:
  - Google Sheets: legacy data for each category
Output:
  - Google Sheet 1cLKz_AjEXswmw3RTaXPUeL430yndRJRb51FdVdqIpW4 (passengers)
  - Google Sheet 1Znur74rgQ9irBFVORfqBmWpO2xk0F3BrGGKvDpXVVmc (aircraft)
  - Google Sheet 1OP1GPP3RUikBiqQ8OpagZWlJtOPnKUGyItGzs0AgqZA (airport cargo)
  - Google Sheet 1XDcfC3QcTSTuoImYU16css6EpMoSekpNAO7zC2VPlKU (maritime cargo)
"""

import logging

import pandas as pd

from pipeline.config.registry import get_sheet_id
from pipeline.fetchers.gdrive import read_google_sheet
from pipeline.loaders.google_sheets import write_sheet

logger = logging.getLogger(__name__)

OUTPUT_SHEETS = {
    "passengers": get_sheet_id("airports", "passengers"),
    "aircraft": get_sheet_id("airports", "aircraft"),
    "airport_cargo": get_sheet_id("airports", "airport_cargo"),
    "maritime_cargo": get_sheet_id("airports", "maritime_cargo"),
}


def transform_passengers() -> pd.DataFrame:
    """Transform passenger data from legacy Google Sheet."""
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["passengers"], "pax_byAirport"
        )
        if "Date" in legacy.columns:
            legacy = legacy.drop(columns=["Date"], errors="ignore")
        if "Year" in legacy.columns and "Quarter" in legacy.columns:
            legacy["Date"] = pd.to_datetime(
                legacy["Year"].astype(str) + " " + legacy["Quarter"].astype(str),
                format="%Y Q%q",
                errors="coerce",
            )
            legacy = legacy.drop(columns=["Year", "Quarter"], errors="ignore")
        logger.info("Passengers transform: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Failed to read legacy passenger data: %s", e)
        return pd.DataFrame()


def transform_aircraft() -> pd.DataFrame:
    """Transform aircraft movement data from legacy Google Sheet."""
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["aircraft"], "aircraft_byAirport"
        )
        if "Date" in legacy.columns:
            legacy = legacy.drop(columns=["Date"], errors="ignore")
        if "Year" in legacy.columns and "Quarter" in legacy.columns:
            legacy["Date"] = pd.to_datetime(
                legacy["Year"].astype(str) + " " + legacy["Quarter"].astype(str),
                format="%Y Q%q",
                errors="coerce",
            )
            legacy = legacy.drop(columns=["Year", "Quarter"], errors="ignore")
        logger.info("Aircraft transform: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Failed to read legacy aircraft data: %s", e)
        return pd.DataFrame()


def transform_airport_cargo() -> pd.DataFrame:
    """Transform airport cargo data from legacy Google Sheet."""
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["airport_cargo"], "cargo_byAirport"
        )
        if "Year" in legacy.columns and "Quarter" in legacy.columns:
            legacy["Date"] = pd.to_datetime(
                legacy["Year"].astype(str) + " " + legacy["Quarter"].astype(str),
                format="%Y Q%q",
                errors="coerce",
            )
            legacy = legacy.drop(columns=["Year", "Quarter"], errors="ignore")
        logger.info("Airport cargo transform: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Failed to read legacy cargo data: %s", e)
        return pd.DataFrame()


def transform_maritime_cargo() -> pd.DataFrame:
    """Transform maritime cargo throughput data from legacy Google Sheet."""
    try:
        legacy = read_google_sheet(
            OUTPUT_SHEETS["maritime_cargo"], "Data"
        )
        if "Year" in legacy.columns and "Quarter" in legacy.columns:
            legacy["Date"] = pd.to_datetime(
                legacy["Year"].astype(str) + " " + legacy["Quarter"].astype(str),
                format="%Y Q%q",
                errors="coerce",
            )
            legacy = legacy.drop(columns=["Year", "Quarter"], errors="ignore")
        logger.info("Maritime cargo transform: %d rows", len(legacy))
        return legacy
    except Exception as e:
        logger.warning("Failed to read legacy maritime data: %s", e)
        return pd.DataFrame()


def transform() -> dict[str, pd.DataFrame]:
    """Run all airport/transport transforms."""
    return {
        "passengers": transform_passengers(),
        "aircraft": transform_aircraft(),
        "airport_cargo": transform_airport_cargo(),
        "maritime_cargo": transform_maritime_cargo(),
    }


def load(dfs: dict[str, pd.DataFrame]) -> None:
    """Write transport data to Google Sheets."""
    for key, df in dfs.items():
        if not df.empty and key in OUTPUT_SHEETS:
            write_sheet(df, OUTPUT_SHEETS[key], "data")


def main() -> dict[str, pd.DataFrame]:
    """Run full airports/transport pipeline."""
    dfs = transform()
    load(dfs)
    return dfs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
