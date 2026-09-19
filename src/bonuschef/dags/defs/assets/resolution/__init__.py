"""Propose products for the pool's unresolved ingredient concepts.

The pool is useless without this. Fetching 900 recipes is cheap and fast; what
makes them *rankable* is knowing which product an ingredient can be bought as,
and until that exists a 900-recipe pool prices 3.3% of its ingredients and ranks
nothing at all.

The matcher runs entirely against the local catalogue - no network, no AH
credential - so this costs nothing but CPU and can be re-run freely.

**These are proposals, not confirmations.** ``propose_products`` writes with
``confirmed_at`` NULL and refuses to overwrite anything a person has decided, so
re-running after a catalogue refresh can never revert a correction. The portal's
review queue is where a proposal becomes a decision; this job only ensures there
is something to review, ordered by how much difference it makes.
"""

import re
from dagster import AssetExecutionContext, AssetKey, RetryPolicy, asset
from sqlalchemy import text

from bonuschef.portal.db import get_engine, propose_products
from bonuschef.portal.matching import propose_for
from bonuschef.utils.ah_auth import AHAuthError
from bonuschef.portal.classification import cohort, judge
from bonuschef.utils.ah_recipes import DEPARTMENT_NON_FOOD
from bonuschef.portal.db import read_linked_products, withdraw_proposals
from bonuschef.utils.ah_recipes import fetch_product_taxonomy  # noqa: F401
from bonuschef.utils.ah_recipes import AHRecipeUnavailable, search_products

# What one run may spend on AH. The first pass over a fresh pool has ~1,400
# concepts to ask about, which at this cap drains over five nightly runs rather
# than in one burst - and clearance, which is unbackfillable, keeps its priority.
# Concepts are taken most-used first, so the budget always buys the most.
MAX_AH_LOOKUPS_PER_RUN = 300

# A read timeout is not a rejection. The first live run gave up its whole budget
# after 101 lookups because one request timed out - and the same pace ran 40 for
# 40 minutes later, so it was a blip, not throttling. Tolerate a few in a row;
# only a credential rejection aborts immediately, because that is the failure
# where retrying does damage.
MAX_CONSECUTIVE_TRANSPORT_FAILURES = 3

# Most-used concepts first. Concept frequency is steep - a few hundred cover
# most ingredient lines - so if this is ever interrupted, the work that has
# landed is the work that mattered.
_UNRESOLVED_CONCEPTS = """
    SELECT i.concept_id, MIN(i.concept_name) AS concept_name, COUNT(*) AS uses
    FROM public."ah__pool_recipe_ingredients" AS i
    LEFT JOIN public.ah_ingredient_products AS p
        ON i.concept_id = p.concept_id
    WHERE p.concept_id IS NULL
    GROUP BY i.concept_id
    ORDER BY uses DESC, i.concept_id ASC
"""


@asset(
    name="ah__ingredient_proposals",
    # Not group_name="dlt": that group is excluded from the nightly rebuild
    # because those assets spend the AH credential. This one spends nothing and
    # should run whenever the catalogue moves, since a product that appeared
    # today may resolve an ingredient that failed to match yesterday.
    group_name="resolution",
    retry_policy=RetryPolicy(max_retries=1, delay=30),
    # dim_product keys as a path because dbt models are grouped by folder.
    deps=[AssetKey("ah__recipe_pool"), AssetKey(["marts", "dim_product"])],
)
def ah__ingredient_proposals_asset(context: AssetExecutionContext) -> None:
    """Match unresolved pool concepts against the product catalogue."""
    engine = get_engine()

    with engine.begin() as conn:
        rows = conn.execute(text(_UNRESOLVED_CONCEPTS)).mappings().all()
    concepts = {int(r["concept_id"]): r["concept_name"] for r in rows}
    if not concepts:
        context.log.info("Every pool concept already has a product; nothing to do.")
        context.add_output_metadata({"unresolved": 0, "proposed": 0})
        return

    context.log.info("Matching %d unresolved concepts", len(concepts))

    # The local matcher first: it is free, and its whole-word rule makes it the
    # conservative one. Whatever it settles never costs an AH request.
    proposals = propose_for(engine, concepts)
    propose_products(engine, proposals)
    local_resolved = {p["concept_id"] for p in proposals}
    context.log.info(
        "Local matcher settled %d of %d concepts", len(local_resolved), len(concepts)
    )

    # Then AH's own search, for what the local rule could not reach. This is the
    # mechanism behind "Kies producten" on an Allerhande page, and it resolves
    # phrasings no name match can: "verse platte peterselie", "eetrijpe
    # avocado". It is also wrong about one time in five, and confidently so, so
    # everything it returns is a proposal for the review queue rather than an
    # answer.
    remaining = [cid for cid in concepts if cid not in local_resolved]
    ah_proposals, spent, unreachable = _propose_from_ah(
        engine, {cid: concepts[cid] for cid in remaining}, context
    )
    propose_products(engine, ah_proposals)

    # Re-judge what is already linked. Filtering only new proposals would fix
    # nothing: a concept with any row at all never re-enters the query above,
    # so every wrong answer already recorded would stay recorded.
    recheck = recheck_existing_links(engine, context)

    resolved = len(local_resolved | {p["concept_id"] for p in ah_proposals})
    context.log.info(
        "Proposed %d products across %d of %d concepts (%d AH lookups)",
        len(proposals) + len(ah_proposals),
        resolved,
        len(concepts),
        spent,
    )
    context.add_output_metadata(
        {
            "unresolved_before": len(concepts),
            "concepts_matched": resolved,
            "matched_locally": len(local_resolved),
            "matched_via_ah_search": resolved - len(local_resolved),
            "products_proposed": len(proposals) + len(ah_proposals),
            "ah_lookups_spent": spent,
            # Concepts the budget did not reach this run. Non-zero means the
            # queue is still draining, not that anything failed.
            "deferred_to_next_run": max(0, len(remaining) - spent),
            "ah_unreachable": unreachable,
            # The ones a person still has to decide. This is the review queue,
            # and it is the honest measure of how far off a full answer is.
            "still_unmatched": len(concepts) - resolved,
            "existing_links_checked": recheck.get("checked", 0),
            "contradicting_links_withdrawn": recheck.get("withdrawn", 0),
            # Concepts whose only products contradict them. Withdrawing those
            # would leave the concept with nothing, so they are reported here
            # for a person instead.
            "concepts_left_with_only_wrong_products": recheck.get("flagged", 0),
        }
    )


