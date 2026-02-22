"""BonusChef Portal — multipage Streamlit app."""

import streamlit as st

from bonuschef.portal.analysis_page import render_analysis
from bonuschef.portal.recipe_builder import render_add_recipe
from bonuschef.portal.recipes_page import render_recipes

st.set_page_config(
    page_title="BonusChef Portal",
    layout="wide",
    initial_sidebar_state="collapsed",
)

pg = st.navigation(
    [
        st.Page(render_recipes, title="Recipes"),
        st.Page(render_analysis, title="Analysis"),
        st.Page(render_add_recipe, title="Add Recipe"),
    ]
)
pg.run()
