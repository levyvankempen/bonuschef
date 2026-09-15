"""BonusChef — multipage Streamlit app."""

import streamlit as st

from bonuschef.portal.clearance_page import render_clearance
from bonuschef.portal.tonight_page import render_tonight
from bonuschef.portal.add_recipe_page import render_add_recipe
from bonuschef.portal.recipes_page import render_recipes

st.set_page_config(
    page_title="BonusChef",
    page_icon="🥬",
    # Centered, not wide: the app is used on a phone in a shop, and "wide" only
    # stretches content on the laptop.
    layout="centered",
)

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
