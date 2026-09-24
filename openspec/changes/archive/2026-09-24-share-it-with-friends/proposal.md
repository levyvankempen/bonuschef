## Why

The portal listens on `127.0.0.1:8501` on the container and nowhere else. There
is no reverse proxy and no `tailscale serve`, so today it is reachable only
through an SSH tunnel by the one person who holds the key. Sharing it with
friends means publishing it, and publishing it changes what the sign-in wall is
for: right now it guards a port nobody else can open, and afterwards it is the
only thing between strangers and other people's data.

Streamlit brings no brute-force protection of its own. A public URL with an
unthrottled password form is an unlimited guessing budget against a gate whose
accounts belong to friends. So the throttle is a prerequisite for the exposure,
not a follow-up to it.

Reading the specs to plan this surfaced a disagreement that has to be settled
first. `user-accounts` says self-service registration SHALL NOT exist and that a
stranger finds "no route to create one"; the portal has offered exactly that
since the multi-user change, behind an invitation code. The code is the better
answer and matches the requirement's own title, so the requirement is what moves.

## What Changes

- The throttle is **written down**. Planning this found it already built and
  tested - attempts recorded in Postgres, five failures inside fifteen minutes,
  checked before the password is looked at, and recorded for unknown usernames
  too so it cannot be used to discover which accounts exist. No requirement
  anywhere mentioned it. Behaviour a reader cannot find in the spec is
  behaviour the next change is free to remove by accident.
- The requirement forbidding self-service registration is **reconciled with
  what ships**: holding the invitation code *is* the invitation. What must stay
  true - that nothing reveals whether a username exists - is kept and tested.
- The portal is **published over HTTPS** on a Tailscale Funnel address, so
  friends need install nothing and the home network is never port-forwarded.
- **Only the portal.** Dagster is published to nothing. It has no authentication
  and can start and terminate pipeline runs, which is precisely why the network
  restriction that presently covers both cannot simply be lifted.

Deliberately not in this change: per-IP limiting as a *requirement*. Behind a
Funnel the request reaches the app from loopback, so an address is only
trustworthy if it arrives on a forwarded header from that local hop - and a
header is exactly what an attacker would forge. The design says how to use one
safely where it can be trusted, and nothing depends on it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-accounts`: repeated failed sign-ins are slowed and then refused for a
  period; the invitation-code registration that ships is described accurately,
  while still refusing to disclose whether a username exists.
- `deployment-target`: the portal may be published to the internet over HTTPS
  for named people, while every other interface - Dagster above all - stays
  unreachable from outside the host.

## Impact

- `src/bonuschef/portal/accounts.py` - the throttle and the lockout around
  `sign_in`.
- `src/bonuschef/portal/schema.py` - a table recording attempts, so the count
  outlives a restart.
- `src/bonuschef/portal/gate.py` - saying that an account is locked without
  saying whether it exists.
- `docs/deployment.md` - the Funnel path, and how to withdraw it in one command.
- No change to Dagster, the pipeline, or the compose port bindings, which stay
  bound to loopback.
