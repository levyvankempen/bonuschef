## Context

See `proposal.md` — Why. Verified against the live API:

- `bargainItems(storeId:)` exposes `product { imagePack { medium { url width height } } }`. `imagePack` is a **list**, each entry carrying named sizes. 120 of 120 current clearance items return one.
- `fct_store_clearance` has 121 rows and **0 with an image**, because the only image source is `public.product_images` — a portal-scraped table holding 14 rows, all recipe ingredients.
- `recipeSearch` accepts `sortBy` of exactly `NEWEST`, `POPULAR`, `TRENDING`. `RELEVANCE`, `RATING`, `TITLE` and `DEFAULT` are all rejected.
- `RecipeSearchQueryFilter` is `{group: String!, values: [String!]!}` and the live groups are `veel-gebruikt, menugang, soort-gerecht, recepten-met, speciale-wensen, momenten, seizoen, kooktechniek, keuken, allerhande-magazine`. None is an ingredient, which is why "what can I cook from clearance" still cannot be asked of AH.
- `recipeSearch { filters { ... } }` returns the groups with their values and counts, so the options can be read rather than hardcoded.

## Goals / Non-Goals

**Goals:**

- Put the picture AH already sends next to the item it belongs to.
- Make the add-recipe page useful before anything is typed.

**Non-Goals:**

- Images for the bonus feed or for tracked products generally. The clearance list is where recognition matters most and where the data is already in hand; a wider change would mean a second scrape.
- Retiring `public.product_images`. The recipe builder still populates it for ingredients, and untangling that belongs with the resolution work, not here.
- Caching images locally. They are served from `static.ah.nl` with sane cache headers and the portal is used by one person.

## Decisions

**The image comes from the clearance scrape, not from a join.**
It arrives in the same response as the price and the stock, so asking for it costs nothing and it is correct by construction for exactly the items being shown. The alternative — populating `product_images` for every clearance product — means a second request per product, which is how the recipe builder ended up making a blocking HTTP call per ingredient during a render. The `dim_product` join stays for the recipe path, which genuinely has a different source.

**Take the `medium` size, falling back through the pack.**
The card renders at 64px and the list can be over a hundred items, so the smallest usable size wins; `medium` is the smallest AH reliably returns for products. Picking by name rather than by index because the pack's ordering is not documented and an index would break silently.

**A missing image renders nothing, not a placeholder.**
The portal spec already requires an entry to render when its image is absent. A grey box per row would add visual noise to a list whose job is scanning, and a missing picture is not information.

**Browsing is the default state, searching replaces it.**
The page currently opens on an empty search box, which requires knowing a dish name before the catalogue is any use — the same "you must already know" problem the ingredient matcher has. Opening on the newest Allerhande recipes makes the page answer "what could I cook" rather than only "do you have this". Typing replaces the list rather than filtering it, because a search term and a browse ordering are different intents and combining them invites a UI that expresses neither.

**`sortBy` is validated in the client, not passed through.**
The catalogue accepts three values and rejects everything else at request time, which would surface as the whole catalogue being unreachable — the same confusing failure the `PageSize` scalar produced. Rejecting an unknown ordering before the request keeps the error where the mistake is.

**Facet values are read from the catalogue, never hardcoded.**
`recipeSearch { filters { ... } }` returns them with counts. Hardcoding `seizoen` values would mean a list that silently rots when AH renames one, and a season filter offering a season with nothing in it is worse than no filter.

## Risks / Trade-offs

- **A hundred images on one page is a hundred requests from the browser to `static.ah.nl`.** → They are small, cached, and lazily fetched by the browser; the alternative is a list nobody can scan. Worth revisiting only if the clearance list grows far beyond its current size.
- **Browsing spends the member credential on arrival**, where previously the page cost nothing until a search. → One request per page load, cached for the same lifetime as a search, and the same credential already serves an hourly scrape. Small, but it is a real increase in the interactive share of a credential the scheduled pipelines depend on.
- **`imagePack`'s shape is undocumented and unofficial.** A list of objects with named sizes is what it returns today. → Read defensively: a missing pack, an empty list or an absent size all degrade to no image rather than to an error, because a picture is never worth failing a scrape over.

## Migration Plan

1. Land the repo changes; the CI session set is the gate.
2. Existing clearance rows keep their NULL image until the next scrape, which is hourly. No backfill: the snapshot they belong to genuinely did not record one.
3. Rollback is `git revert` plus a rebuild; the column simply stops being populated.
