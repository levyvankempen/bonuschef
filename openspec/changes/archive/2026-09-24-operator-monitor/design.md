## Context

See proposal.md. The facts that shape it:

Everything the page shows already exists. `accounts` carries `created_at`,
`last_sign_in_at`, `store_id` and `is_operator`; `account_recipes` carries
`saved_at`, `last_made_at` and `notes`; `account_sessions` carries
`last_seen_at`. No schema change, no pipeline change.

`last_sign_in_at` is not the question being asked. Somebody who signed in six
weeks ago and has used the app every day since has a six-week-old sign-in and a
session touched this morning. **`max(account_sessions.last_seen_at)` is "last
opened"**; the sign-in date is when they first got in.

## Goals / Non-Goals

**Goals:**

- Answer "is anybody using this", and "did somebody get stuck", in one screen.
- Be unreachable by anyone who is not an operator, by access control rather
  than by being unlinked.

**Non-Goals:**

- Not editing anyone's data from here. It is a window, not a console. Deleting
  an account stays a deliberate act at the database.
- Not charts. Three accounts do not need a time series.
- Not exported anywhere.

## Decisions

### The check lives in the render function, not only in the navigation

`app.py` omits the page from `st.navigation` for accounts that are not
operators, which is what keeps it out of the way. That is presentation, and
presentation is not a wall: `render_monitor` re-reads `account.is_operator` and
refuses on its own. A page that is safe only because nothing links to it is one
refactor away from being public, and this one displays other people's data.

The spec pins both halves separately for that reason.

### "Never" is a state, not a blank

An account created and never signed in, and an account signed in but with no
shop chosen, are the two shapes of "this person got stuck" - which is the thing
the operator most wants to catch, and exactly what a dash or a zero hides. They
are rendered as their own words.

### The store is resolved to its name

`store_id` is a number. The operator wants to know it is the Kamperfoelielaan,
not 1876, and `int_store` already holds the name the rest of the portal shows.

### Passwords are not on the page, and the reader does not select them

`password_hash` is excluded from the SELECT rather than merely left unrendered.
A column that is never fetched cannot be leaked by a later change to the
rendering, and the spec has a scenario for it.

## Risks / Trade-offs

- **It shows other people's collections.** That is the deliberate choice
  recorded in the proposal. The operator hosts the database and can read it
  directly, and the invitee document already says so - but a page makes it
  routine in a way that psql does not, and that is a real difference even if it
  is not a new capability.
- **`is_operator` becomes load-bearing for privacy.** It was previously about
  who could trigger a rebuild. Anything that grants it now grants reading
  everybody's data, which is worth remembering the next time it is handed out.
