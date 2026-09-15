"""Handmatig een recept invoeren — create new recipes and save to PostgreSQL."""

import re
from html import unescape
from urllib.request import Request, urlopen

import streamlit as st

from bonuschef.portal.rebuild import start_recipe_rebuild
from bonuschef.portal.db import (
    ensure_product_images_table,
    ensure_recipe_tables,
    existing_recipe_names,
    get_engine,
    insert_ingredients,
    insert_recipe,
    list_products,
    next_recipe_id,
    upsert_product_image,
)


_OG_IMAGE_RE = re.compile(
    r'<meta\s+property="og:image"\s+content="([^"]+)"', re.IGNORECASE
)


@st.cache_data(ttl=3600, show_spinner=False)
@st.cache_resource
def _ensure_tables(_engine) -> bool:
    """Create the portal-owned tables once per process, not once per rerun.

    dbt's on-run-start creates these too, but the portal can be opened on a
    fresh deployment before dbt has ever run. Calling them unconditionally ran
    three CREATE TABLE statements on every keystroke in the search box.
    """
    ensure_recipe_tables(_engine)
    ensure_product_images_table(_engine)
    return True


def _fetch_product_image(product_url: str) -> str | None:
    """Extract og:image URL from an AH product page (cached 1 hour)."""
    try:
        req = Request(product_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        matches = _OG_IMAGE_RE.findall(html)
        for url in matches:
            if "400x400" in url or "800x800" in url:
                return unescape(url)
        return unescape(matches[0]) if matches else None
    except Exception:
        return None


def _validate(engine, recipe_name: str, quantities: dict[str, int]) -> list[str]:
    errors: list[str] = []
    if not recipe_name or not recipe_name.strip():
        errors.append("Geef het recept een naam.")
    if not quantities:
        errors.append("Kies minstens één product.")
    if recipe_name and recipe_name.strip() in existing_recipe_names(engine):
        errors.append(f"Er bestaat al een recept met de naam '{recipe_name.strip()}'.")
    return errors


def _save_recipe(
    engine,
    recipe_name: str,
    servings: int,
    quantities: dict[str, int],
    link_by_name: dict[str, str],
    url_by_name: dict[str, str],
) -> int:
    recipe_id = next_recipe_id(engine)
    insert_recipe(engine, recipe_id, recipe_name, servings)
    insert_ingredients(
        engine,
        recipe_id,
        [(name, link_by_name[name], qty) for name, qty in quantities.items()],
    )
    for name in quantities:
        image_url = _fetch_product_image(url_by_name[name])
        if image_url:
            upsert_product_image(engine, link_by_name[name], image_url)
    return recipe_id


def render_manual_entry():
    st.title("Recept toevoegen")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    _ensure_tables(engine)

    try:
        products_df = list_products(engine)
    except Exception as e:
        st.error(f"De producten konden niet geladen worden: {e}")
        return

    if products_df.empty:
        st.warning("Er staan nog geen producten in de database.")
        return

    link_by_name: dict[str, str] = dict(
        zip(products_df["product_name"], products_df["product_link"])
    )
    image_by_name: dict[str, str | None] = dict(
        zip(products_df["product_name"], products_df["image_url"])
    )
    url_by_name: dict[str, str] = dict(
        zip(products_df["product_name"], products_df["product_url"])
    )
    price_by_name: dict[str, float] = dict(
        zip(products_df["product_name"], products_df["price"])
    )

    # Initialise selected ingredients in session state
    if "recipe_ingredients" not in st.session_state:
        st.session_state.recipe_ingredients = {}

    # --- Step 1: Search and add products ---
    st.markdown("**Stap 1: zoek producten en voeg ze toe**")
    search = st.text_input(
        "Zoek een product", placeholder="bijv. eieren, melk, kibbeling"
    )

    if search.strip():
        words = search.strip().split()
        patterns = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in words]
        matches = products_df[
            products_df["product_name"].apply(
                lambda n: all(p.search(n) for p in patterns)
            )
        ]

        if matches.empty:
            st.info(f"Geen producten gevonden voor '{search.strip()}'.")
        else:
            display = matches[["product_name", "product_url", "price"]].copy()
            display = display.rename(
                columns={
                    "product_name": "Product",
                    "product_url": "AH",
                    "price": "Prijs (€)",
                }
            )
            st.dataframe(
                display,
                hide_index=True,
                width="stretch",
                column_config={"AH": st.column_config.LinkColumn(display_text="link")},
            )

            available = [
                n
                for n in matches["product_name"]
                if n not in st.session_state.recipe_ingredients
            ]
            if available:
                to_add = st.multiselect(
                    "Kies producten om toe te voegen",
                    options=available,
                    key=f"add_{search.strip()}",
                )
                if st.button("Voeg toe aan recept") and to_add:
                    for name in to_add:
                        st.session_state.recipe_ingredients[name] = 1
                    st.rerun()
            else:
                st.info("Alle gevonden producten zitten al in het recept.")

    # --- Current ingredients ---
    if not st.session_state.recipe_ingredients:
        st.info("Zoek en voeg minstens één product toe om verder te gaan.")
        return

    st.markdown("---")
    st.markdown("**Gekozen ingrediënten**")

    to_remove: list[str] = []
    for name in list(st.session_state.recipe_ingredients):
        col_img, col_name, col_price, col_qty, col_rm = st.columns([1, 4, 1, 1, 0.5])
        with col_img:
            # From the warehouse, not from ah.nl at render time.
            img_url = image_by_name.get(name)
            if img_url:
                st.image(img_url, width=80)
        with col_name:
            st.markdown(f"[{name}]({url_by_name[name]})")
        with col_price:
            st.write(f"€{price_by_name[name]:.2f}")
        with col_qty:
            st.session_state.recipe_ingredients[name] = st.number_input(
                "Aantal",
                min_value=1,
                value=st.session_state.recipe_ingredients[name],
                step=1,
                key=f"qty_{name}",
                label_visibility="collapsed",
            )
        with col_rm:
            if st.button("✕", key=f"rm_{name}"):
                to_remove.append(name)

    if to_remove:
        for name in to_remove:
            del st.session_state.recipe_ingredients[name]
        st.rerun()

    # --- Step 2: Save recipe ---
    st.markdown("---")
    with st.form("recipe_form"):
        st.markdown("**Stap 2: receptgegevens**")
        recipe_name = st.text_input("Naam van het recept")
        servings = st.number_input("Personen", min_value=1, value=4, step=1)
        submitted = st.form_submit_button("Recept opslaan")

    if submitted:
        quantities = dict(st.session_state.recipe_ingredients)
        errors = _validate(engine, recipe_name, quantities)
        if errors:
            for err in errors:
                st.error(err)
        else:
            try:
                recipe_id = _save_recipe(
                    engine,
                    recipe_name.strip(),
                    int(servings),
                    quantities,
                    link_by_name,
                    url_by_name,
                )
                # The portal knows what has to happen; it should not ask the
                # user to open a terminal and type it.
                start_recipe_rebuild()
                st.success(f"**{recipe_name.strip()}** opgeslagen (nr. {recipe_id}).")
                st.caption("De prijs wordt op de achtergrond berekend.")
                st.session_state.recipe_ingredients = {}
            except Exception as e:
                st.error(f"Opslaan is mislukt: {e}")
