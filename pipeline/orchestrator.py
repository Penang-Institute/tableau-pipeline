#!/usr/bin/env python3
"""Pipeline orchestrator — run individual or all transforms.

Usage:
    python -m pipeline.orchestrator                  # Run all transforms
    python -m pipeline.orchestrator cpi gdp          # Run specific transforms
    python -m pipeline.orchestrator --list            # List available transforms
    python -m pipeline.orchestrator --dry-run         # Show what would run
"""

import argparse
import importlib
import logging
import sys
import time

logger = logging.getLogger(__name__)

# Transform registry: name → module path
# Order matters — this defines the default execution order (DAG-like).
TRANSFORMS = {
    "copy_opendosm": "pipeline.transforms.copy_opendosm",
    "cpi": "pipeline.transforms.cpi",
    "cpi_national": "pipeline.transforms.cpi_national",
    "cpi_core": "pipeline.transforms.cpi_core",
    "ppi": "pipeline.transforms.ppi",
    "gdp_quarterly": "pipeline.transforms.gdp_quarterly",
    "utilisation": "pipeline.transforms.utilisation",
    "population": "pipeline.transforms.population",
    "hospitals": "pipeline.transforms.hospitals",
    # Phase 2 transforms
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


def run_transform(name: str, dry_run: bool = False) -> bool:
    """Run a single named transform. Returns True on success."""
    module_path = TRANSFORMS.get(name)
    if not module_path:
        logger.error("Unknown transform: %s", name)
        return False

    if dry_run:
        logger.info("[DRY RUN] Would run: %s (%s)", name, module_path)
        return True

    logger.info("=" * 60)
    logger.info("Running: %s", name)
    logger.info("=" * 60)

    start = time.time()
    try:
        module = importlib.import_module(module_path)
        module.main()
        elapsed = time.time() - start
        logger.info("Completed: %s (%.1fs)", name, elapsed)
        return True
    except Exception:
        elapsed = time.time() - start
        logger.exception("FAILED: %s (%.1fs)", name, elapsed)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run Penang Institute data pipeline transforms"
    )
    parser.add_argument(
        "transforms",
        nargs="*",
        help="Transform names to run (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available transforms and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without executing",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running remaining transforms if one fails",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.list:
        print("Available transforms:")
        for name, module_path in TRANSFORMS.items():
            print(f"  {name:20s} ({module_path})")
        return

    names = args.transforms or list(TRANSFORMS.keys())

    # Validate all names before running
    unknown = [n for n in names if n not in TRANSFORMS]
    if unknown:
        logger.error("Unknown transforms: %s", ", ".join(unknown))
        logger.info("Available: %s", ", ".join(TRANSFORMS.keys()))
        sys.exit(1)

    total_start = time.time()
    results = {}

    for name in names:
        ok = run_transform(name, dry_run=args.dry_run)
        results[name] = ok
        if not ok and not args.continue_on_error:
            logger.error("Stopping due to failure in '%s'. Use --continue-on-error to skip.", name)
            break

    # Summary
    total_elapsed = time.time() - total_start
    n_ok = sum(results.values())
    n_fail = len(results) - n_ok

    logger.info("=" * 60)
    logger.info("Pipeline complete: %d/%d succeeded (%.1fs total)", n_ok, len(results), total_elapsed)
    if n_fail:
        failed = [n for n, ok in results.items() if not ok]
        logger.error("Failed transforms: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
