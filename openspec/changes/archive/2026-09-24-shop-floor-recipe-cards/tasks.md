## 1. The image, at the size the source actually has

- [x] 1.1 Add `bigger_image(url)` to `portal/ui.py`: rewrite `_220x162_` to
      `_440x324_` in an `static.ah.nl` recipe URL, return anything else unchanged.
- [x] 1.2 Test it: the known URL upgrades; a URL with an unknown variant, a
      non-AH URL, an empty string and `None` all pass through untouched.
- [x] 1.3 Test that the card never renders wider than the source: a card asked for
      more than 440 caps there rather than stretching.

## 2. One card renderer

- [x] 2.1 Add `render_recipe_card()` to `portal/ui.py` inside
      `st.container(border=True)`: image first at full card width, then the saving
      as the largest text, then the price line, then badges, then the named
      discounted ingredients, then the action slot.
- [x] 2.2 Give it a `lead` mode (saving at `##`, up to 3 named ingredients,
      rating) and a runner-up mode (`###`, 1 named ingredient). Same image size in
      both - the difference is type scale and how much is carried.
- [x] 2.3 Render nothing where there is no image, with no reserved gap.
- [x] 2.4 Test: image precedes all text; the saving is the largest element; a
      recipe without an image still renders; lead and runner-up get the same image
      width.

## 3. Name the discounted ingredients on the card

- [x] 3.1 From the existing `read_recipe_opportunity_items` (already ordered by
      `item_saving DESC`), take the discounted rows and pass the top N plus a
      remainder count to the card.
- [x] 3.2 Render each as a badge carrying the ingredient and its saving, green for
      bonus and orange for clearance, matching the vocabulary already in use.
- [x] 3.3 Test: the largest savings are the ones named; the remainder appears as a
      count and is never silently dropped; a recipe with no discounted ingredient
      renders no badges.

## 4. Adopt the card on both pages

- [x] 4.1 Replace `_render_lead`, `_render_brief` and `_render_cheapest_anyway` in
      `tonight_page.py` with calls to the shared renderer.
- [x] 4.2 Replace `recipes_page._render_card` with the same renderer, keeping the
      title, cost-where-known and last-made facts its spec requires.
- [x] 4.3 Keep `_saving_phrase`'s "minstens" wording and the `±` price convention
      verbatim - promoting the saving must not turn a lower bound into a figure.
- [x] 4.4 Collapse the three-button action row into one full-width primary action
      plus a popover for the rest, so nothing truncates at 358px.
- [x] 4.5 Test: the lower-bound wording survives on a partially-priced recipe; the
      saved-recipe card carries its image; both pages render without exception.

## 5. Start from an ingredient

- [x] 5.1 Add a cached reader returning recipes whose `item_label` or
      `product_name` matches a term, for the active store, keeping the existing
      order. Bound the query rather than filtering afterwards.
- [x] 5.2 Add a cached reader returning today's discounted ingredient labels with
      how many ranked recipes use each, most first, bounded to what the row shows.
- [x] 5.3 Render the discounted ingredients as `st.pills` above the lead card, and
      a text field beside them for anything else.
- [x] 5.4 Put the filtered list in an `@st.fragment` so choosing an ingredient does
      not rerun the banners and the coverage block.
- [x] 5.5 Empty result answers in terms of the ingredient and still offers the
      cheapest recipes using it, reusing the existing `_render_cheapest_anyway`
      pattern rather than a new one.
- [x] 5.6 Test the *effect*, not the widget: choosing an ingredient narrows the
      cards to recipes using it; naming one matches on both the recipe's word and
      the product name; an unmatched term still shows the fallback; an empty box
      leaves the page exactly as it was.

## 6. Fix what is in the way

- [x] 6.1 `recipes_page.py` search: treat the term as literal text, not a regex.
- [x] 6.2 Test that `40+`, `kip (`, `*` and `[` each return a result set and do not
      raise - this is a live crash today.
- [x] 6.3 Put "Verwijderen" behind a confirming step, away from a single tap
      beside "Gemaakt vandaag".
- [x] 6.4 Test that one tap does not delete, and that confirming does.
- [x] 6.5 Move the ingredient list from `st.expander` to the button-to-open
      pattern, so a closed section issues no query and registers no controls.
- [x] 6.6 Test that rendering the tonight page with cards closed issues no
      per-recipe item query, and that opening one does.
- [x] 6.7 Move pipeline health and the coverage commentary below the lead card,
      leaving above it only what changes what to buy - stale clearance and a
      credential failure. This is the portal spec's existing "product, not the
      pipeline" requirement, presently unmet on this page.
- [x] 6.8 Test that the first thing the tonight page renders after its title is a
      recipe, not pipeline telemetry.

## 7. Verify for real

- [x] 7.1 Full suite green; no test asserts only that copy exists - each asserts
      the page does not raise.
- [x] 7.2 Mutate each new rule (the URL rewrite, the ingredient filter, the
      literal-text search, the delete guard) and confirm a test fails for each.
- [x] 7.3 After deploy, verify on the running container by behaviour rather than by
      grepping for a comment: the upgraded URL, the filter narrowing the list, and
      a closed card issuing no item query.
