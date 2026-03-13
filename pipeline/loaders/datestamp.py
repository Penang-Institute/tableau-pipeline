"""Centralized date-stamp utility for output file paths."""

from __future__ import annotations

from datetime import date
from pathlib import Path


def dated_output_dir(base_dir: Path, run_date: date | None = None) -> Path:
    """Return base_dir / YYYY-MM-DD, creating it if needed."""
    d = run_date or date.today()
    out = base_dir / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    return out


def dated_filename(basename: str, run_date: date | None = None) -> str:
    """Insert date before extension: 'gdp_qtr.csv' → 'gdp_qtr_2026-03-11.csv'."""
    d = run_date or date.today()
    p = Path(basename)
    return f"{p.stem}_{d.isoformat()}{p.suffix}"
