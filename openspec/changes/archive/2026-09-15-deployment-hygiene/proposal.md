## Why

Two things on disk contradict what the specs say this system does.

**`k8s/` is a tracked path to a stack that violates four binding requirements.** Its services are `NodePort`, publishing both web UIs on every node interface — against the requirement that nothing answers on a routable interface, which exists because neither UI authenticates its callers and the Dagster one can launch and kill jobs. Its `secret.yaml` commits working credentials (`cG9zdGdyZXM=` is `postgres`). Its webserver probe is `/server_info`, the one already documented as reporting healthy for hours while every code location was dead. And its `livenessProbe`s restart a service for failing a probe, which the container-runtime spec deliberately rejects: a cascade of restarts hides where the fault is.

Nothing references it. The deployment is docker compose on a Proxmox guest, documented end to end in `docs/deployment.md`. Two archived changes call `k8s/` "not the deployment path" — but no binding spec carves it out, so it currently reads as a supported deployment that breaks four rules.

**dlt keeps every completed load package forever, where nothing will find it.** `delete_completed_jobs` defaults to false, so each finished package is moved to `load/loaded/` and kept, data files included. Running as root, dlt's data directory resolves to `/var/dlt` — inside the container's writable layer, not a volume. It is invisible to `du /opt/bonuschef`, to `docker volume ls`, and to the nightly backup. The github asset compounds it by naming its pipeline per commit SHA, so each backfill leaves a permanent directory behind.

## What Changes

- `k8s/` is deleted. It is recoverable from git history if a Kubernetes deployment is ever wanted, and rebuilding it from the current specs would be better than resurrecting manifests that predate them.
- dlt stops retaining completed load packages, so the disk cost of a load is the data it loaded rather than the data plus a copy.

## Capabilities

### Modified Capabilities
- `container-runtime`: unattended running does not accumulate hidden state on the host disk.

## Impact

- `k8s/` — deleted.
- `docker-compose.yml` — one environment variable on the two services that run dlt.
- No change to any pipeline, mart or page.
