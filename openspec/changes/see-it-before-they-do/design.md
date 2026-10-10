## Context

One host, 192.168.1.144, LXC 101. Four containers, ~780 MiB resident in total
(dagster-daemon 467, postgres 172, dagster-webserver 74, streamlit 68) against
a 2 GiB limit, with 9.8 GiB free on the host. A 1,115 MB database. A second
environment is not a capacity question here, which is why the design can be
decided on other grounds.

Three facts about the existing delivery path shape everything below, and two of
them were discovered while writing this rather than assumed.

**A release is a git tag, and each host builds its own image from it.**
`scripts/deploy.sh` checks out `refs/tags/<tag>` and runs
`docker compose up -d --build`. There is no image artifact anywhere. So
"promote what was watched" is not satisfiable today even in principle: two
hosts, or one host at two moments, build independently.

**Python dependencies are reproducible; the base image is not.** The Dockerfile
runs `uv sync --frozen`, so `uv.lock` pins the Python side exactly. But the
base is `ghcr.io/astral-sh/uv:python3.12-bookworm` - a floating tag. Two builds
a fortnight apart get different Debian and CPython patch levels from the same
commit. That is the whole gap between "same source" and "same artifact", and it
is narrow but real.

**All four services set `container_name`.** A second compose stack on the same
host collides on the names immediately; Compose's project-name prefix does not
apply to an explicit `container_name`. Ports collide too, and the named volumes.

## Goals / Non-Goals

**Goals**

- A second environment, on the same host, with its own database and no retailer
  credential.
- A one-command copy of production's data into it.
- One image per version, built once, run by both.
- A visible marker so the two cannot be confused.

**Non-Goals**

- Kubernetes, Argo CD, or a cluster. Discussed below, deliberately not here.
- Automatic promotion. The operator decides what gets promoted; this change
  makes "what was watched" a meaningful phrase, not a gate.
- Continuous data sync. The copy is on request. A test environment whose data
  moves under you is one where you cannot tell a defect from a refresh.
- Any second retailer credential, ever. That is a requirement, not a scope line.

## Decisions

### A second Compose project, not a cluster

The operator asked for Kubernetes with Argo CD, and `argocd-delivers-the-portal`
specifies it. This change is deliberately buildable without it, for a reason
worth stating plainly: **the test environment is the thing that was wanted, and
the cluster is one way to get it.** The stated motivation was not wanting a
cluster for its own sake - it was waiting between changes and not knowing
whether something works. The deploy half of that is already fixed (one-minute
timer, units now actually installed, merge to live about four minutes). This is
the confidence half, and on a single host a second Compose project delivers it
in an afternoon rather than after a control plane.

Nothing here is wasted if the cluster follows. Every requirement is written
about environments rather than mechanisms - "its own database", "not published",
"the artifact that was watched" - and all six are satisfied by two namespaces
and two value files exactly as well as by two Compose projects. The migration
replaces the *how* and keeps the *what*, which is the point of specifying it
this way round.

The honest cost: two Compose files to keep in step, which is the duplication a
Helm chart with two value files exists to remove. At two environments and four
services, that is a smaller problem than a control plane on a 16 GiB desktop.

### One image per version, built once

This is the change that makes promotion mean something, and it is small.

Today `deploy.sh` builds. Instead: build once, tag the image
`bonuschef:<version>`, and have both environments reference `image:` rather
than `build:`. Both then run bit-identical code, and promotion is pointing
production's tag at a version that is already on the host.

The base image gets pinned by digest at the same time. Without that, "built
once" still holds for a single version but drifts between versions for reasons
nobody chose, and a floating base is how a deployment acquires a CPython patch
bump that nobody can find in the diff.

No registry is needed while there is one host: the image is in the local
daemon's store and both projects see it. A registry becomes necessary when the
cluster arrives, which is the cluster's problem to solve.

### The copy: `pg_dump` over the network boundary that already exists

`pg_dump` from the production container into a file on the SSD, `pg_restore`
into the test container. One script, `scripts/copy-to-test.sh`.

`pg_dump` and not a volume snapshot, because a snapshot of a running Postgres
data directory is a torn file and the restore is a coin toss, while `pg_dump`
runs in a transaction and production keeps serving - which the requirement
demands.

The dump file is kept rather than streamed. It is the thing that makes the copy
repeatable without touching production again, and it records when it was taken:
the restore writes that timestamp into a one-row table that the portal reads for
the "data copied at" line. Taking the age from the newest row in the data
instead would conflate "the copy is old" with "production's pipeline was down
when I copied", which are different things and read identically.

Both the dump files and the test database live on `/dev/sda`, the 500 GB SSD.
Production's Postgres stays on the NVMe. This is the one place where the new
disk changes a decision rather than merely providing room: a 1.1 GB restore and
a 1.1 GB dump file alongside production's working set on one spindle is
avoidable contention.

### The credential is absent by omission, not by configuration

The test project's Compose file **does not contain the dagster-daemon service**.
Not present with an empty schedule, not present and scaled to zero - absent.

A disabled scheduler is one `docker compose up dagster-daemon` from being an
enabled one, and the failure mode is not a broken test environment but a
silently rotated production credential and prices that stop updating. The
requirement says the jobs are absent rather than idle, and this is what absent
costs: the test environment cannot run a pipeline at all, and its data only ever
changes when someone copies it.

That also removes the 467 MiB resident daemon, which is most of why the second
environment is cheap.

The dagster-webserver is kept, because reading what the last production run did
is useful and it starts nothing on its own.

### The marker rides the version path

`bonuschef.version` already carries `BONUSCHEF_VERSION` and `BONUSCHEF_COMMIT`
into the portal footer. `BONUSCHEF_ENVIRONMENT` joins them, unset or
`production` in production and `test` in the second environment.

Rendered as a banner rather than a footnote, and at the top. The footer was
right for the version - "a footnote rather than chrome", as the code says,
because the version answers a question only occasionally asked. Which
environment you are looking at has to be answered before you read anything else
on the page, or the page misinforms you.

Absent in production by design. An invited person has one environment and
labelling it is noise, which is the second scenario in the requirement.

## Risks / Trade-offs

**Two Compose files drift.** The duplication is real and will be gotten wrong at
least once. Mitigated by a test that reads both files and asserts the service
set and image reference agree, and by the test file being a short override
rather than a copy. Not eliminated.

**A copy of production's data is a copy of production's accounts.** The test
database contains real usernames, real password hashes, real saved recipes for
the invited people. It is on the same host, behind the same host boundary, and
not published - so the exposure is not new. But it is a second place the hashes
live, and it is worth saying rather than discovering. Not scrubbing them: the
accounts are what makes the copy realistic, and a scrubbed copy cannot reproduce
a defect in the per-account pricing that this exists to catch.

**Promotion stays manual, and "what was watched" is a claim nobody checks.**
Nothing here prevents promoting a version that was never run in test. The
requirement deliberately allows it - an urgent fix must not wait on a broken
test environment - which means the discipline is the operator's. A gate would be
the cluster's job.

**The test environment will be left broken.** It is nobody's production, so a
failed copy or a stopped container will sit there until someone needs it, which
is exactly when a broken one is most expensive. Its health is therefore surfaced
on the operator's Beheer page rather than being something to remember to check.

## Open Questions

None blocking. One deferred: whether the test environment should get its own
Tailscale hostname on the tailnet rather than being reached by host and port.
A name is kinder than remembering a port, and the tailnet is not the internet,
so it satisfies "not published" either way. Left out because it adds a serve
configuration to keep correct for a convenience, and the port works.
