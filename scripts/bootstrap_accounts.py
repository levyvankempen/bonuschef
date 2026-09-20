"""Turn a single-user bonuschef into an account-shaped one, without loss.

This runs once against a database that has been in use for months. The rows
in it were not written with an owner, because there was only ever one, and
this is where they get attributed.

What it does NOT touch, deliberately:

  Resolutions. public.ah_ingredient_products holds roughly 1,900
  concept-to-product links, each of which cost a search against AH, and 86 of
  them were confirmed by hand. Those are facts about the catalogue - that
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
from bonuschef.portal.schema import ensure_account_tables

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
    applied = ensure_account_tables(engine)
    print(f"schema: {applied} statement(s) applied")

    with engine.begin() as conn:
        counts = {
            "adopted recipes": conn.execute(
                text("SELECT count(*) FROM public.ah_recipes")
            ).scalar(),
            "hand-entered recipes": conn.execute(
                text("SELECT count(*) FROM public.recipes")
            ).scalar(),
            "verdicts": conn.execute(
                text(
                    "SELECT count(*) FROM public.ah_recipe_verdicts "
                    "WHERE account_id IS NULL"
                )
            ).scalar(),
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
