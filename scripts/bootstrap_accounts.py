"""Turn a single-user bonuschef into an account-shaped one, without loss.

This runs once against a database that has been in use for months. The rows
in it were not written with an owner, because there was only ever one, and
this is where they get attributed.

What it does NOT touch, deliberately:

  Resolutions. public.ah_ingredient_products holds 4,161
  concept-to-product links over 1,903 ingredient concepts, each concept
  having cost a search against AH, and 86 of the links confirmed by hand. Those are facts about the catalogue - that
  "sjalot" is satisfied by AH Sjalotten is true for everybody - and scoping
  them to an account would hand every new person an unpriceable catalogue and
  ask them to redo work already done. The script prints that it skipped them,
  so nobody later wonders whether it was an oversight.

The token bundle is moved with its issue date intact. That timestamp measures
how long a credential value has survived, and it is the only evidence anyone
has about how AH expires refresh tokens from disuse - which has already
happened twice. Re-stamping it would destroy the series.

    uv run python scripts/bootstrap_accounts.py --username levy --dry-run
    uv run python scripts/bootstrap_accounts.py --username levy
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig
from bonuschef.portal.schema import _STATEMENTS, ensure_account_tables

# Adopted recipes, hand-entered recipes, and the verdicts that hide a recipe
# from the recommendations. All three were global; all three become the
# operator's.
_CLAIM_ADOPTED = """
INSERT INTO public.account_recipes (account_id, recipe_id, saved_at)
SELECT :account_id, recipe_id, COALESCE(adopted_at, now())
FROM public.ah_recipes
ON CONFLICT (account_id, recipe_id) DO NOTHING
"""

_CLAIM_MANUAL = """
INSERT INTO public.account_recipes (account_id, recipe_id, saved_at)
SELECT :account_id, recipe_id, now()
FROM public.recipes
ON CONFLICT (account_id, recipe_id) DO NOTHING
"""

_CLAIM_VERDICTS = """
UPDATE public.ah_recipe_verdicts
SET account_id = :account_id
WHERE account_id IS NULL
"""


def _unclaimed_verdicts(conn) -> int:
    """Verdicts not yet attributed to an account.

    Has to cope with the column not existing. Under --dry-run the migration
    has deliberately not run, so `WHERE account_id IS NULL` would fail against
    exactly the database the dry run exists to inspect - and it would fail
    with a column-does-not-exist error that reads like a bug rather than like
    "nothing has been migrated yet".
    """
    has_column = conn.execute(
        text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'ah_recipe_verdicts'
              AND column_name = 'account_id'
        """)
    ).scalar()
    if not has_column:
        return int(
            conn.execute(
                text("SELECT count(*) FROM public.ah_recipe_verdicts")
            ).scalar()
            or 0
        )
    return int(
        conn.execute(
            text(
                "SELECT count(*) FROM public.ah_recipe_verdicts "
                "WHERE account_id IS NULL"
            )
        ).scalar()
        or 0
    )


def _operator_account(conn, username: str, store_id: int) -> tuple[int, bool]:
    """Find or create the operator account. Returns (id, created)."""
    existing = conn.execute(
        text(
            "SELECT account_id FROM public.accounts WHERE lower(username) = lower(:u)"
        ),
        {"u": username},
    ).scalar()
    if existing is not None:
        return int(existing), False
    account_id = conn.execute(
        text("""
            INSERT INTO public.accounts (username, store_id, is_operator)
            VALUES (:u, :s, TRUE)
            RETURNING account_id
        """),
        {"u": username, "s": store_id},
    ).scalar()
    return int(account_id), True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="the operator's username")
    parser.add_argument(
        "--store-id",
        type=int,
        default=int(os.getenv("AH_STORE_ID", "1876")),
        help="seeded from AH_STORE_ID, so the existing markdown history stays "
        "attributed to this account",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_engine(DatabaseConfig.from_env().url)

    # Not under --dry-run. The statements are idempotent and additive, so
    # applying them early looked harmless, and it is not: a dry run that
    # alters the schema of the database it is inspecting is not a dry run,
    # and the whole reason to offer one is to look before touching anything.
    # Found by rehearsing this script against a clone of production.
    if args.dry_run:
        print(f"schema: {len(_STATEMENTS)} statement(s) would be applied")
    else:
        print(f"schema: {ensure_account_tables(engine)} statement(s) applied")

    with engine.begin() as conn:
        counts = {
            "adopted recipes": conn.execute(
                text("SELECT count(*) FROM public.ah_recipes")
            ).scalar(),
            "hand-entered recipes": conn.execute(
                text("SELECT count(*) FROM public.recipes")
            ).scalar(),
            "verdicts": _unclaimed_verdicts(conn),
            "resolutions (untouched)": conn.execute(
                text("SELECT count(*) FROM public.ah_ingredient_products")
            ).scalar(),
        }

        if args.dry_run:
            print(
                f"would create/reuse account {args.username!r} "
                f"with store {args.store_id}"
            )
            for label, n in counts.items():
                verb = "would leave" if "untouched" in label else "would claim"
                print(f"  {verb} {n} {label}")
            return 0

        account_id, created = _operator_account(conn, args.username, args.store_id)
        print(
            f"account {account_id} ({args.username}) "
            f"{'created' if created else 'already existed'}, store {args.store_id}"
        )
        for label, sql in (
            ("adopted recipes", _CLAIM_ADOPTED),
            ("hand-entered recipes", _CLAIM_MANUAL),
            ("verdicts", _CLAIM_VERDICTS),
        ):
            result = conn.execute(text(sql), {"account_id": account_id})
            print(f"  claimed {result.rowcount} {label}")
        print(
            f"  left {counts['resolutions (untouched)']} resolutions alone - "
            "they are the catalogue's, not an account's"
        )

    print(
        "\nNot done here: the Albert Heijn credential is still the shared token "
        "file.\nMoving it needs the encryption key, which is task 4.4."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
