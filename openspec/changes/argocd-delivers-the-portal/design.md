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

### Storage: the 500 GB M.2 is in, and it changed where things belong

*This decision was written before the disk existed, and two of its premises
turned out to be wrong once measured. Corrected in place, with the numbers,
rather than left to mislead whoever implements it.*

A k3s VM needs an OS, containerd's image store, and its datastore. The images
here are Python with uv, pandas, dbt and Dagster. Measured rather than
estimated: six images sharing a base occupy **13 GiB** of `/var/lib/containerd`
on the compose host, so roughly 2.2 GiB marginal per retained version — and a
GitOps rollback is only real if the previous image is still on disk.

Budget: 8 GiB OS, 20 GiB images (about eight retained versions at the measured
marginal size), 2 GiB datastore and logs, headroom — **64 GiB**, with 32 GiB
the floor.

The pool exists now: LVM-thin `ssd`, **456.3 GiB**, with 300 GiB thin-provisioned
to LXC 101 and **427.7 GiB** actually free.

| on the 500 GB M.2 (`ssd`) | |
|---|---|
| LXC 101 `/var/lib/docker` — Postgres volume lives here | 100 GiB, 1.3 used |
| LXC 101 `/var/lib/containerd` — image store | 100 GiB, 13 used |
| LXC 101 `/mnt/ssd/bonuschef-test` — test data and dumps | 100 GiB, 2.4 used |
| k3s VM | 64 GiB |
| remainder | backups, a second node's images |

**Correction 1: LXC 101's rootfs does not need growing.** This said 16 → 48 GiB
because it was "at 67% with 4.9 GiB free and the cluster will not reduce that".
The pressure was the image store, and the image store moved: the rootfs is now
**1.5 GiB of 16, at 10%**, because `/var/lib/docker` and `/var/lib/containerd`
are volumes on the M.2. Growing it would reserve 32 GiB to hold nothing.

**Correction 2: Postgres is on the M.2, not the NVMe, and that is the right way
round.** This said it would stay on the original NVMe, "which is the better
outcome for it than sharing with image pulls". That was an assumption about
which disk is faster, and it is backwards. Measured on the host, same
filesystem layer, `dd oflag=direct`:

| | NVMe PM991 | SATA 860 EVO |
|---|---|---|
| sequential write | 88.6 MB/s | **461 MB/s** |
| 8k sync writes | 1.0 MB/s | **3.6 MB/s** |
| sequential read | **982 MB/s** | 469 MB/s |

The PM991 is a DRAM-less OEM part. Reads favour it and are largely served from
page cache; writes are what the dbt build, the dlt loads and every commit do.

That inverts the separation argument. Keeping the cluster's datastore away from
Postgres was worth something when they would share a 119 GiB consumer NVMe
under contention; it is worth little now, and buying it would mean putting the
fsync-sensitive thing on the disk that manages **1.0 MB/s of 8k sync writes**.
So the k3s VM goes on the M.2 as well, beside Postgres, and the separation is
dropped deliberately rather than by oversight.

Two things make that comfortable. The pool has 427.7 GiB free and the host sits
at **load 0.36 on four cores**. And single-node k3s uses SQLite through kine by
default, not etcd — so the datastore is far less fsync-brutal than this decision
originally assumed. If the cluster ever grows a second node and real etcd, the
NVMe is free by then and the question can be reopened with numbers.

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

Its storage moved since this was written, but not its home: it is still a
volume in LXC 101, now backed by the M.2 rather than the NVMe, and measurably
better off for it. See the storage decision above. The reasons for leaving it
out of the cluster are unchanged - there is nowhere to reschedule it to, and a
push to GitHub does not update a database.

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
