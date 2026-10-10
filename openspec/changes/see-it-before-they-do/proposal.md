## Why

Every merge goes straight to the people who were invited. There is nowhere to
watch a change run before they do.

That has been survivable while changes were small and the operator was the only
user. It is not what the operator wants now: the stated goal is to work feature
by feature with AI tooling and stop waiting between them, and the thing that
actually makes that safe is seeing a change working somewhere real before it
reaches a friend's phone in a shop.

The deploy wait was the other half of the complaint and is already fixed - the
timer went from ten minutes to one, and the units it lives in are now actually
installed. Merge to live is about four minutes. This change is the remaining
half, and it is the one about confidence rather than speed.

Two constraints are specific to this system and shape the whole design:

- **There is one Albert Heijn credential, and refreshing it may rotate it.**
  `refresh_tokens` persists a rotated token, so two environments refreshing the
  same credential would invalidate each other's. A second environment therefore
  cannot be a second copy of the pipeline.
- **The portal is published.** A second environment must not be, or an
  unfinished change is reachable by anyone holding the address.

## What Changes

- A **second environment** runs the portal against its own database, on the
  same host, reachable only from the host and the tailnet.
- It **does not scrape**. No pipeline, no credential, no writes to the retailer.
  Its data is a copy of production's, taken on request, so what is being judged
  is the real catalogue rather than a fixture.
- It **says which it is**, in the interface, so a screenshot or a bug report
  cannot be mistaken for production.
- **What is promoted is what was tested**: the same released artifact, not a
  rebuild from the same commit.
- Production keeps its database on the fast disk; the copy and its dumps live
  on the new SSD, where cold bulk belongs.

Deliberately not decided here: whether this is a second compose stack or a
second namespace in a cluster. The requirements are the same either way, and
the operator has not chosen. `argocd-delivers-the-portal` would satisfy them
with one chart and two value files; a second compose project would satisfy them
with a second port. This change says what must be true, not which.

## Capabilities

### Modified Capabilities

- `deployment-target`: a change can be seen running before the people who were
  invited see it; a second environment never touches production's data, never
  holds the retailer credential, and is never published; and what reaches
  production is the artifact that was watched rather than a rebuild of it.

## Impact

- A second database, seeded from a production dump, on the new SSD.
- A second portal process, bound to the host, not on the Funnel.
- Whatever carries the "which environment am I" marker into the interface.
- `docs/deployment.md` - what the second environment is for, how to refresh its
  data, and the rule that it never scrapes.
- No change to the pipeline, the marts, or the portal's features.
