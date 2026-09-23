"""BonusChef — multipage Streamlit app."""

import streamlit as st

from bonuschef.portal import gate
from bonuschef.portal.accounts import SINGLE_USER
from bonuschef.portal.clearance_page import render_clearance
from bonuschef.portal.tonight_page import render_tonight
from bonuschef.portal.add_recipe_page import render_add_recipe
from bonuschef.portal.db import get_engine
from bonuschef.portal.profile_page import render_profile
from bonuschef.portal.recipes_page import render_recipes
from bonuschef.version import describe, get_commit

st.set_page_config(
    page_title="BonusChef",
    page_icon="🥬",
    # Centered, not wide: the app is used on a phone in a shop, and "wide" only
    # stretches content on the laptop.
    layout="centered",
)

# The wall, above the navigation and ending in st.stop().
#
# This is what makes "a page cannot be added unguarded" structural rather than
# a convention somebody has to remember. pg.run() below is the only thing in
# the process that executes a page function, and it is unreachable when the
# script has already stopped. A fifth page added to the list inherits the
# guard by being in a list that is never reached.
#
# The wall is off unless BONUSCHEF_REQUIRE_SIGN_IN says otherwise. A
# deployment with no account would otherwise become unreachable the moment
# this shipped, and that is the one failure that cannot be fixed from inside
# the application.
# The flag is read before the engine is touched, so with the wall down this
# file behaves exactly as it did before the wall existed. Resolving the engine
# unconditionally made app.py require database configuration at startup for
# the first time - it used to be reached lazily, by whichever page needed it -
# which turned a missing variable into a blank application instead of a page
# that could say so.
if gate.sign_in_required():
    _engine = get_engine()
    _gate = gate.decide(
        _engine,
        gate.token_from_state(st.session_state) or gate.token_from_cookie(),
        required=True,
    )
    if not _gate.may_pass:
        gate.render_sign_in(_engine)
        st.caption(f":gray[BonusChef {describe()}]", help=f"commit {get_commit()[:12]}")
        gate.flush_cookie(st.session_state)
        st.stop()

    # Asserted on the attribute and assigned afterwards, so the narrowing
    # reaches the closure below. Assigning first and asserting on the local
    # leaves the variable declared as the union, and the lambda captures the
    # declaration rather than the narrowed value.
    assert _gate.account is not None  # may_pass with the wall up means an account
    _account = _gate.account

    # A person with no shop chosen is asked before anything else, and the ask
    # blocks. Clearance is scoped to a store, so the alternative is a page of
    # figures belonging to somebody else's shop with nothing to reveal it -
    # which is the failure the whole store-scoping exercise exists to close.
    #
    # Deliberately not a default. AH_STORE_ID still exists and would make a
    # serviceable one, and filling it in silently is precisely how one
    # person's prices become everybody's.
    if _account.store_id is None:
        render_profile(_account)
        st.caption(f":gray[BonusChef {describe()}]", help=f"commit {get_commit()[:12]}")
        gate.flush_cookie(st.session_state)
        st.stop()


# Top navigation, not the sidebar. With initial_sidebar_state="collapsed" the
# four destinations had no affordance at all. Titles are Dutch throughout,
# matching the domain the data describes.
def _signed_in():
    """The account the pages act for.

    SINGLE_USER when the wall is down, so a page takes the same shape either
    way rather than branching on whether accounts exist.
    """
    return _account if gate.sign_in_required() else SINGLE_USER


pg = st.navigation(
    [
        # First, and therefore the default destination: this is the question the
        # rest of the application exists to support.
        st.Page(
            lambda: render_tonight(_signed_in()),
            title="Vanavond",
            url_path="vanavond",
            icon=":material/local_dining:",
        ),
        st.Page(render_clearance, title="Laatste kans", icon=":material/schedule:"),
        st.Page(render_recipes, title="Recepten", icon=":material/menu_book:"),
        st.Page(render_add_recipe, title="Toevoegen", icon=":material/add:"),
        *(
            # Only with the wall up: without accounts there is no profile to
            # edit, and a tab that offers to change a password nobody has is
            # worse than no tab.
            [
                st.Page(
                    lambda: render_profile(_account),
                    title="Profiel",
                    url_path="profiel",
                    icon=":material/person:",
                )
            ]
            if gate.sign_in_required()
            else []
        ),
    ],
    position="top",
)
pg.run()

# The version, after the page, so it reads as a footnote rather than chrome
# competing with the answer. "Is the fix live?" is usually asked by the person
# looking at the page, not by an operator with a shell -- before this, they had
# no way to tell, because the deployment carried no provenance at all.
#
# The commit goes in the tooltip: it is what you need when the answer is "that
# is not the version I expected", and noise the rest of the time.
st.caption(
    f":gray[BonusChef {describe()}]",
    help=f"commit {get_commit()[:12]}",
)

# Any cookie write, last. The component has to render for the browser to be
# asked to store anything, and the sign-in path reruns immediately after
# succeeding - so writing it there tore the frame down before it could. This
# is the end of a run that reached a page, which means the frame survives.
gate.flush_cookie(st.session_state)
