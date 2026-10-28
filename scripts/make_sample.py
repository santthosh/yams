"""Regenerate the committed offline snapshot in data/sample/ from Yahoo Finance.

Usage: uv run python scripts/make_sample.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data import write_sample  # noqa: E402

if __name__ == "__main__":
    meta = write_sample()
    print(f"Sample written: as_of={meta['as_of']} tickers={meta['ticker_count']} missing={len(meta['missing'])}")
