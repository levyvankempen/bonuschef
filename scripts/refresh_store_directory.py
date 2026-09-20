"""Fetch the Albert Heijn store directory into the database.

Run when the list needs establishing or refreshing. Shops open and close on a
scale of years, so this is not on a schedule - putting it on one would spend
a daily request re-learning something that changed about never.

    uv run python scripts/refresh_store_directory.py --dry-run
    uv run python scripts/refresh_store_directory.py
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine

from bonuschef.config import DatabaseConfig
from bonuschef.portal.db import replace_store_directory
from bonuschef.portal.schema import ensure_account_tables
from bonuschef.utils.ah_stores import fetch_stores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stores = fetch_stores()
    print(f"fetched {len(stores)} stores")
    for store in stores[:3]:
        print(f"  {store.store_id:>5}  {store.label()}")
    if len(stores) > 3:
        print(f"  ... and {len(stores) - 3} more")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    engine = create_engine(DatabaseConfig.from_env().url)
    ensure_account_tables(engine)
    written = replace_store_directory(engine, stores)
    print(f"wrote {written} stores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
