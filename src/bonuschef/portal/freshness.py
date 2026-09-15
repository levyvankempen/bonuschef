"""How old the data is, and whether it still describes today.

Lifted out of ``clearance_page`` when a second page needed the same judgement.
Two pages each deciding for themselves what "current" means is how two surfaces
come to disagree about whether the same snapshot is usable.

The judgement is deliberately made at *read* time. ``CURRENT_DATE`` in a dbt
model is evaluated when the model is built, so a mart that filtered stale data
away would grow more confidently wrong the longer it went unbuilt. The mart
publishes the snapshot time; this module decides what it is worth now.
"""

from __future__ import annotations

from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd

LOCAL_TZ = ZoneInfo("Europe/Amsterdam")

# Mirrors the markdowns_refresh cron "0 11-20 * * *": before the first scrape of
# the day there is legitimately no data for today, which is a different fact
# from the pipeline being broken.
FIRST_SCRAPE_HOUR = 11


def now() -> pd.Timestamp:
    """Current instant in Dutch local time. Test seam: monkeypatched in tests."""
    return pd.Timestamp.now(tz=LOCAL_TZ)


def to_local(snapshot: pd.Timestamp | None) -> pd.Timestamp | None:
    """Normalise a timestamp to Amsterdam, treating NaT as absent."""
    if snapshot is None or pd.isna(snapshot):
        return None
    # pd.Timestamp() is typed as Timestamp | NaTType and the pd.isna guard above
    # does not narrow it for the checker. The cast records what the guard proves.
    return cast("pd.Timestamp", pd.Timestamp(snapshot)).tz_convert(LOCAL_TZ)


def is_current(snapshot: pd.Timestamp | None, at: pd.Timestamp) -> bool:
    """True when the snapshot falls on the current trading day in Amsterdam.

    Clock distance is the wrong measure: 19:00 yesterday is worthless at 09:00
    (14h later) while 09:00 today is still the best data available at 23:00
    (also 14h later). What matters is whether the store has restocked and
    re-marked since.

    Both sides are converted rather than assumed local. Comparing UTC dates
    would silently misclassify every snapshot between 22:00 and midnight local
    in summer, when the local date has already rolled over and the UTC one has
    not. A missing snapshot is never current.
    """
    local = to_local(snapshot)
    if local is None:
        return False
    return local.date() == at.tz_convert(LOCAL_TZ).date()


def describe_age(snapshot: pd.Timestamp, at: pd.Timestamp) -> str:
    """Coarse, glanceable age. Precision below the decision is noise."""
    hours = (at - snapshot).total_seconds() / 3600
    if hours < 1:
        return "minder dan een uur oud"
    if hours < 48:
        count = round(hours)
        return f"{count} uur oud"
    days = round(hours / 24)
    if days < 60:
        return "1 dag oud" if days == 1 else f"{days} dagen oud"
    return f"{round(days / 30)} maanden oud"


def format_local(snapshot: pd.Timestamp | None) -> str:
    """Timestamp for a caption, or a word when there is none."""
    local = to_local(snapshot)
    if local is None:
        return "een onbekend moment"
    return f"{local:%Y-%m-%d %H:%M}"


def before_first_scrape(at: pd.Timestamp) -> bool:
    """True early in the day, when today's absence of data is expected."""
    return at.tz_convert(LOCAL_TZ).hour < FIRST_SCRAPE_HOUR
