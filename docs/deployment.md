# Deploying bonuschef to a Proxmox guest

Written while doing it, on 2026-09-14, against Proxmox 9.2.2 (kernel 7.0.2-6-pve)
and Debian 13.6. Every figure here was measured on that host rather than estimated.

The point of this document is that the second deployment needs no knowledge held
only by whoever did the first. Where something bit, it says so.

## What you are building

One unprivileged LXC running the four-service compose stack. Not a VM: the stack
idles at 798 MB and a VM's own kernel would cost more than the application.

| | value | why |
|---|---|---|
| VMID / hostname | 101 / `bonuschef` | |
| rootfs | `local-lvm`, 16 GB | 4.5 GB used after build; the database grows slowly |
| cores / memory | 2 / 2048 MB + 1024 MB swap | `DBT_THREADS=2` matches the cores |
| features | `nesting=1` | see **keyctl** below |
| network | `vmbr0`, DHCP | |
| boot | `onboot=1`, `startup=order=2,up=60` | order 2 puts it behind Home Assistant; the 60 s delay stops the two contending during boot |

## Before you start

**Do not use a Proxmox API token for the container creation if you can avoid it.**
Two checks cannot be satisfied by a token at all:

- `keyctl=1` is rejected with *"only allowed for root@pam"*. The check is against
  the literal user, so **no token passes it regardless of `--privsep`** — turning
  privsep off does not help. It turned out not to matter: Docker 29.8.0 runs the
  full stack under `nesting=1` alone, on overlayfs with cgroup v2 and no keyring
  errors. If a future image needs it: `pct set 101 -features nesting=1,keyctl=1`.
- `SDN.Use` on `/sdn/zones/localnetwork/vmbr0` is needed to attach any network
  interface. A privsep token lacks it until granted.

`pveum user token modify root@pam bonuschef --privsep 0` clears the second.
Note the CLI takes *user* and *token* as separate arguments — and quote nothing
with `!` in an interactive shell, or history expansion eats it.

## 1. Guest

```
# template
pveam download local debian-13-standard_13.6-1_amd64.tar.zst

# container, with your SSH key baked in so you never need the host shell
pct create 101 local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst \
  --hostname bonuschef --storage local-lvm --rootfs local-lvm:16 \
  --cores 2 --memory 2048 --swap 1024 --unprivileged 1 \
  --features nesting=1 --net0 name=eth0,bridge=vmbr0,ip=dhcp,firewall=1 \
  --onboot 1 --startup order=2,up=60 --ostype debian \
  --ssh-public-keys ~/.ssh/id_ed25519.pub
pct start 101
```

## 2. Docker

Docker's own apt repository, not Debian's. Verify you got the **plugin**:
`docker compose version` must report v2+, not a `docker-compose` binary.

```
apt-get install -y ca-certificates curl gnupg git rsync
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker
```

`systemctl enable docker` is not optional. Without it every `restart: unless-stopped`
in the compose file is inert and the stack silently never returns from a power cut.
`systemctl is-enabled` only states an intention — it is proven by the reboot in step 6.

## 3. Application

**Clone it. Do not copy it.**

```bash
git clone https://github.com/levyvankempen/bonuschef.git /opt/bonuschef
cd /opt/bonuschef && ./scripts/deploy.sh v1.3.0
```

The first deployment rsynced a working tree — with 33 unpushed commits, as it
turned out — and for months afterwards nothing on the host could say what it was
running. A clone can be asked. `git describe` becomes the version stamped into
the image and shown in the portal footer, so "is the fix live?" is answerable
from the page rather than by reading source inside a container.

`deploy.sh` takes a **tag**, and refuses anything else. A branch names something
different tomorrow while the image stamp claims to describe a fixed thing, which
is the confusion this whole arrangement exists to remove. It also refuses to
rebuild while a run is in flight (§ below), and refuses to start without `.env`.

### One image per version, built once

`deploy.sh` no longer builds during `up`. It calls `scripts/build-image.sh`,
which produces `bonuschef:<version>` and **reuses an image already tagged for
that version** rather than rebuilding it. The compose services then name that
image instead of a build context.

