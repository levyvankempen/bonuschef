# Multi-user bonuschef

## Why

bonuschef has one user. Extending it to a handful of friends is worth doing
for its own sake and for the alpha feedback, but it changes three assumptions
the system currently rests on, and each one is load-bearing:

- **There is one store.** `AH_STORE_ID` is an environment variable read at
  startup, defaulting to 1876. Clearance is store-scoped and member-scoped, so
  a second person with a different store is not a preference setting - it is a
  second set of prices.
- **There is one Albert Heijn session.** One refresh token in `.env` fetches
  everything. Per-user stores are only honest if each user's own session
  fetches their own clearance.
- **Every recipe belongs to everyone.** `keep_recipe(engine, recipe_id)` has
  no notion of who kept it, and neither does anything downstream.

The decision taken here is that the catalogue stays shared and everything
*about* a recipe becomes private: your edits, your notes, when you last made
it. A friend adding a recipe helps everyone; a friend renaming an ingredient
does not change your copy.

## What Changes

**New capability: user accounts.** Username and password, sessions, and a
per-user store. Registration is by invitation rather than open signup, because
an open signup on an app holding Albert Heijn sessions is a liability with no
upside at this size.

**Per-user Albert Heijn credentials.** Each user authenticates with their own
AH account. Their refresh token is encrypted at rest with a key held outside
the database, and they can revoke it from the portal. This is the part of this
change with real consequences: a refresh token is a live session to somebody
else's shop account, and the spec says so rather than leaving it implied.

**Recipes gain an owner for the parts that are personal.** The catalogue is
shared. Saved lists, edits, notes and last-made dates are per user.

**The recipes page becomes a dashboard.** Cards rather than a list, showing
when each recipe was last made, filterable to recipes whose ingredients are on
offer right now. Editing a saved recipe, and saving one from the vanavond
page, are included but ranked below those two.

**Catalogue content.** Two Allerhande recipes added (quiche with broccoli and
smoked salmon, tacos with kibbeling and red cabbage), zuurkoolstampot removed.

## Impact

- The portal gains a login wall. Nothing is reachable unbatched by a user.
- `AH_STORE_ID` stops being the source of truth for which store applies.
- Ingestion becomes per-user for clearance, and stays national for bonus.
- Deployment stays on the tailnet. Public exposure is explicitly out of scope
  here and named as a later change, because it needs a tunnel and an abuse
  story that this change does not provide.

## Out of scope, deliberately

- Public internet exposure, TLS termination, rate limiting, abuse handling.
  Named as a follow-up: Cloudflare Tunnel from the LXC, so no port is opened.
- Password reset by email. There is no mail path; an invited alpha user asks
  the operator.
- Sharing, following, or any social feature between accounts.
- Vercel or any serverless host. Streamlit holds a long-lived process and a
  WebSocket per visitor; it does not run on serverless functions at all.
