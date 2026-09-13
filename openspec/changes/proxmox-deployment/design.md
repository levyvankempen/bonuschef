## Context

See `proposal.md` — Why. Measured on the node and on the running stack, not assumed:

| | |
|---|---|
| Node | Proxmox 9.2.2, single node `proxmox`, i5-7500T, **4 cores**, **8.2 GB RAM** |
| Free RAM | **1.4 GB** (6.2 GB in use) |
| Existing guest | VM 100 `haos-18.2`: 2 cores, 4 GB fixed, **balloon disabled**, actually using 3.95 GB |
| Storage | `local-lvm` 39.7 GB free (lvmthin, images), `local` 34.9 GB free (dir, backups/templates/ISOs) |
| Network | `vmbr0`, 192.168.1.240/24, gateway 192.168.1.1 |
| Swap | 8.2 GB, currently unused |
| Next free VMID | 101 |
| Repos | no-subscription |

Stack footprint, measured after exercising: **798 MB** resident — `dagster_daemon` 328 MB, `pg_bonuschef` 251 MB, `dagster_webserver` 151 MB, `streamlit_portal` 46 MB (understated; budget ~200 MB with a live browser session, so ~950 MB realistic). This is down from 1.74 GB: each service was started through `uv run`, which resolves the environment and then lingers as a parent process costing 177-189 MB per container. The image is 1.73 GB, shared across all three application services. A full `dbt build` spills ~2.8 GB to Postgres temp files (disk, not RAM) and pushes Postgres RSS to roughly 611 MB.

## Goals / Non-Goals

**Goals:**

- Put the stack somewhere it actually stays running, since that is what keeps the AH credential alive.
- Size it from measurements, and stop rather than improvise when they do not fit.
- Make the second deployment as reproducible as the first.

**Non-Goals:**

- Kubernetes. The `k8s/` manifests exist but assume a locally built image with `imagePullPolicy: Never`, and adding a control plane to a node with 1.4 GB free is the opposite of the problem being solved.
- Exposing anything to the internet. Neither UI authenticates, and the Dagster one can launch and kill jobs.
- Migrating Home Assistant, touching its configuration, or changing its memory without an explicit decision. It is the household's, not this project's.
- CI/CD to the box. `git pull` plus one command is proportionate for a single-user app, and a registry would add an account, credentials and a build pipeline to save a rebuild that takes minutes.

## Decisions

**LXC, not a VM — which reverses my earlier advice, because the measurements changed it.**
I previously recommended a Debian VM over an LXC container, on the grounds that Docker-in-LXC needs `nesting=1` and `keyctl=1` and that learning one thing at a time was worth the overhead. At 1.4 GB free that trade no longer holds: a VM carries its own kernel and page cache, costing roughly 400–500 MB that an LXC does not, and that is a third of the entire remaining headroom. The nesting flags are two checkboxes set once at creation. When memory is the binding constraint, the simpler-to-explain option is the wrong one.

**The shortfall was closed by removing waste, not by buying capacity.**
The original 1.74 GB against 1.4 GB free was a genuine blocker. But a third of that footprint was three `uv run` wrapper processes doing nothing after startup; calling the venv binaries directly costs nothing and returns ~550 MB. Sizing Dagster's sensor and schedule workers to the instigators that actually exist returns more. At 798 MB the stack fits with roughly 400 MB spare, so no RAM purchase is needed — though the margin is thin enough that an LXC remains the right guest and the numbers below stay tied to measurements. For the record, had it not fit, the paths were: Deploying anyway means either Postgres swapping — on a box whose entire value is an always-on database — or the kernel reclaiming from Home Assistant, which is using every megabyte it holds. There are three honest paths and each has a stated cost:

1. **Add RAM.** The i5-7500T platform takes two DDR4 SODIMMs, commonly to 32 GB. This ends the constraint permanently for the price of one module and is the only option with headroom for growth.
2. **Reclaim from Home Assistant.** Enabling ballooning with a floor below 4 GB lets the host take back what HA is not actively using — but it is actively using 3.95 GB of its 4 GB, so this degrades it rather than finding slack.
3. **Run degraded.** LXC plus a tuned-down Postgres `shared_buffers`, accepting swap during builds. Workable, and the dbt work now takes 10 s rather than 17 s, but it puts the database on swap precisely when it is busiest.