This matters only because there are now two environments. While every host
built its own, nothing compared two builds, and `up -d --build` was fine. Once
a change is supposed to be *watched working* somewhere and then promoted,
"promote the version I watched" needs an artifact — and two builds of one
commit were genuinely not the same bytes. `uv.lock` pins the Python side
exactly via `uv sync --frozen`, but the base image was a floating tag, so a
fortnight's gap bought a different Debian and CPython patch level with nothing
in any diff to show it. The base is now pinned by digest; bumping it is a
commit.

Three consequences to know about:

- **`BONUSCHEF_VERSION` is mandatory.** Compose interpolates at parse time, so
  *every* command fails without it — `ps`, `logs` and `exec` included, none of
  which resolve an image. Use **`./scripts/compose.sh`** instead of
  `docker compose`: it reads the version from the running stack's OCI label and
  hands off. Every command in this document does.
- The version is deliberately **not** written into `.env`. The services read
  `.env` into their environment, so a value there would override the one baked
  into the image, and the portal would report a version it is not running.
- **Each release leaves a 2.6 GB image behind**, and `docker image prune -f`
  removes only *dangling* images, so none of them qualify. Measured: 7.6 GB
  free before the first versioned deploy, 4.0 GB after. `deploy.sh` therefore
  keeps the newest `BONUSCHEF_KEEP_IMAGES` (default 2 — the running one and a
  rollback target) and removes the rest, never touching an image in use.

### Promoting a version

```bash
# build it once. build-image.sh refuses unless HEAD is at the tag, because
# otherwise it would tag an image with a version it did not build.
git fetch --tags && git checkout --detach refs/tags/v1.41.0
./scripts/build-image.sh v1.41.0

# watch it in the test environment (below)
BONUSCHEF_VERSION=v1.41.0 docker compose \
    -f docker-compose.test.yml --env-file .env.test up -d

# then promote the same artifact
./scripts/deploy.sh v1.41.0        # reuses bonuschef:v1.41.0, does not rebuild
```

Deploying a version that was never watched in the test environment is
**allowed**, and deliberately so: an urgent fix must not wait on a test
environment that happens to be broken. Nothing enforces the sequence — the
discipline is yours.

### Deploying automatically

A systemd timer checks for a newer release every minute and deploys it:

```bash
install -m 0755 scripts/auto-deploy.sh /usr/local/bin/bonuschef-autodeploy
cp deploy/systemd/bonuschef-autodeploy.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now bonuschef-autodeploy.timer

systemctl list-timers bonuschef-autodeploy    # when it next runs
journalctl -u bonuschef-autodeploy -n 50      # what it has been doing
```

This is the pull half of GitOps, which is what ArgoCD does for a cluster. A
cluster was considered and rejected: k3s' control plane plus ArgoCD's five
components need roughly as much memory as this guest has in total, and the
repository already carried Kubernetes manifests nobody ran, which were deleted
for the reason now written down as *"a committed deployment path meets the
requirements it is subject to"*.

The runner is installed to `/usr/local/bin`, deliberately outside the
checkout, and `deploy.sh` refreshes it after every successful deploy. Run from
`scripts/` instead, it would be part of what it deploys: a rollback to a
release predating it deletes systemd's `ExecStart` target and auto-deploy stops
for good, because recovering is the one thing it can no longer do. This was
found by rolling the real server back to v1.3.1.

What it will **not** do, and what you give up by not running ArgoCD:

- It does not detect drift. Edit a file on the server and nothing reverts it —
  though the version stamp will mark the checkout `-dirty` and the portal will
  stop calling it a release, so the drift is at least visible.
- It refuses to touch a dirty checkout at all, so debugging on the box is safe
  from it.
- It never rolls backwards. Rolling back is `./scripts/deploy.sh v1.3.0`,
  deliberately, by a person.

A tick that declines to act exits 0. In particular, "a Dagster run is in
flight" is not a failure: that happens several times a day, and a timer that
reported it would be muted within a week and then the real failures would be
invisible too. Genuine deploy failures do mark the unit failed, and show up in
`systemctl --failed`.

