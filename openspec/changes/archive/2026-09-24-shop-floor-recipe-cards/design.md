## Context

See proposal.md for motivation. The constraints that actually shape the approach:

**The image ceiling is 440x324, and it was measured, not assumed.** Stored URLs
look like `https://static.ah.nl/static/recepten/img_122541_220x162_JPG.jpg`, so
the variant is in the path. Probing that path on two different recipes:

| variant | result |
|---|---|
| `220x162` | 200, 9.4 KB - what every stored row holds |
| `440x324` | 200, 32.5 KB |
| `330x243`, `550x405`, `640x472`, `660x486`, `700x520`, `800x600`, `880x648`, `1200x630`, `1320x972` | 404 |

Two variants exist. This kills the obvious plan - re-fetch with a larger
`min_width` in `_smallest_image` - because there is nothing larger to fetch: the
helper's `or usable` fallback would return 440 anyway, after a full pool refresh
and a backfill of already-adopted rows. Rewriting the URL gets the same pixels
for no pipeline work, and reaches all 908 existing rows at once.

It also sets a hard limit. 440 CSS pixels is about 1.2x a phone's content column,
which is a sharp render; it is about 0.6x a desktop `centered` column, which is
not. The spec's "SHALL NOT be enlarged past the resolution the source publishes"
exists because of this measurement.

**`st.columns` do not stack.** A two-column desktop grid is a two-column 170px
phone grid. `recipes_page`'s module docstring already argues this and it is
right. Streamlit exposes no viewport width, so there is no honest responsive
fallback and no grid anywhere in this change.

**Every widget interaction is a full script rerun.** The portal has exactly one
`st.fragment` today. On shop signal, a rerun that re-renders six cards to apply a
filter is the difference between usable and not.

**The data is already at the right grain.** `int_recipe_item_opportunity` carries
`(store_id, recipe_id, item_key, item_label, product_name, is_discounted,
offer_kind, item_saving)`. Nothing in this change needs a new model, a new mart
or a pipeline run. Measured on production today: 910 recipes, 1,909 distinct
ingredient labels, of which **55 are discounted** and 304 recipes carry at least
one offer.

## Goals / Non-Goals

**Goals:**

- One card renderer, used by both pages, so the tonight card and the saved-recipe
  card cannot drift apart again.
- The in-store path - open app, see dish, see saving, see which discounted
  ingredient drives it - costs zero taps.
- Finding a recipe for a discounted ingredient costs one tap.
- The tonight page gets cheaper to render than it is now, not dearer.

**Non-Goals:**

- No responsive grid. One card per row at every width (see Context).
- No change to ranking, pricing, saving arithmetic, or the lower-bound wording.
  This change is presentation and one new read path.
- No new mart, dbt model or column.
- Not the shopping list, not URL state, not cook time, not the clearance page's
  filters. Named in the proposal as deferred.

## Decisions

### Rewrite the image URL rather than re-fetch it

A pure function maps `_220x162_` to `_440x324_` in a `static.ah.nl` recipe URL and
returns the input unchanged for anything it does not recognise. Applied at read
time, so it needs no migration and self-corrects if AH's naming changes (the
unrecognised URL simply passes through and renders as it does today).

*Alternative considered:* raise `min_width` in `_smallest_image` and backfill.
Rejected on the measurement above - it buys the same 440 pixels for a pool
refresh plus a backfill of `ah_recipes.image_url`.

*Alternative considered:* rewrite in dbt, in `int_pool_recipes_available`.
Rejected because it would fix the pool and not the person's own adopted recipes,
which come from a different table, and because a display concern in a mart is a
worse place to find it later.

### One shared card renderer in `ui.py`

`render_recipe_card(...)` takes what it draws - image, title, saving phrase,
price line, badges, the named discounted ingredients, the action slot - and both
pages call it. Today there are four near-identical renderers
(`_render_lead`, `_render_brief`, `_render_cheapest_anyway`,
`recipes_page._render_card`) which is exactly how the saving ended up as a
heading in one and a caption in another.

Lead and runner-up differ by **type scale and how much they carry**, never by
image size: the lead gets the saving at `##`, up to three named ingredients and
its rating; a runner-up gets `###` and one. Both get the full-width image. The
56px runner-up thumbnail is the single worst thing on the page today.

### The discounted ingredients come from the reader that already exists

`read_recipe_opportunity_items` is already ordered by `item_saving DESC`, so the
top rows filtered on `is_discounted` are the named ingredients, in the right
order, at no extra cost. The card shows the largest two or three and a count for
the rest, so "and 2 more" never hides the biggest saving.

### Ingredient search belongs on the tonight page, not on a new page

It filters the list that page already ranks. A new page would need a sixth
navigation slot in a bar that already overflows on a phone, and would have to
reimplement the card renderers, the stale-clearance withdrawal, and the
lower-bound price rules - two surfaces deciding what "current" means, which is
the drift that `offers.py` and `freshness.py` were extracted to prevent.

It degrades to nothing: an empty box is today's page, byte for byte.

### The tap targets are the discounted ingredients, not a blank box

55 of 1,909 ingredient labels are discounted today. A free-text box over the
other 1,854 mostly answers "nothing on offer with that", and typing one-handed
in a shop is the interaction we are trying to remove. So the primary control is a
row of the discounted ingredients that appear in the most ranked recipes, as
direct choices; the text field stays for "I already have courgette at home".

The list is bounded to what fits - the head of the distribution is steep
(`verse platte peterselie` 80 recipes, `scharrelkipfilet` 20, `kipfilet` 15), so a
short row carries most of the value.

### The filtered list re-renders inside a fragment

Choosing an ingredient must not rerun the whole page, including the banners and
the coverage block, over shop wifi.

### The collapsed detail stops costing

The ingredient list moves from `st.expander(expanded=False)` to the
button-to-open pattern `recipes_page` already uses and documents. Streamlit
executes an expander's body whether or not it is open, so today one render of the
tonight page issues up to six extra queries and registers ~54 correction buttons
that nobody asked to see. This is a straight deletion of work, and it is what the
spec's new "A detail section nobody opened" scenario pins.

## Risks / Trade-offs

- **440 is not retina on a phone, and is soft on desktop.** It is 4.7x the pixels
  of today's 220 and it is everything the source has. The spec forbids stretching
  past it, so the desktop card caps its image rather than blurring it. If AH ever
  publishes a larger variant the rewrite is one string.
- **32.5 KB per image instead of 9.4 KB.** Six cards is ~195 KB against ~56 KB,
  on the connection least able to afford it. Judged worth it: the thumbnail is
  currently unrecognisable, which costs a scroll and a tap instead. The
  eager-expander deletion removes up to six queries and ~54 widgets from the same
  page, so the render gets cheaper overall.
- **A card is taller than a paragraph**, so fewer recipes fit on a screen. That is
  the intended trade - the page answers "what shall I cook", and the lead card is
  meant to be the answer rather than the first row of a table.
- **`st.pills` under AppTest.** Two files in this repo record that AppTest
  mis-reads `st.segmented_control`'s single-select value as a sequence. Multi-select
  `st.pills` returns a list and should be fine, but the tests must assert the
  filter's *effect*, not just that the widget exists - the same trap that let a
  crashing page ship with a passing test.
- **The URL rewrite is a string match on a third party's path convention.** It
  fails open: an unrecognised URL renders exactly as it does today.
