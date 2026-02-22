"""Add Recipe page — create new recipes and save to PostgreSQL."""

import re
from html import unescape
from urllib.request import Request, urlopen

import streamlit as st

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
        errors.append("Recipe name cannot be empty.")
    if not quantities:
        errors.append("Select at least one product.")
    if recipe_name and recipe_name.strip() in existing_recipe_names(engine):
        errors.append(f"A recipe named '{recipe_name.strip()}' already exists.")
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


def render_add_recipe():
    st.title("Add Recipe")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    ensure_recipe_tables(engine)
    ensure_product_images_table(engine)

    try:
        products_df = list_products(engine)
    except Exception as e:
        st.error(f"Could not load products: {e}")
        return

    if products_df.empty:
        st.warning("No products found in the database.")
        return

    link_by_name: dict[str, str] = dict(
        zip(products_df["product_name"], products_df["product_link"])
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
    st.markdown("**Step 1: Search and add products**")
    search = st.text_input(
        "Search for a product", placeholder="e.g. eieren, melk, kibbeling"
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
            st.info(f"No products match '{search.strip()}'.")
        else:
            display = matches[["product_name", "product_url", "price"]].copy()
            display = display.rename(
                columns={
                    "product_name": "Product",
                    "product_url": "AH",
                    "price": "Price (€)",
                }
            )
            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                column_config={"AH": st.column_config.LinkColumn(display_text="link")},
            )

            available = [
                n
                for n in matches["product_name"]
                if n not in st.session_state.recipe_ingredients
            ]
            if available:
                to_add = st.multiselect(
                    "Select products to add",
                    options=available,
                    key=f"add_{search.strip()}",
                )
                if st.button("Add to recipe") and to_add:
                    for name in to_add:
                        st.session_state.recipe_ingredients[name] = 1
                    st.rerun()
            else:
                st.info("All matching products are already in the recipe.")

    # --- Current ingredients ---
    if not st.session_state.recipe_ingredients:
        st.info("Search and add at least one product to continue.")
        return

    st.markdown("---")
    st.markdown("**Selected ingredients**")

    to_remove: list[str] = []
    for name in list(st.session_state.recipe_ingredients):
        col_img, col_name, col_price, col_qty, col_rm = st.columns([1, 4, 1, 1, 0.5])
        with col_img:
            img_url = _fetch_product_image(url_by_name[name])
            if img_url:
                st.image(img_url, width=80)
        with col_name:
            st.markdown(f"[{name}]({url_by_name[name]})")
        with col_price:
            st.write(f"€{price_by_name[name]:.2f}")
        with col_qty:
            st.session_state.recipe_ingredients[name] = st.number_input(
                "Qty",
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
        st.markdown("**Step 2: Recipe details**")
        recipe_name = st.text_input("Recipe name")
        servings = st.number_input("Servings", min_value=1, value=4, step=1)
        submitted = st.form_submit_button("Save Recipe")

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
                st.success(
                    f"Recipe **{recipe_name.strip()}** saved (ID {recipe_id}). "
                    "Run the following to update the models:"
                )
                st.code("dbt run", language="bash")
                st.session_state.recipe_ingredients = {}
            except Exception as e:
                st.error(f"Failed to save: {e}")