def _propose_from_ah(
    engine, concepts: dict[int, str], context: AssetExecutionContext
) -> tuple[list[dict], int, bool]:
    """Ask AH for the concepts the local matcher could not settle.

    Returns the proposals, how many lookups were spent, and whether AH became
    unreachable. Stops on the first failure that survives the auth layer's own
    retry rather than working through 1,400 rejections: the credential is the
    scarce thing, and a partial pass is not a failure - the next run continues
    from where this one stopped, because a concept with a proposal is no longer
    in the query that drives this.
    """
    if not concepts:
        return [], 0, False

    crosswalk = _webshop_id_to_product(engine)
    proposals: list[dict] = []
    spent = 0
    rejected = 0
    narrowed = 0
    consecutive_failures = 0
    for concept_id, name in list(concepts.items())[:MAX_AH_LOOKUPS_PER_RUN]:
        try:
            hits = search_products(name)
        except AHRecipeUnavailable as exc:
            if isinstance(exc.__cause__, AHAuthError):
                # The credential, not the connection. Stop at once: retrying
                # through the auth fallback chain is how a refresh token dies.
                context.log.warning(
                    "AH rejected the credential after %d lookups: %s. "
                    "%d concepts deferred.",
                    spent,
                    exc,
                    len(concepts) - spent,
                )
                return proposals, spent, True
            consecutive_failures += 1
            context.log.warning(
                "AH lookup %d failed (%d in a row): %s",
                spent + 1,
                consecutive_failures,
                str(exc)[:120],
            )
            if consecutive_failures >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
                context.log.warning(
                    "Giving up after %d consecutive failures; %d concepts "
                    "deferred to the next run.",
                    consecutive_failures,
                    len(concepts) - spent,
                )
                return proposals, spent, True
            continue
        consecutive_failures = 0
        spent += 1
        # AH's relevance is good but not about *kind*: it returns Verstegen
        # Dille, a jar of dried dill, for "verse dille". Its own classification
        # says so, and rank() then puts a candidate the taxonomy actually names
        # ahead of one that merely mentions the ingredient in its title.
        # Reject on kind first, then keep only the candidates that are the
        # same kind as the best one. Proposing all of a search's hits is what
        # lets a wrong one poison a cost: downstream the cheapest candidate
        # wins, so a Boursin among the shallots can decide a recipe's price.
        acceptable = []
        for hit in hits:
            verdict = judge(name, hit.department)
            if not verdict.accepted:
                rejected += 1
                context.log.debug(
                    "rejected %s for %r: %s", hit.title, name, verdict.reason
                )
                continue
            acceptable.append(hit)

        chosen = cohort(name, acceptable)
        narrowed += len(acceptable) - len(chosen)
        for hit in chosen:
            known = crosswalk.get(hit.webshop_id)
            if known is None:
                # AH sells it; we have never seen a price for it. Proposing it
                # would put an unpriceable product in front of a person as an
                # answer.
                continue
            proposals.append(
                {
                    "concept_id": concept_id,
                    "product_link": known[0],
                    "product_name": known[1],
                }
            )
    if narrowed:
        context.log.info(
            "%d candidate(s) dropped as a different kind of thing from the "
            "best match for their ingredient",
            narrowed,
        )
    if rejected:
        context.log.info(
            "%d candidate(s) rejected because their classification "
            "contradicted the ingredient",
            rejected,
        )
    return proposals, spent, False


