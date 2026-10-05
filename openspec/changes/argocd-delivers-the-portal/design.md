## Context

Measured on the host, not estimated:

| | |
|---|---|
| host | HP EliteDesk, i5-7500T, 4 cores |
| RAM | 15.5 GiB total, 5.0 used, **9.8 free** |
| swap | 7.6 GiB, unused |
| disk | **one** 119 GiB Samsung PM991 NVMe |
| `local` | 39 GiB, 22 free |
| `local-lvm` | 54 GiB, 26 free |
| LXC 101 bonuschef | 2 GiB RAM, 16 GiB rootfs at **67% full** |
| VM 100 haos | 4 GiB RAM |
| allocated | 6 of 15.5 GiB |

The repository is **public**, so GHCR is free and ArgoCD reads the repo with no
credential. Images are built on the box today by three compose services from one
Dockerfile; nothing in CI publishes anywhere.

## Goals / Non-Goals

**Goals:**

- A push to GitHub changes what runs, with the cluster reconciling toward the
  repository.
- The published address keeps working across the move. It has been shared.
- The cluster is subject to every guarantee the compose stack is.

**Non-Goals:**

- Not moving Postgres. See below.
- Not high availability. One node cannot provide it, and pretending otherwise
  would be the worst outcome of this change.
- Not multi-node, not an ingress controller beyond what serves the portal, not
  cert-manager - Tailscale already terminates TLS.
- Not replacing Dagster's scheduler with CronJobs. Its schedules carry reasoning
  this change has no cause to relitigate.

## Decisions

### Storage: the 500 GB M.2 is a prerequisite, not an improvement

A k3s VM needs an OS, containerd's image store and etcd. The images here are
Python with uv, pandas, dbt and Dagster - the three app images share a base but
still land in the low tens of gigabytes once a few versions accumulate, because
a GitOps rollback is only real if the previous image is still on disk.

Budget: 8 GiB OS, 20 GiB images across a handful of retained versions, 2 GiB
etcd and logs, headroom - **64 GiB**, and 32 GiB would be the floor.

`local-lvm` has 26 GiB free. A 64 GiB volume does not fit, and thin-provisioning
it onto a disk that also holds Postgres means the database's writes and the
cluster's image pulls compete for the same 119 GiB consumer NVMe. etcd is
fsync-latency-sensitive and Postgres is the thing that must not be slowed.

So:

| on the new 500 GB M.2 | |
|---|---|
| new LVM-thin pool | the whole device |
| k3s VM | 64 GiB |
| LXC 101 rootfs, grown | 16 → 48 GiB |
| reserve | the remainder, for backups and a second node's images |

Growing LXC 101 is not scope creep: it is at 67% with 4.9 GiB free, against a
documented 4.5 GiB after build, and the cluster will not reduce what it holds.

Postgres stays on the original NVMe, alone with Home Assistant, which is the
better outcome for it than sharing with image pulls.

### A VM, not an LXC, for k3s

k3s in an unprivileged LXC needs cgroup and kernel-module concessions, and the
container that would need them is the one next to the container serving real
users. A VM costs about a gigabyte of overhead and buys a failure boundary: a
cluster experiment cannot take down the portal while the portal is still being
served by compose, which is also what makes the cutover reversible.

**RAM for the VM: 4 GiB.** k3s control plane ~0.7, ArgoCD's components ~1.5,
the three app workloads ~1.2 measured in LXC 101 today, OS and headroom. The
host has 9.8 GiB free, so this leaves ~5.5 GiB spare.

**CPU: 2 vCPU**, overcommitted against 4 cores. CPU is the tightest resource on
this box once dbt runs with two threads, and it is worth saying that the cluster
will make dbt runs slower, not faster.

### Postgres stays in LXC 101

The database is the one thing that cannot be rebuilt. Its restore path is tested
and documented. A single-node orchestrator rescheduling it buys nothing: there
is nowhere to reschedule it to.

It is also not what the operator asked for. A push to GitHub should update the
application; the database is not updated by pushes. Moving it would add the only
genuinely dangerous migration in this change for no part of the stated goal.

The cluster reaches it over the LAN. That means Postgres must listen on more
than loopback, which is a real widening - so it is bound to the host-only bridge
and reachable from the cluster VM, never from the wider network, and the
existing requirement that published ports are reachable only from the host still
binds.

### Images: GHCR, tagged by version, built once in CI

The Dockerfile is one file with three consumers. CI builds on release and pushes
`ghcr.io/<owner>/bonuschef:<version>` - one tag per build, never re-pointed,
because a mutable tag means the described state no longer determines what runs.

The version and commit must survive into the image, which the existing
requirement already demands and which the chart then reads back - so "which
version is live" is answerable from the cluster, as it is from the page footer
today.

*Alternative considered:* build on the node with a local registry. Rejected - it
reintroduces the build step a cluster is not supposed to have, and makes a
rollback depend on a build rather than on a pull.

### Secrets: created out of band, referenced by name

Around twenty values, including an AH refresh token, the database password, a
GitHub token, the ntfy topic and the invitation code. The repository already
forbids committed configuration from carrying a working credential.

They are created once from the existing `.env` with `kubectl create secret`, and
the chart references them by name. No sealed-secrets, no SOPS: both put
ciphertext in the repository and a decryption key on the node, which is a key
management problem this deployment does not need to take on for five accounts.

The cost is honest and should be written down: a new secret is a manual step, and
the cluster cannot be rebuilt from the repository alone without it. That is the
trade for never having a credential in git.

### The systemd timer stops managing the portal

Two mechanisms reconciling toward their own idea of "current" is how a deploy
succeeds and is undone ten minutes later. At cutover the timer's scope narrows to
Postgres, or it is retired and Postgres is pinned - decided when the cutover is
done, not before, because until then the timer is what serves users.

### The Funnel moves, the address does not

`tailscale funnel` currently proxies to `127.0.0.1:8501` in LXC 101. After
cutover it proxies to the cluster's portal service. The address people were
given keeps working; it has been shared and cannot be recalled.

## Risks / Trade-offs

- **This makes the stack slower and larger for no user-visible gain.** Stated
  plainly because the proposal's "why" is the operator's preference for the
  tools, which is a legitimate reason and not the same as a performance one.
- **A single node gets k8s' complexity and none of its resilience.** A control
  plane failure is total, as a compose failure is - but there is now a control
  plane that can fail.
- **etcd on consumer NVMe.** Mitigated by moving it to the new device, away from
  Postgres. Worth watching: etcd complains about fsync latency long before it
  fails.
- **Rollback depends on retained images.** 20 GiB of image budget is the
  difference between "roll back" and "rebuild and hope".
- **Two paths exist during the cutover, deliberately.** That is the window the
  "one workload has one manager" requirement is about; it is bounded by the
  cutover task and the compose stack is what gets turned off, not the cluster.