None was needed. The specification still requires capacity to be checked against measurement before provisioning, because the next thing added to this host will face the same question.

**Sizing: 2 cores, 1.5 GB, 24 GB disk.**
Two cores because the node has four and Home Assistant holds two; dbt's measured ceiling is CPU and `DBT_THREADS` already defaults to 2 for exactly this host. 1.5 GB is the measured 798 MB plus a live browser session and the page cache Postgres wants, inside the 1.4 GB free with the LXC's own overhead counted. 24 GB covers the 1.73 GB image, the database — currently 1.19 M rows in `fct_products` at 157 MB plus indexes — and years of markdown history, against 39.7 GB free on `local-lvm`.

**Access over Tailscale, with SSH port-forwarding as the fallback.**
Every published port binds to loopback by decision of the `container-runtime` capability, so reaching the portal from a phone needs an overlay network or a tunnel, not a firewall hole. Tailscale on the host gives the phone a route without exposing anything; `ssh -L` needs nothing installed and is the fallback while Tailscale is being set up. Rejected: publishing on the LAN, which the container-runtime spec forbids for good reason; and a reverse proxy with authentication, which is real work to protect a service only one person wants to reach.

**Backups are `vzdump` on a schedule, not a script.**
One nightly snapshot of the guest captures the database volume, the `dagster_home` volume holding the AH credential, and the configuration, in one artifact the platform knows how to restore. A `pg_dump` cron would cover only the database and would need its own retention, monitoring and restore procedure. The spec's requirement that a restore has actually been confirmed matters more than the schedule: an unverified backup is a belief.

**The data migration is `pg_dump` once, not a re-scrape.**
`fct_products` rebuilds from source tables, but `ah__store_markdowns` is append-only and irreplaceable — it holds the intraday markdown curve, which is the point of the project and cannot be back-filled because AH publishes only the present. Same for `public.recipes` and `recipe_ingredients`, which were typed by hand. Those three, plus the token file, are the entire set of things a rebuild cannot produce.

**`systemctl enable docker` is a requirement, not a note.**
Every `restart: unless-stopped` in `docker-compose.yml` is inert without it, and the failure mode is silent: the stack simply never comes back after a power cut, and the credential dies again some weeks later. The specification requires the automatic-start path to be exercised rather than configured, because the difference is only visible on a reboot nobody plans.

## Risks / Trade-offs

- **Docker-in-LXC is less isolated than a VM** and an unprivileged container with nesting has known sharp edges around storage drivers and `overlayfs`. → Acceptable for a single-user hobby workload on a trusted LAN, and Proxmox 9.2 handles the common cases. The escape hatch is converting to a VM later, which costs a re-provision and the RAM this decision is trying to save.
- **One node, one disk, no redundancy.** A disk failure loses the guest and the backups, since both live on the same machine. → Proportionate for the workload, but it means "backed up" here means "recoverable from an operator mistake", not "survives hardware loss". Worth stating plainly rather than implying more.
- **The stack shares a host with home automation**, which is the more important service. A runaway dbt build competing for four cores will make Home Assistant sluggish. → `DBT_THREADS=2` and the serialised run coordinator bound it; the daily rebuild is about ten seconds of real work.
- **Tailscale introduces a dependency on a third party** for routine access. → `ssh -L` works without it and needs nothing installed, so the dependency is a convenience rather than a requirement.

## Migration Plan

1. **Resolve capacity first.** Nothing below is worth doing on a host that will swap.
2. Create the LXC on `local-lvm` from a Debian template, with nesting and keyctl enabled and start-on-boot set.
3. Install Docker; `systemctl enable docker`; verify by rebooting the guest and confirming the stack returns unaided.
4. Clone the repository, copy `.env.example` to `.env`, and fill it — including a `POSTGRES_PASSWORD`, and `NTFY_TOPIC` if alerting is wanted.
5. `docker compose up -d --build`.
6. Restore the database from a `pg_dump` taken on the laptop, then bootstrap the AH credential with an interactive login, since it cannot be moved without one.
7. Schedule a nightly `vzdump`, then restore it once to a scratch VMID to confirm the backup is real.
8. Set up access, then stop the laptop stack so two schedulers are not scraping the same store and rotating the same credential against each other.

## Open Questions

- Which capacity path is taken is the operator's decision and is deliberately left open; it changes the sizing constants but not the specification or the task breakdown.
