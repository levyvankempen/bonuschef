"""What counts as an offer right now, and what to do when clearance is stale.

Lifted out of the Vanavond page when the Recepten page needed the same
judgement. Two pages each deciding for themselves what "current" means is how
two surfaces come to disagree about one snapshot - the same reason
`freshness` was lifted out before it.
"""

from __future__ import annotations

import pandas as pd

from bonuschef.portal import freshness

# Every column derived from clearance, and its bonus-only twin.
#
# All of them, not the three that show up first. Swapping only the headline
# left the per-serving price, the "±" estimate shown for most of the pool, and
# every ingredient line still clearance-priced - directly beneath a banner
# saying clearance did not count. A reader multiplying servings by the
# per-serving price got a different number from the total above it.
_WITHDRAWN = {
    "saving_total": "saving_bonus_only",
    "cost_today": "cost_today_bonus_only",
    "partial_cost_today": "partial_cost_today_bonus_only",
    "cost_today_per_serving": "cost_today_per_serving_bonus_only",
}


def euro(value) -> str:
    """One formatter, so two pages cannot render a price differently."""
    return f"\u20ac{float(value):.2f}"


def snapshot_of(df: pd.DataFrame):
    """When the clearance behind these rows was captured."""
    if df.empty or "clearance_scraped_at" not in df:
        return None
    stamps = pd.to_datetime(df["clearance_scraped_at"], utc=True, errors="coerce")
    return None if stamps.isna().all() else stamps.max()


def withdraw_stale_clearance(df: pd.DataFrame, *, now=None) -> tuple[pd.DataFrame, str]:
    """Return the frame with clearance withdrawn if it is not from today.

    Withdraw rather than blank the page: the bonus evidence is national and
    week-scoped, so it has not aged out just because the store scan has, and
    at 09:00 you still want to know what to cook.

    The second element is the sentence to show, or "" when clearance counts.
    """
    if df.empty:
        return df, ""
    snapshot = snapshot_of(df)
    if freshness.is_current(snapshot, now or freshness.now()):
        return df, ""

    withdrawn = df.assign(
        **{column: df[twin] for column, twin in _WITHDRAWN.items() if twin in df},
        items_discounted_clearance=0,
        min_stock_remaining=None,
        earliest_expiry=pd.NaT,
    )
    withdrawn = withdrawn.assign(
        opportunity_rank=withdrawn["saving_total"]
        .where(withdrawn["saving_total"] > 0)
        .rank(ascending=False, method="min")
    )
    when = (
        freshness.format_local(snapshot) if snapshot is not None else "onbekend moment"
    )
    return withdrawn, (
        f"De winkelscan is van {when} en dus niet van vandaag. De laatste "
        "kans-koopjes tellen daarom even niet mee; hieronder staat alleen wat "
        "er in de bonus is."
    )
