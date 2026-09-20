"""Create the tables dbt reads but does not create, so the SQL can be executed.

Two sources of DDL, deliberately:

- the portal's own `ensure_catalogue_tables`, called rather than copied,
  because two statements of one schema is how they come to disagree;
- `tests/fixtures/warehouse_sources.sql` for the tables dlt creates at load
  time from the shape of what it loaded, which cannot be called into
  existence without a load.

Empty tables are the point. Building in CI executes the SQL; a statement runs
against an empty table exactly as well, and it is an empty database that
catches a rendered-to-nonsense expression.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from bonuschef.portal.db import ensure_catalogue_tables, ensure_verdict_table  # noqa: E402

FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "warehouse_sources.sql"
)


def main() -> int:
    url = (
        f"postgresql+psycopg2://{os.getenv('PG_USER', 'postgres')}:"
        f"{os.getenv('PG_PASSWORD', 'postgres')}@"
        f"{os.getenv('PG_HOST', 'localhost')}:{os.getenv('PG_PORT', '5432')}/"
        f"{os.getenv('PG_DB', 'postgres')}"
    )
    engine = create_engine(url)

    ensure_catalogue_tables(engine)
    ensure_verdict_table(engine)

    with engine.begin() as conn:
        # Strip comments BEFORE splitting on ";". A semicolon inside a
        # comment - "one clearance unit; the recipe claimed it twice" - would
        # otherwise split a statement in half and send the remainder to the
        # database as SQL.
        sql = "\n".join(
            line
            for line in FIXTURE.read_text().splitlines()
            if line.strip() and not line.strip().startswith("--")
        )
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    print("warehouse sources ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