def _webshop_id_to_product(engine) -> dict[int, tuple[str, str]]:
    """AH's product id is the key our own catalogue is derived from.

    searchProducts returns 4164 for courgette; our product_link is
    wi4164/ah-courgette. That shared id is what makes AH's answers joinable at
    all - without it there would only be a title to fuzzy-match, which is the
    problem this exists to escape.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT webshop_id, product_link, product_name "
                "FROM public.int_product_crosswalk WHERE webshop_id IS NOT NULL"
            )
        ).all()
    return {int(r[0]): (r[1], r[2]) for r in rows}


def recheck_existing_links(engine, context: AssetExecutionContext) -> dict:
    """Re-judge links already in the database against what the products are.

    A filter applied only to new proposals fixes nothing, because the wrong
    answers are already recorded: "mierikswortel in pot" resolves to pesto,
    salsa and peanut butter today, and nothing revisits a concept once it has
    any row at all.

    Two guards, both load-bearing:

    - a confirmed row is never touched, because a person decided it;
    - a contradicting proposal is withdrawn only if the concept keeps another
      acceptable one. Removing the last candidate turns a visibly wrong price
      into a silently missing one, and silence is the worse failure - a wrong
      product on the page can be seen and corrected, an absent one cannot.

    Returns counts; the concepts it could not fix are reported for review
    rather than being quietly emptied.
    """
    links = read_linked_products(engine)
    if not links:
        return {"checked": 0, "withdrawn": 0, "flagged": 0}

    webshop_ids = sorted(
        {
            wid
            for link in links
            if (wid := _webshop_id(link["product_link"])) is not None
        }
    )
    try:
        classified = fetch_product_taxonomy(webshop_ids)
    except AHRecipeUnavailable as exc:
        context.log.warning("Could not classify products: %s", str(exc)[:160])
        return {"checked": 0, "withdrawn": 0, "flagged": 0, "unreachable": True}

    by_concept: dict[int, list[dict]] = {}
    for link in links:
        by_concept.setdefault(int(link["concept_id"]), []).append(link)

    withdraw: list[tuple[int, str]] = []
    flagged: list[str] = []
    for concept_id, rows in by_concept.items():
        name = rows[0]["concept_name"]
        contradicting, acceptable = [], []
        for row in rows:
            wid = _webshop_id(row["product_link"])
            hit = classified.get(wid) if wid is not None else None
            if hit is None:
                # Unknown is not wrong. A delisted product still counts as a
                # candidate here rather than being withdrawn on no evidence.
                acceptable.append(row)
            elif row["confirmed"] or judge(name, hit.department).accepted:
                acceptable.append(row)
            else:
                contradicting.append((row, hit.department))

        if not contradicting:
            continue

        # A non-food product can never be right, so it goes whether or not the
        # concept keeps anything. Leaving "wortel" resolved to a paper napkin
        # because the napkin is its only candidate would price a recipe off a
        # napkin; an ingredient with nothing is already required to be visible
        # rather than silent, so the gap is the better outcome.
        never_right = [r for r, d in contradicting if d == DEPARTMENT_NON_FOOD]
        wrong_form = [r for r, d in contradicting if d != DEPARTMENT_NON_FOOD]

        withdraw.extend((concept_id, r["product_link"]) for r in never_right)

        # A form mismatch is a worse match, not an impossible one - dried
        # tarragon will do if fresh is all the recipe asked to avoid. Withdraw
        # it only when something better survives.
        if wrong_form and acceptable:
            withdraw.extend((concept_id, r["product_link"]) for r in wrong_form)
        elif wrong_form:
            flagged.append(f"{name} ({len(wrong_form)})")

    removed = withdraw_proposals(engine, withdraw)
    if flagged:
        context.log.warning(
            "%d concept(s) have only contradicting products and were left "
            "alone rather than emptied: %s",
            len(flagged),
            ", ".join(flagged[:10]),
        )
    return {"checked": len(links), "withdrawn": removed, "flagged": len(flagged)}


def _webshop_id(product_link: str) -> int | None:
    match = re.match(r"wi(\d+)/", product_link or "")
    return int(match.group(1)) if match else None
