## Why

A push to GitHub should update the running application, declaratively, with the
cluster reconciling toward what the repository says. ArgoCD and Helm are the
operator's chosen tools for that.

The present path already does the pull half of GitOps - a systemd timer that
deploys the newest tag every ten minutes - and it works. This replaces it for
the application workloads with a cluster that reconciles continuously and shows
what it is converging on.

The host now has room: 15.5 GiB of RAM with 6 GiB allocated, where before the
upgrade 8 GiB had 6 allocated and a k3s control plane could not be fitted
without squeezing Home Assistant. That was the binding constraint and it is
gone.

Storage is now the binding one, and this change is **blocked on the 500 GB M.2**
being installed. See design.md.

## What Changes

Three things are needed that "install ArgoCD" does not imply, and they are the
bulk of the work:

- **Images must be published.** Kubernetes pulls images; it never builds them.
  Three services currently build from one Dockerfile on the box itself, and
  nothing in CI publishes anywhere. The release workflow SHALL build and push to
  GHCR, tagged with the version, and the chart SHALL reference those tags. The
  repository is public, so GHCR is free and ArgoCD needs no credential to read
  the repo either.
- **Secrets cannot be in the chart.** The stack needs around twenty values
  including an AH refresh token, the database password and a GitHub token. The
  repository already forbids committed configuration carrying a working
  credential. They SHALL be created in the cluster out of band from the existing
  `.env`, and the chart SHALL reference them by name only.
- **Two deployment paths SHALL NOT manage one workload.** Once ArgoCD serves the
  portal, the systemd timer stops managing it. Both reconciling toward different
  ideas of "current" is how a rollback becomes a fight.

And the deliberate exclusions:

- **Postgres stays out of the cluster**, in LXC 101 where it is today. Its data
  is the one thing that cannot be rebuilt, its restore path is tested and
  written down, and a single-node orchestrator rescheduling a database buys
  nothing. The cluster connects to it over the LAN.
- **Dagster's UI and ArgoCD's UI are not published.** Neither authenticates, and
  Dagster can start and terminate pipeline runs. The portal remains the only
  interface on the internet.

## Capabilities

### Modified Capabilities

- `container-runtime`: a cluster is a committed deployment path and is therefore
  subject to every guarantee the compose stack is - recovery without an
  operator, bounded logs, health that reflects whether a service can work,
  configuration from the repository, no credential in committed configuration,
  and an image that carries the version it was built from. Adds that the
  application's desired state lives in the repository and the cluster
  reconciles toward it, and that one workload has one manager.
- `deployment-target`: the portal may be served from the cluster rather than
  from compose, with publication rules unchanged and extended to the two new
  unauthenticated interfaces a cluster brings.

## Impact

- `.github/workflows/` - build and push three image tags to GHCR on release.
- `deploy/helm/bonuschef/` - new chart: Dagster webserver, Dagster daemon,
  Streamlit, their config, health probes and log limits.
- `deploy/argocd/` - the Application manifest pointing at the chart.
- `docs/deployment.md` - the cluster path, what it replaces, and how to get back
  to compose.
- `scripts/deploy.sh`, `scripts/auto-deploy.sh`, `deploy/systemd/` - scope
  narrowed to Postgres, or retired, once the cluster serves traffic.
- Proxmox: a new VM for k3s, and disk growth for LXC 101, both on the new M.2.
- No change to the pipeline, the marts, the portal's code, or the database.
