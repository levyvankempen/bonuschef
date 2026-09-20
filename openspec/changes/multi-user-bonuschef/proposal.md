# Multi-user bonuschef

## Why

bonuschef has one user. Extending it to a handful of friends is worth doing
for its own sake and for the alpha feedback, but it changes assumptions the
system rests on, and several are load-bearing.

## What the review found

Three specialist reviews - architecture, backend, frontend - were run against
the first draft of this proposal. They found four things in it that were
simply wrong, and those corrections are the most useful part of this document.

**Clearance may not be member-scoped at all.** The first draft justified
per-user Albert Heijn credentials by claiming a shared session would give a
friend "clearance that is really the operator's". The query is
`bargainItems(storeId: $storeId)` - store-parameterised and authentication-
*gated*. Whether the response also varies by member is **untested**, and it
decides the grain of six models. If gated, per-user credentials are still
worth having - for rate limiting, and for not lending one bonuskaart session
to four people - but that is a different and smaller justification.

**Today, an account without a credential would see nothing at all.**
`int_store` is derived from scraped markdowns, and `int_product_offer_today`,
`int_recipe_item_opportunity` and `fct_recipe_opportunity` all join it. A
store nobody has scraped has no row, so it gets zero rows - including for
national promotions. The first draft promised "bonus prices are still shown,
clearance is withheld". That is unachievable until `int_store` is re-sourced
from accounts rather than from scrapes.

**The portal does not filter by store, and its caches are process-global.**
`store_id` appears exactly once in the whole portal layer and never in a
`WHERE`. `@st.cache_data` is shared across every visitor to the process, and
this project's convention of prefixing the engine with an underscore excludes
it from the cache key. Nine readers would serve the first arrival's data to
everyone else, deterministically, and it would look right.

**The stated reason for overrides-not-forks was false.** The draft said a
forked recipe stops receiving catalogue corrections. Re-resolution is keyed on
`concept_id`, not on the recipe, and `_ALL_INGREDIENT_LINES` unions adopted
and pool lines precisely so a concept is re-judged either way. Adoption is
already a fork and was accepted for exactly this reason. Overrides are still
the right answer, but on different grounds: they keep the account dimension
off the 2,002-recipe pool, which is the difference between ~360 extra rows and
~336,000.

## What Changes

**New capability: user accounts.** Sign-in before anything renders, a store
per account, and isolation of everything personal. Registration is by
invitation: an open signup form on an application holding other people's
supermarket sessions is a liability with no upside at four users.

**Per-user Albert Heijn credentials**, encrypted at rest under a key held
outside the database, revocable from the portal. Two hazards the review found
in the existing code must be closed first: `AHTokenManager._candidates()`
falls back to the bootstrap `AH_REFRESH_TOKEN`, so a friend's dead credential
would silently refresh using the operator's; and `AH_TOKEN_FILE` is one shared
file on a shared volume.

**A three-way data split**, not two. Shared catalogue *including the ~1,900
resolved concepts* - those are facts about the catalogue, not opinions, and
scoping them per account would hand every friend an unpriceable collection.
Per-account annotations *including verdicts* - today one person's "niet voor
mij" hides a recipe from everyone, and one person adopting removes it from
everyone else's pool. Per-account secrets.

**The recipes page becomes a dashboard.** Cards with last-made dates,
filterable to what is on offer today for that person's store. The page
currently renders the same rows three times and its detail pane makes you
re-select a recipe you are already looking at.

**Catalogue content.** Shipped already in #76.

## Impact

- The portal gains a sign-in wall. Nothing renders without an account.
- `AH_STORE_ID` becomes the default for an account that has not chosen, not
  the source of truth.
- `int_store` stops being derived from scrapes, which means dbt gains a
  dependency on a portal-owned table.
- Ten declared grains widen, or are deliberately kept narrow and said so.
- Deployment stays on the tailnet.

## Out of scope, deliberately

- Public internet exposure. A later change, and it should be a Cloudflare
  Tunnel - outbound-only from the LXC, so no port opens.
- **Self-service Albert Heijn connection.** AH's OAuth client redirects to
  `appie://login-exit`, a custom scheme no web page can receive, behind
  hCaptcha. There is no server-side callback to build. Connecting means
  copying a code out of a blocked redirect in desktop DevTools, or the
  operator doing it for you. This materially limits who can be invited.
- Password reset by email. There is no mail path.
- Any social feature between accounts.
- Vercel or any serverless host. Streamlit holds a long-lived process and a
  WebSocket per visitor.