To migrate a host that was rsynced, convert it in place rather than moving it —
`.env` is untracked and must survive, and the Docker volumes are not in this
directory at all, so the data is not at risk:

```bash
cd /opt/bonuschef
git init -q && git remote add origin https://github.com/levyvankempen/bonuschef.git
git fetch --tags origin
git reset --hard v1.3.0     # .env is untracked and is left alone
git status --short          # leftovers from the rsync era, now visible
```

Then `.env`: copy `.env.example`, fill every key. Generate a **new**
`POSTGRES_PASSWORD` on the guest rather than reusing the laptop's, and set the
three password keys to the same value. Generate `NTFY_TOPIC` with
`openssl rand -hex 16` — it is a capability URL, so anyone who knows it reads your
notifications. `./scripts/compose.sh config -q` fails while any required key is unset,
which is the point.

## 3b. The test environment

Somewhere to watch a change work before the people who were invited see it.
Same portal, same image, its own database, a copy of production's data, and
**no pipeline**.

### The two rules

**It never holds the Albert Heijn credential.** Not "blank for now" — never.
There is one credential, and refreshing it may rotate the refresh token;
`refresh_tokens` persists the rotated one. Two environments refreshing it would
invalidate each other's, and the symptom is not a broken test environment — it
is production's prices quietly ceasing to update, in whichever environment
refreshed first, which would be production about half the time. There is also
no pipeline here to use a credential with: `docker-compose.test.yml` contains
no `dagster-daemon` and no `dagster-webserver` at all. Absent, not disabled.

**It is never published.** Loopback only, never on the Tailscale Funnel.
Unfinished work is what it holds, along with a copy of production's accounts.

Both rules are in the spec as requirements, and the compose file says why at
the point where somebody would be tempted to undo them.

### Setting it up

It needs real disk. The 500 GB SSD is the intended home, and it is not
provisioned yet — `/dev/sda` is wiped and nothing from it is mounted into the
container. Until it is, the only space available is production's 16 GiB rootfs
with ~6 GiB free, and a 1.1 GB restore plus a 1.1 GB dump beside it is how a
test environment takes production down. So `BONUSCHEF_TEST_DATA_DIR` has **no
default** and the stack refuses to start without it.

On the Proxmox host:

```bash
# a filesystem on the SSD, and a mountpoint into the container
# (this stops CT 101 briefly - production goes down for the restart)
pvesm add dir bulk --path /mnt/bulk     # after formatting /dev/sda
pct set 101 -mp0 /mnt/bulk,mp=/mnt/bulk
```

Then in the container:

```bash
cd /opt/bonuschef
cp .env.test.example .env.test          # fill in; it must NOT get an AH token
mkdir -p /mnt/bulk/bonuschef-test

BONUSCHEF_VERSION=$(git describe --tags --abbrev=0) docker compose \
    -f docker-compose.test.yml --env-file .env.test up -d
```

The portal is then on `127.0.0.1:8502` (production stays on 8501), reachable
over the tailnet or `ssh -L`.

### Getting data into it

```bash
./scripts/copy-to-test.sh
```

`pg_dump` from production — which keeps serving throughout, because the dump
runs in one transaction — then drop-and-restore into the test database, then a
row recording **when the copy was taken**. Repeatable: restoring over an
existing database gives the same result as restoring into an empty one. The
dump files are kept on the SSD, last three by default
(`BONUSCHEF_KEEP_DUMPS`), and deletions are announced.

The copy's age is the copy's age, not the data's. Taking it from the newest row
of some data table would conflate "this copy is a week old" with "production's
pipeline was down when I copied", which read identically and mean different
things. The test portal reports it in its banner.

### What the copy contains

**Production's accounts** — real usernames, real scrypt password hashes, real
saved recipes. Same host, same boundary, not published, so the exposure is not
new; but it is a second place they live, and whoever places this disk should
know rather than find out.

Deliberately not scrubbed. The accounts are what make the copy able to
reproduce a per-account pricing defect, which is most of what the environment
is for.

### Telling the two apart

