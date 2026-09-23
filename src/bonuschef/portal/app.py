"""BonusChef — multipage Streamlit app."""

import streamlit as st

from bonuschef.portal import gate
from bonuschef.portal.clearance_page import render_clearance
from bonuschef.portal.tonight_page import render_tonight
from bonuschef.portal.add_recipe_page import render_add_recipe
from bonuschef.portal.db import get_engine
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
        st.stop()

# Top navigation, not the sidebar. With initial_sidebar_state="collapsed" the
# four destinations had no affordance at all. Titles are Dutch throughout,
# matching the domain the data describes.
pg = st.navigation(
    [
        # First, and therefore the default destination: this is the question the
        # rest of the application exists to support.
        st.Page(render_tonight, title="Vanavond", icon=":material/local_dining:"),
        st.Page(render_clearance, title="Laatste kans", icon=":material/schedule:"),
        st.Page(render_recipes, title="Recepten", icon=":material/menu_book:"),
        st.Page(render_add_recipe, title="Toevoegen", icon=":material/add:"),
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
