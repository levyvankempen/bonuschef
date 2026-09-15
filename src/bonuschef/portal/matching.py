"""Proposing products for an ingredient concept.

Runs entirely against the local catalogue — no network — because it fires while
a person waits for an adoption to finish, and because AH's own product search
would spend the member credential that the scheduled pipelines depend on.

The ranking is deliberately crude. AH names generic products generically, so
"how few words does this product name add beyond the ingredient itself" sorts
"AH Courgette" above "AH Courgette spiraal" above "AH Courgettesoep 400ml" — the
last being a different food entirely. Crude is fine here: a wrong proposal costs
a correctable error, while demanding confirmation for every ingredient costs the
whole feature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text

# Beyond this the product name has drifted into being a different food:
# "courgette" vs "Bonduelle pasta pronto fusilli courgette broccoli".
_MAX_EXTRA_WORDS = 2
# More than this and we have matched a category, not an ingredient.
_MAX_HEAD_GROUP = 4
_CANDIDATE_LIMIT = 12


@dataclass(frozen=True)
class Candidate:
    product_link: str
    product_name: str
    price: float | None
    extra_words: int


def _query(schema: str) -> str:
    return f"""
        SELECT
            d.product_link,
            d.product_name,
            d.price,
            -- Words the product name adds beyond the ingredient itself.
            cardinality(string_to_array(
                trim(regexp_replace(lower(d.product_name),
                     '\\m' || :pattern || '\\M', ' ', 'g')), ' ')) AS extra_words
        FROM "{schema}"."dim_product" AS d
        WHERE lower(d.product_name) ~ ('\\m' || :pattern || '\\M')
        ORDER BY extra_words ASC, d.price ASC NULLS LAST
        LIMIT {_CANDIDATE_LIMIT}
    """


def candidates(
    engine, concept_name: str, schema: str = "public_marts"
) -> list[Candidate]:
    """Products whose name contains the ingredient as a whole word.

    Whole-word matching is what stops "room" matching "roomboter" and
    "slagroom" — a substring match on Dutch grocery names is unusable.
    """
    cleaned = (concept_name or "").strip().lower()
    if not cleaned:
        return []
    with engine.begin() as conn:
        rows = (
            conn.execute(text(_query(schema)), {"pattern": re.escape(cleaned)})
            .mappings()
            .all()
        )
    return [
        Candidate(
            product_link=r["product_link"],
            product_name=r["product_name"],
            price=r["price"],
            extra_words=int(r["extra_words"] or 0),
        )
        for r in rows
    ]


def accept(found: list[Candidate]) -> list[Candidate]:
    """Attach the whole head group, not a single winner.

    Which product is cheapest changes from day to day and the cheapest is the
    point of the project, so "AH Courgette" and "AH Biologisch Courgette" both
    attach and costing takes whichever is cheaper today. Picking one winner here
    would throw away the answer the whole thing exists to give.
    """
    if not found:
        return []
    fewest = min(c.extra_words for c in found)
    if fewest > _MAX_EXTRA_WORDS:
        # Only compound products matched, so this ingredient is not among them.
        return []
    head = [c for c in found if c.extra_words == fewest]
    return head if len(head) <= _MAX_HEAD_GROUP else []


def propose_for(
    engine, concepts: dict[int, str], schema: str = "public_marts"
) -> list[dict]:
    """Rows ready for ``db.propose_products`` — one per accepted product."""
    rows: list[dict] = []
    for concept_id, name in concepts.items():
        for candidate in accept(candidates(engine, name, schema=schema)):
            rows.append(
                {
                    "concept_id": concept_id,
                    "product_link": candidate.product_link,
                    "product_name": candidate.product_name,
                }
            )
    return rows