The test portal shows a sticky banner on every page naming the environment and
how old its copy is. Production shows nothing: an invited person has one
environment and labelling it would be noise on every page they ever see.

The banner is driven by `BONUSCHEF_ENVIRONMENT`, which is unset in production.
Absence means production — the honest reading, since production is the
deployment that sets nothing.

### Watching whether it still works

Optional. Set `BONUSCHEF_TEST_DATABASE_URL` in production's `.env` and the
Beheer page gains a panel: running or not, how old the copy is, what produced
it. Unset, the panel is omitted — a deployment with one environment is not
broken.

One catch before you set it: the URL is resolved from inside production's
container, where `127.0.0.1` is the container's own loopback rather than the
host's, so the test database's published `127.0.0.1:5456` is **not** reachable
as written. Giving it a route means one of:

- `extra_hosts: ["host.docker.internal:host-gateway"]` on production's
  `streamlit` service, then pointing the URL at `host.docker.internal:5456`;
- a shared Docker network that production's `streamlit` and the test
  `postgres` both join — and nothing else, so the reverse direction stays
  impossible;
- running the portal outside Docker, where loopback is the host's.

None is done by default, because each widens production's network for a
convenience. The panel is not part of the delivery path; the copy script and
the banner are.

### When the cluster arrives

`argocd-delivers-the-portal` replaces the *how* and keeps the *what*. Every
requirement here is written about environments rather than mechanisms — its own
database, not published, the artifact that was watched — so two namespaces and
two value files satisfy them exactly as well as two Compose projects.

What changes: the two compose files become one chart with two value files, and
the duplication that `tests/unit/test_the_test_environment.py` currently guards
against goes away. What does not: the credential rule, the publication rule,
one image per version, and the marker.

## 4. Data that cannot be rebuilt

**Stop the app services before restoring. This is the step that bites.**

Every schedule and sensor carries `default_status=RUNNING`, deliberately, so a
fresh host needs nobody to unpause it. That means the github sensor starts loading
within seconds of the first `compose up` and races your restore. Doing it in the
wrong order produced 1,259,047 rows against the source's 1,193,311 — the surplus a
partial duplicate load — with every `CREATE TABLE` failing as "already exists"
while the `COPY`s appended anyway.

```
./scripts/compose.sh up -d postgres                       # postgres only
./scripts/compose.sh stop dagster-daemon dagster-webserver streamlit
```

Dump from the old host — the irreplaceable set is wider than it looks:

| table | why it cannot be rebuilt |
|---|---|
| `ah__store_markdowns` | append-only; AH publishes only the present, so the intraday markdown curve cannot be back-filled |
| `recipes`, `recipe_ingredients` | typed by hand |
| `ah_recipes`, `ah_recipe_ingredients` | adopted from the catalogue |
| `ah_ingredient_products`, `ah_ingredient_aliases`, `ah_ingredient_review` | **hand-confirmed resolutions** — the most expensive human work in the system |
| `github__products` | rebuildable in principle, 1.2 M rows and hours in practice; it is the reference every saving is measured against |
| `_dlt_*`, `public_staging` | dlt's own state; without it dlt reloads rather than continues |

```
pg_dump -U postgres -d postgres --no-owner --no-acl -t 'public.<each>' -t 'public_staging.*' | gzip -9 > data.sql.gz
gunzip -c data.sql.gz | ./scripts/compose.sh exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1
```

`ON_ERROR_STOP=1` turns silent mixing into a stop. Then compare row counts on both
sides table by table — that comparison is the verification, not the absence of errors.

Bring the app services up and run a full `dbt build`. It rebuilds every mart from
the restored sources, which is what establishes nothing else needed migrating.
Measured: 27 s at 2 threads, 106 passing tests.

### The restore has an aftershock: Dagster's own state did not come with it

Migrating the data does not migrate the Dagster instance tables, and nothing tells
you that. A fresh instance has no dynamic partitions, so the github sensor treats
every commit in the history as new and queues a run for each — 43 of them here. The
source merges on `(l, snapshot_at)`, so each is an expensive no-op rather than a
duplicate, but with `max_concurrent_runs: 1` they serialise: the first ran 33 minutes
on two cores and the other 42 waited behind it.

