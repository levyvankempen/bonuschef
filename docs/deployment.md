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

Copy the repository to `/opt/bonuschef` (clone once the branch is pushed; the first
deployment rsynced a working tree with 33 unpushed commits).

**Exclude `.nox`.** The first rsync copied 3.3 GB of nox virtualenvs before anyone
noticed. Also exclude `.venv`, `__pycache__`, `.idea`, `.tmp_dagster_home_*`,
`src/bonuschef/sql/target`, `src/bonuschef/sql/dbt_packages`.

Then `.env`: copy `.env.example`, fill every key. Generate a **new**
`POSTGRES_PASSWORD` on the guest rather than reusing the laptop's, and set the
three password keys to the same value. Generate `NTFY_TOPIC` with
`openssl rand -hex 16` — it is a capability URL, so anyone who knows it reads your
notifications. `docker compose config -q` fails while any required key is unset,
which is the point.

## 4. Data that cannot be rebuilt

**Stop the app services before restoring. This is the step that bites.**

Every schedule and sensor carries `default_status=RUNNING`, deliberately, so a
fresh host needs nobody to unpause it. That means the github sensor starts loading
within seconds of the first `compose up` and races your restore. Doing it in the
wrong order produced 1,259,047 rows against the source's 1,193,311 — the surplus a
partial duplicate load — with every `CREATE TABLE` failing as "already exists"
while the `COPY`s appended anyway.

```
docker compose up -d postgres                       # postgres only
docker compose stop dagster-daemon dagster-webserver streamlit
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
gunzip -c data.sql.gz | docker compose exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1
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
docker exec pg_bonuschef psql -U postgres -d postgres -Atc \
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
docker compose up -d --build
```

The Dockerfile runs `dbt deps` and `dbt parse` at build time, so this regenerates
the manifest once and every container gets the same one. Verify rather than
assume, in **both** long-running containers:

```
for c in dagster_daemon dagster_webserver; do
  docker exec $c python -c "import json; m=json.load(open('/app/src/bonuschef/sql/target/manifest.json')); \
    print('$c', [n.split('.')[-1] for n in m['nodes']['model.bonuschef.dim_recipe']['depends_on']['nodes']])"
done
```

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

**Reboot the Proxmox host** and confirm both guests return.

## 7. Access

Nothing authenticates its callers and the Dagster UI can launch and kill jobs, so
all three ports bind `127.0.0.1` inside the guest. Verify from another LAN machine
that 3000, 8501 and 5455 are **refused**, and that nothing is forwarded on the router.

Reach them over Tailscale (`tailscale up`, then `http://bonuschef:8501`) or
`ssh -L 8501:127.0.0.1:8501 root@<guest>`.

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

## 9. Cutover

Stop the old stack so two schedulers are not scraping the same store and rotating
the same credential against each other. Then confirm over the following days that
the schedules fire: clearance hourly 11:00–20:00, the daily refresh at 17:30, the
credential heartbeat at 03:30 and 15:30 — and that `fct_store_clearance_history`
starts accumulating the intraday curve.
