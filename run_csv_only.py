#!/usr/bin/env python3
"""Run all transforms and save outputs as CSV files (no Google Sheets/Drive).

Usage:
    python run_csv_only.py                  # Run all transforms
    python run_csv_only.py cpi gdp_quarterly  # Run specific transforms
"""

import importlib
import logging
import sys
import time
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("csv_runner")

from pipeline.loaders.datestamp import dated_output_dir

_BASE_OUTPUT_DIR = Path(__file__).parent / "csv_output"

TRANSFORMS = {
    "cpi": "pipeline.transforms.cpi",
    "ppi": "pipeline.transforms.ppi",
    "gdp_quarterly": "pipeline.transforms.gdp_quarterly",
    "utilisation": "pipeline.transforms.utilisation",
    "population": "pipeline.transforms.population",
    "hospitals": "pipeline.transforms.hospitals",
    "inferred_population": "pipeline.transforms.inferred_population",
    "gdp_capita_states": "pipeline.transforms.gdp_capita_states",
    "gdp_econ_activity": "pipeline.transforms.gdp_econ_activity",
    "gender": "pipeline.transforms.gender",
    "graduates": "pipeline.transforms.graduates",
    "gross_income": "pipeline.transforms.gross_income",
    "labour": "pipeline.transforms.labour",
    "labour_demographics": "pipeline.transforms.labour_demographics",
    "demo_mukim": "pipeline.transforms.demo_mukim",
    "population_opendosm": "pipeline.transforms.population_opendosm",
    "population_ethnicity": "pipeline.transforms.population_ethnicity",
    "property": "pipeline.transforms.property",
    "trade_hs": "pipeline.transforms.trade_hs",
    "trade": "pipeline.transforms.trade",
    "airports": "pipeline.transforms.airports",
}

# copy_opendosm excluded — it downloads 115 files to a temp dir, not a table


def save_result(name: str, result) -> list[str]:
    """Save transform result(s) as CSV in a date-stamped subfolder."""
    output_dir = dated_output_dir(_BASE_OUTPUT_DIR)
    saved = []

    if isinstance(result, pd.DataFrame):
        path = output_dir / f"{name}.csv"
        result.to_csv(path, index=False)
        logger.info("  -> Saved %d rows to %s", len(result), path.name)
        saved.append(str(path))
    elif isinstance(result, dict):
        for key, df in result.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                path = output_dir / f"{name}_{key}.csv"
                df.to_csv(path, index=False)
                logger.info("  -> Saved %d rows to %s", len(df), path.name)
                saved.append(str(path))
    return saved


def run_one(name: str) -> bool:
    module_path = TRANSFORMS[name]
    logger.info("=" * 60)
    logger.info("Running: %s", name)
    start = time.time()
    try:
        mod = importlib.import_module(module_path)
        result = mod.transform()
        save_result(name, result)
        logger.info("  Done in %.1fs", time.time() - start)
        return True
    except Exception:
        logger.exception("  FAILED: %s (%.1fs)", name, time.time() - start)
        return False


def main():
    names = sys.argv[1:] if len(sys.argv) > 1 else list(TRANSFORMS.keys())

    unknown = [n for n in names if n not in TRANSFORMS]
    if unknown:
        logger.error("Unknown transforms: %s", ", ".join(unknown))
        logger.info("Available: %s", ", ".join(TRANSFORMS.keys()))
        sys.exit(1)

    total_start = time.time()
    results = {}
    for name in names:
        results[name] = run_one(name)

    # Summary
    elapsed = time.time() - total_start
    ok = sum(results.values())
    fail = len(results) - ok
    logger.info("=" * 60)
    logger.info("Done: %d/%d succeeded (%.1fs)", ok, len(results), elapsed)
    if fail:
        failed = [n for n, v in results.items() if not v]
        logger.error("Failed: %s", ", ".join(failed))

    logger.info("CSV files saved in: %s", dated_output_dir(_BASE_OUTPUT_DIR).resolve())


if __name__ == "__main__":
    main()
