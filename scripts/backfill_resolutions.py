"""Re-derive every ingredient's products in one pass, now.

The nightly asset caps itself at 300 retailer lookups so that it drains over
several nights and clearance - which cannot be backfilled - keeps its
priority. That is right for a job nobody is watching, and wrong when the
question is "the matching improved, apply it to everything".

This is the deliberate version: one operator, one sitting, the same logic the
asset uses, no cap beyond a safety stop.

    python scripts/backfill_resolutions.py            # the whole catalogue
    python scripts/backfill_resolutions.py --dry-run  # say what would change
    python scripts/backfill_resolutions.py --limit 50

Safe to interrupt and safe to re-run. Each concept is replaced in its own
transaction, and re-deriving a concept stamps it as freshly proposed, which
moves it to the back of the queue - so a second run continues where the first
stopped rather than starting over.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bonuschef.dags.defs.assets.resolution import (  # noqa: E402
    _candidates_for,
    _webshop_id_to_product,
)
from bonuschef.portal.db import (  # noqa: E402
    get_engine,
    read_stale_concepts,
    replace_proposals,
)
from bonuschef.utils.ah_recipes import AHRecipeUnavailable  # noqa: E402

# A stop, not a budget. At 0.25s between calls the whole catalogue is about
# 25 minutes; this exists so a bug cannot turn "apply the improvement" into
# an unbounded spend against someone else's API.
SAFETY_STOP = 6000

# A read timeout against api.ah.nl is ordinary over a run this long - one
# happened 8 concepts into the first trial. Stopping on the first would make
# the whole backfill a coin flip, so transient failures are tolerated the way
# the nightly asset tolerates them, and only a run of them means the retailer
# is actually gone.
MAX_CONSECUTIVE_FAILURES = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="concepts, 0 = all")
    parser.add_argument("--batch", type=int, default=100)
    args = parser.parse_args()

    engine = get_engine()
    crosswalk = _webshop_id_to_product(engine)
    print(f"catalogue: {len(crosswalk)} priceable products")

    started = time.monotonic()
    spent = examined = replaced = unchanged = empty = failures = 0
    consecutive = 0
    stopped_because = ""
    seen: set[int] = set()

    while spent < SAFETY_STOP and not stopped_because:
        batch = read_stale_concepts(engine, limit=args.batch)
        # read_stale_concepts orders by least-recently-proposed, and replacing
        # a concept stamps it as fresh - so the queue advances on its own.
        # Under --dry-run nothing is stamped, so track what we have seen or it
        # would return the same batch forever.
        batch = [row for row in batch if row["concept_id"] not in seen]
        if not batch:
            break
        if args.limit and examined >= args.limit:
            break

        for row in batch:
            if spent >= SAFETY_STOP or (args.limit and examined >= args.limit):
                break
            if stopped_because:
                break
            seen.add(row["concept_id"])
            examined += 1
            name = row["concept_name"]
            try:
                proposals, cost, _rejected = _candidates_for(name, crosswalk)
            except AHRecipeUnavailable as exc:
                failures += 1
                consecutive += 1
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    stopped_because = f"retailer unreachable ({str(exc)[:80]})"
                    break
                # Back off and carry on. The concept is not marked seen, so a
                # later batch will offer it again.
                seen.discard(row["concept_id"])
                examined -= 1
                time.sleep(2 * consecutive)
                continue
            consecutive = 0
            spent += cost

            if not proposals:
                empty += 1
                continue
            titles = [p["product_name"] for p in proposals]
            if args.dry_run:
                print(f"  {name[:34]:34} -> {', '.join(t[:26] for t in titles[:3])}")
                unchanged += 1
                continue
            for proposal in proposals:
                proposal["concept_id"] = row["concept_id"]
            replace_proposals(engine, row["concept_id"], proposals)
            replaced += 1

            if replaced and replaced % 50 == 0:
                mins = (time.monotonic() - started) / 60
                print(
                    f"  {replaced} re-derived, {examined} examined, "
                    f"{spent} lookups, {mins:.1f} min"
                )

    mins = (time.monotonic() - started) / 60
    print(
        f"\nexamined {examined} concept(s) in {mins:.1f} min: "
        f"{replaced} re-derived, {empty} left alone (nothing priceable found)"
        + (f", {unchanged} would change (dry run)" if args.dry_run else "")
    )
    if failures:
        print(f"{failures} lookup(s) failed transiently and were retried later")
    if stopped_because:
        # Distinguishing these matters: one means "run it again", the other
        # means "something is wrong". Reporting the safety stop for a network
        # timeout, as the first version did, sends the operator the wrong way.
        print(f"stopped early: {stopped_because}")
    elif spent >= SAFETY_STOP:
        print("stopped at the safety limit; run again to continue")
    else:
        print("nothing left to re-derive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
