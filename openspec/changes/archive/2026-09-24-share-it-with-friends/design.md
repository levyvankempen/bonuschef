## Context

See proposal.md for motivation. The constraints that shape the approach:

**Nothing is exposed today.** `docker port streamlit_portal` reports
`8501/tcp -> 127.0.0.1:8501`; Dagster the same on 3000; Postgres on 5455. There
is no reverse proxy on the host and `tailscale serve status` reports no config.
The tailnet holds three devices, all the operator's.

**Funnel arrives from loopback.** Tailscale terminates TLS and proxies to the
local port, so the peer address the application sees is the local hop, not the
visitor. Any per-visitor address therefore comes from a forwarded header - and a
header is the one thing a visitor can write themselves.

**Dagster has no authentication** and can start and terminate pipeline runs.
The existing requirement says so, and says the network restriction is the only
thing in front of it. That is the reason publication is per-interface.

## Goals / Non-Goals

**Goals:**

- A friend opens a link on their phone and signs in. No VPN, no install, no
  router change, no domain.
- Guessing passwords against the published form is not free.
- The exposure is one command to withdraw.

**Non-Goals:**

- Not publishing Dagster, on any address, by any means.
- Not a per-IP quota as a promised behaviour (see Decisions).
- Not a CAPTCHA, not e-mail verification, not password reset. A handful of
  friends and an operator who can be messaged.
- Not changing how accounts are stored or how passwords are hashed.

## Decisions

### The throttle counts against the account, not the address

The lockout is keyed on the attempted username. It is the key that actually
protects an account, it cannot be forged by a visitor, and it works the same
whether the request arrived over the tailnet, over Funnel, or from loopback.

A per-address limit is genuinely useful against spraying many usernames from
one host, and it is deliberately **not** a requirement here, because behind
Funnel it rests on a header. Where an address is used at all, it is read only
when the immediate peer is the local hop - trusting `X-Forwarded-For` from an
arbitrary peer converts the limiter into a bypass, since the attacker chooses
the value and can vary it per request.

*Alternative considered:* PROXY protocol, which Funnel supports for TCP
forwarding and which carries a trustworthy client address. Rejected for now: it
means terminating TLS ourselves, which is the part Funnel is being used to
avoid.

### The count lives in Postgres

An in-process counter resets on every deploy, and deploys happen every ten
minutes by timer. `st.cache_data` is worse than it looks here: it is
process-global, which is right, but it is also cleared by exactly the events an
attacker can wait for. A small table keyed by username, with a timestamp per
attempt, survives both and is already the storage every other account fact uses.

The same table answers "when may this be tried again", which the refusal has to
say.

### A locked account refuses a correct password too

Otherwise the lockout only delays a guess that has already landed: the attacker
who finds the password during the window simply returns after it. This also
keeps the refusal uniform, which is what stops the message from distinguishing a
real account from an absent one.

### The refusal must not become an oracle

`sign_in` already returns the same refusal for an unknown username as for a
wrong password, and deliberately spends the same work on both. A lockout message
that appears only for accounts that exist would undo that in one line. So the
locked refusal is the same shape as the others, and the test asserts the two are
indistinguishable rather than asserting each separately.

### Publish the portal only, by publishing one port

`tailscale funnel` is pointed at 8501. Dagster's 3000 and Postgres's 5455 stay
bound to loopback in compose and are named in no serve config. Nothing about
publishing the portal touches them, and the spec scenario pins that so a later
convenience cannot quietly add one.

## Risks / Trade-offs

- **The URL is public.** Funnel's address is not secret and not indexed, but
  anyone who has it can reach the sign-in form. That is the trade accepted in
  exchange for friends installing nothing, and it is why the throttle ships
  first rather than after.
- **A lockout is a denial of service against one account.** Someone who knows a
  friend's username can keep them locked out. At this size the operator can be
  messaged, and the alternative - no lockout - is worse against the attack that
  actually matters.
- **The invitation code is shared, not per-person.** Rotating it is the only
  revocation, and it revokes for everybody at once. Acceptable for a handful of
  friends; a per-person invitation is the natural next step if that stops being
  true.
- **Tailscale becomes a dependency of reaching the app at all.** It already is
  for the operator's own access, so this adds no new party.