The visible symptom is somewhere else entirely. Pressing **Nu verversen** in the
portal queues a run at position 44 and it does not start for hours, while the page
shows a spinner claiming the store is being scanned.

So after restoring, check the queue before trusting anything on-demand:

```
./scripts/compose.sh exec postgres psql -U postgres -d postgres -Atc \
  "SELECT status, count(*) FROM runs GROUP BY status;"
```

Cancel the backfill runs if the data they would load is already restored — they are
redundant by construction. The partitions stay registered, so the sensor does not
re-queue them.

## 5. The AH credential

The refresh token **rotates on use**, so two stacks running at once fight over it
and both lose. Stop the old stack *first*, then move the live token file:

```
docker run --rm -v bonuschef_dagster_home:/dh alpine cat /dh/ah_tokens.json > tok.json
# ... transfer ...
docker run --rm -v bonuschef_dagster_home:/dh -v /root:/src:ro alpine \
  sh -c 'cp /src/tok.json /dh/ah_tokens.json && chmod 600 /dh/ah_tokens.json'
```

Shred both staging copies. `.env`'s `AH_REFRESH_TOKEN` is only a bootstrap seed;
the file on the volume is the live credential. If it is lost, the only recovery is
an interactive browser login — it cannot be recovered unattended.

### Copying source into a running container does not update the asset graph

Dagster builds its asset graph from `src/bonuschef/sql/target/manifest.json`,
parsed when the code location loads. `docker compose cp` of the source tree does
not touch it, and `target/` is excluded from rsync because it is build output.

The symptom is a job failing on a dependency that no longer exists:

```
DagsterInvariantViolationError: Asset "marts/dim_recipe" was yielded before its
dependency "stg_ah__pool_recipes"
```

That edge had been removed from the model an hour earlier. dbt was running fine
against the new SQL; Dagster was orchestrating the old graph.

**Every container has its own copy**, and the daemon is the one that executes
jobs. Running `dbt build` inside `dagster-webserver` refreshes only that one - the
job then fails in exactly the same way it did before, which reads as the fix not
working rather than as having been applied to the wrong container.

So after changing any model's `ref()`s, rebuild:

```
./scripts/build-image.sh "$(git describe --tags --abbrev=0)"
./scripts/compose.sh up -d
```

The Dockerfile runs `dbt deps` and `dbt parse` at build time, so this regenerates
the manifest once and every container gets the same one. Verify rather than
assume, in **both** long-running containers:

```
for c in dagster-daemon dagster-webserver; do
  ./scripts/compose.sh exec $c python -c "import json; m=json.load(open('/app/src/bonuschef/sql/target/manifest.json')); \
    print('$c', [n.split('.')[-1] for n in m['nodes']['model.bonuschef.dim_recipe']['depends_on']['nodes']])"
done
```

### Rebuilding while a run is in flight wedges the queue for an hour

Restarting a service kills the run worker's process. Dagster does not
notice: the run stays STARTED, and with `max_concurrent_runs: 1` it holds the
only slot. Everything afterwards queues behind a run that will never finish -
including the credential heartbeat.

`run_monitoring` does clean it up, but only at `max_runtime_seconds`, which is
3600. An hour of a wedged queue looks exactly like a broken portal: corrections
appear not to save, the refresh button does nothing.

Check before rebuilding:

```
./scripts/compose.sh exec postgres psql -U postgres -d postgres -Atc \
  "SELECT status, count(*) FROM runs WHERE status IN ('STARTED','QUEUED') GROUP BY 1;"
```

If something is in flight, wait for it - the clearance scrape takes under a
minute. If one is already orphaned, terminate it through GraphQL
(`terminateRun` with `MARK_AS_CANCELED_IMMEDIATELY`) rather than waiting out the
hour.

## 6. Prove it, rather than configuring it

**Reboot the guest** and confirm the stack returns with nobody logging in. Measured:
all four containers up and healthy 11 seconds after start.

**Break each service and watch its probe fail.** A probe that has never been
observed to fail is a belief, not a check. Of the three here, two were lying:

