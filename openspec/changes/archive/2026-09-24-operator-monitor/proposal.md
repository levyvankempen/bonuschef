## Why

The portal is now published and other people have accounts on it. The operator
has no way to see whether anybody is using it, whether a friend got stuck
before picking a shop, or whether an account has been dormant since the day it
was made. The only way to find out today is to open psql.

## What Changes

- A page visible **only to an operator account**, listing every account with
  when it was created, when it was last opened, which Albert Heijn it is
  connected to, and what it has saved.
- The privacy requirement is amended to say so. It presently says account data
  is readable only by that account, and names the store and the saved recipes
  among the things it covers. This change makes the operator an explicit
  exception rather than leaving the page in contradiction with the text - which
  is the drift that had to be repaired in `user-accounts` once already.

The operator could already read all of this straight from the database, and
`docs/for-people-invited.md` already tells invitees so. This makes it routine
rather than new, which is the part the spec has to record.

The operator decided not to expand the invitee document beyond the line it
already carries. That is a deliberate choice and it is noted here so the next
reader knows it was made rather than overlooked.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-accounts`: account-scoped data is readable by that account and by an
  operator; it remains invisible to every other account.
- `portal`: an operator can see the state of the system it runs - who has an
  account, when they were last here, and what they have.

## Impact

- `src/bonuschef/portal/monitor_page.py` - new.
- `src/bonuschef/portal/app.py` - the page is registered only for an operator.
- `src/bonuschef/portal/db.py` - one reader for the account overview, one for a
  single account's saved recipes.
- No schema change: `accounts`, `account_recipes` and `account_sessions` already
  carry everything shown.
