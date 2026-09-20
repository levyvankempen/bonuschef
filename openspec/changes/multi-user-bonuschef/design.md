# Design

## The decision that shapes everything else

Per-user Albert Heijn credentials. It is the right answer - clearance is
member-scoped, so a shared session gives a friend clearance that is really the
operator's - and it is the reason this change is not small.

A refresh token is a live session to somebody else's supermarket account. The
project already holds one of these; the difference is that holding your own
carelessly is your problem, and holding four of them carelessly is four other
people's. That drives the encryption requirement, the revocation requirement,
and the decision not to offer open signup.

## Authentication

Password hashing with a deliberately slow, salted algorithm. Sessions keyed by
an opaque token, not by anything derived from the username.

Streamlit has no session model of its own worth using here: `st.session_state`
is per-browser-connection and evaporates. The session record belongs in
Postgres so that a restart does not sign everybody out, and so that revocation
means something.

The sign-in gate has to sit in front of page rendering rather than inside each
page, or the first page anyone forgets to guard is the hole. One entry point
that either renders the sign-in form or dispatches to the app.

## Data model

Three shapes, in increasing order of how much they change:

1. **Account-owned singletons.** Store, AH credential, password hash. A row
   per account.
2. **Account-scoped facts about shared rows.** Saved, last made, notes. A join
   table keyed on (account, recipe) - the recipe stays in one place.
3. **Account-scoped overrides of shared rows.** Edits. The recipe's ingredient
   lines are shared; an account's edit is an override layered on read. Copying
   the whole recipe on first edit is the other option and is simpler, at the
   cost of the edited copy never again receiving catalogue corrections.

The override approach is chosen. The catalogue is maintained - recipes get
withdrawn, ingredients get re-resolved - and a fork stops receiving that.

## What this does to ingestion

Bonus stays national and stays one fetch. Clearance becomes per store, which
means per account with a credential. That is a fan-out in the Dagster asset
graph rather than a new pipeline, but it changes the shape of the clearance
tables: they gain a store dimension that is presently implicit.

`AH_STORE_ID` stops being the source of truth. It should remain as the default
for an account that has not chosen, rather than being deleted, so that a
single-user deployment still works with no configuration.

## Hosting

Stays on the tailnet for this change. Friends join the tailnet; no port opens,
no certificate is needed, no bot ever sees the sign-in page.

Public exposure is a separate change and should be a Cloudflare Tunnel - an
outbound connection from the LXC, so the router stays closed - with TLS and a
domain terminating at Cloudflare. It needs rate limiting and an abuse story
that this change does not provide, which is why it is not in this change.

Serverless hosts are not an option and the spec says so explicitly, because it
is the kind of thing that gets tried once: Streamlit holds a long-lived
process and a WebSocket per visitor.

## Order of work

The catalogue content changes are independent of everything else and can go
first. Accounts must precede per-user stores, which must precede per-user
credentials, which must precede per-user clearance. The dashboard and the
on-offer filter depend only on accounts existing.

## What is deliberately not solved

Password reset needs a mail path, and there is none. For a handful of invited
users, the operator setting a new password is the honest answer rather than
building mail infrastructure for four people.