- **Dagster webserver** — `/server_info` answered from static version strings and
  passed while every code location was dead. Replacing it with `repositoriesOrError`
  was *also* wrong: a broken definitions module still answers `RepositoryConnection`,
  just with `nodes: []`, and a `__typename` check waves that through. It stayed green
  through five probes. The probe now requires a served repository and no `PythonError`
  location entry. **Generalise this:** a well-formed but empty response is what a
  broken service returns.
- **Postgres** — sound. `pg_isready` exits 0 live, 2 with no server; a genuine stop
  makes the container exit and self-heal through the restart policy.
- **Streamlit** — a known gap, accepted deliberately. With a `raise` in `app.py`,
  `/_stcore/health` still returns 200 and `/` still serves its shell, because
  Streamlit runs the script per browser session. Not strengthened, because importing
  the page modules every 30 s would pull pandas into a fresh interpreter on a 2 GB
  guest. The AppTest suite is the real guard, and a broken portal announces itself.

**Reboot the Proxmox host** and confirm both guests return. This is the only
thing that proves `onboot`; a guest reboot proves Docker comes back *inside* the
guest, which is a different mechanism.

The API answers `HTTP 200 {"data":null}` at once and then shuts guests down
gracefully, so uptime does not move for a minute or two. Watch for uptime to
reset, not for the call to return — otherwise it reads as the reboot silently
failing, and issuing it a second time is how you reboot twice.

Measured here: guests returned unaided, CT101 within 5s via `startup=order=2`,
and the Home Assistant VM about 50s later since it has `onboot=1` but no startup
order. The stack was healthy about a minute after the guest booted.

## 7. Access

Nothing authenticates its callers and the Dagster UI can launch and kill jobs, so
all three ports bind `127.0.0.1` inside the guest. Verify from another LAN machine
that 3000, 8501 and 5455 are **refused**, and that nothing is forwarded on the router.

Reach them over Tailscale (`tailscale up`, then `http://bonuschef:8501`) or
`ssh -L 8501:127.0.0.1:8501 root@<guest>`.

### Sharing the portal with people who are not on the tailnet

The portal — and **only** the portal — can be published on a public HTTPS
address, so a friend opens a link and installs nothing. Dagster must never be
published this way: it has no authentication and can start and kill pipeline
runs, and the loopback binding above is the only thing in front of it.

Funnel has to be enabled for the tailnet once, in the admin console. The CLI
prints the exact link, and waits:

```
tailscale funnel --bg 8501          # prints a login.tailscale.com/f/funnel link
                                    # if the tailnet has not enabled it yet
```

Enable it there, re-run the same command, and the address is
`https://bonuschef.<your-tailnet>.ts.net`.

Three things to check straight after, because publishing the portal must not
publish anything else:

```
tailscale funnel status             # 8501 only — no 3000, no 5455
./scripts/compose.sh port dagster-webserver 3000   # still 127.0.0.1:3000
./scripts/compose.sh port postgres 5432            # still 127.0.0.1:5455
```

Withdraw it with one command; local and tailnet access are unaffected:

```
tailscale funnel --https=443 off
```

The address is public, though not indexed. The sign-in wall is what stands in
front of it, so it is load-bearing in a way it is not on the tailnet: sign-in
throttling (five failures per username inside fifteen minutes, recorded in
Postgres so a restart does not clear it) is a prerequisite for publishing, not
a later improvement. `BONUSCHEF_INVITE_CODE` is what lets a friend register;
rotating it in `.env` revokes for everyone at once and is the only revocation
there is.

### One growth path this cannot see

`LOAD__DELETE_COMPLETED_JOBS=true` stops dlt keeping a copy of every completed
load. It is dlt's own configuration, read from the environment, so if dlt ever
renames or drops the key the setting silently stops applying and the growth
resumes — under `/var/dlt` in the container's writable layer, where `du` on the
project directory and `docker volume ls` both miss it.

There is no offline way to assert a third-party config key is still honoured.
If disk use climbs without the tables growing, look there first:

