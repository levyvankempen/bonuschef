"""Whether the portal can actually do its work.

The container's health probe used to ask Streamlit's `/_stcore/health`, which
answers for the server rather than the app it serves. docs/deployment.md
records it returning 200 with a `raise` in app.py - a probe that passes while
the service cannot do its job, which the deployment spec calls worse than no
probe at all.

This is deliberately narrow. It reports whether the page's own modules import
and whether the warehouse answers, which are the states a probe can settle
cheaply and honestly. A logic error part-way through a render is not among
them, and pretending otherwise would repeat the mistake.
"""

from __future__ import annotations


def ready() -> bool:
    """True when the portal's modules load and the warehouse answers."""
    try:
        # Importing the pages is most of "the deploy is not broken": a missing
        # dependency or a syntax error in any of them fails here.
        from bonuschef.portal import (  # noqa: F401
            clearance_page,
            recipes_page,
            tonight_page,
        )
        from bonuschef.portal.db import get_engine
        from sqlalchemy import text

        with get_engine().begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