```
./scripts/compose.sh exec dagster-daemon du -sh /var/dlt 2>/dev/null
```

## 8. Recoverability

Nightly `vzdump` of the guest to `local` at 03:00, `keep-last=3`, snapshot mode,
zstd. 03:00 is before the 03:30 credential heartbeat and clear of the 11:00–20:00
clearance window. One artifact captures the database volume, the credential and the
configuration together.

**Restore it once to a scratch VMID and confirm it produces a working guest.** An
unverified backup is a belief.

What is recoverable from where:

| | source |
|---|---|
| application code | the repository |
| product prices, bonus feed | re-derivable from GitHub and AH, slowly |
| markdown curve, hand-typed recipes, confirmed resolutions | **the backup only** |
| AH credential | the backup, or a browser. Never unattended |

### The backup, and the one thing a restore still has not proven

Restore-tested on 2026-09-20, against that morning's 03:29 GB archive.

The nightly job exists and runs — this document previously implied otherwise,
and it was wrong. It is configured in Proxmox rather than in this repository,
which is why nothing here found it:

```
scheduled   03:00 daily, vmid 101, enabled, storage local
on disk     2026-09-18 3.91G · 2026-09-19 3.92G · 2026-09-20 3.29G
```

**The drill, and how to repeat it.** Restore to a scratch VMID with the
network link DOWN. That part is not optional: a clone of this stack has
Dagster schedules at `default_status=RUNNING`, so the moment it boots with a
live link it starts scraping AH on the same credential and firing ntfy alerts
from a machine you have forgotten exists.

```bash
pct restore 999 /var/lib/vz/dump/vzdump-lxc-101-<date>.tar.zst \
    --storage local-lvm --hostname bonuschef-restoretest \
    --net0 name=eth0,bridge=vmbr0,link_down=1,type=veth
pct start 999
# postgres only, so the application image - and therefore the version - is
# not needed; the placeholder just gets the file to parse.
pct exec 999 -- env BONUSCHEF_VERSION=verify-only \
    docker compose -f /opt/bonuschef/docker-compose.yml up -d postgres
pct exec 999 -- docker exec "$(pct exec 999 -- docker ps -q -f label=com.docker.compose.service=postgres)" psql -U postgres -At -c \
    "SELECT count(*) FROM public.ah__store_markdowns"   # compare against 101
pct destroy 999 --force
```

Check headroom first. The archive is ~3.3 GB and the rootfs ~8 GB used of a
16 GB volume; `local` and `local-lvm` each had ~23 GB free when this was run.
Filling the host would take the production guest down with it.

**What the 2026-09-20 run proved, and what it did not.** The archive restores:
`vzrestore` completed OK and produced a 16 GB rootfs on `local-lvm`, which was
then destroyed and the space returned. Container 101 was untouched throughout.

It did **not** verify the data inside. That needs `pct exec` into the started
clone, which needs a shell on the Proxmox host — the API alone cannot do it.
So what is settled today is that the backup is restorable, not that the
database within it is complete. The row-count comparison above is the step
that would close that, and it has not been run.

### What grows, and what bounds it

| | bounded by |
| --- | --- |
| schedule and sensor ticks | `dagster.yaml` retention, 30 days |
| runs and their event logs | the `prune_run_history` job, Sunday 03:15, 90 days |
| container logs | the json-file driver's max-size/max-file |
| clearance history | nothing, deliberately — it is the product |

Dagster OSS has no retention setting for `event_logs`, which is why a job does
it rather than configuration. Deleting a run deletes its event logs with it;
reaching into the table directly would work until a schema change made it not.

The failure worth recognising is not a full disk. It is `daily_refresh` failing
to spill its temp files while the smaller hourly scrape keeps working — which
reads as "the recipe prices seem stuck".

## 9. Cutover

Stop the old stack so two schedulers are not scraping the same store and rotating
the same credential against each other. Then confirm over the following days that
the schedules fire: clearance hourly 11:00–20:00, the daily refresh at 17:30, the
credential heartbeat at 03:30 and 15:30 — and that `fct_store_clearance_history`
starts accumulating the intraday curve.
