# Deploy a version, not a working tree

## Why

Nobody can say what is running on the guest right now.

`/opt/bonuschef` is not a git repository. It was populated by rsync from a
laptop, and `docs/deployment.md` already records what that costs: an early
deployment "rsynced a working tree with 33 unpushed commits". The running
stack has no version, no commit, and no way to be asked. Answering "is the
fix live?" means reading source inside a container and comparing it by eye.

The project already cuts semantic versions — v1.0.0 through v1.2.0 exist as
tags and GitHub releases. They are simply not connected to anything. A
release is a tag on GitHub and the deployment is whatever was last copied
over; the two have never had to agree.

Two things break because of that gap, and both have already happened:

The release for v1.3.0 failed. Its verification step runs a hand-picked
subset of nox sessions that omits `lint_sql` — which is the session that
runs `dbt parse` and so produces `target/manifest.json`. Without it the
test suite cannot import the Dagster definitions and dies during
collection. CI passes because CI happens to run `lint_sql` first. Two
gates, written separately, drifted; the release gate was the weaker one,
and it was the one guarding the tag.

`nox -s tests` therefore does not work on a clean checkout. The suite
depends on a build artefact that a different session happens to leave
behind. That ordering is written down nowhere.

## What Changes

A release becomes the unit of deployment.

- The release gate and the CI gate become the same gate, so they cannot
  disagree about what "passing" means.
- `nox -s tests` produces what it needs, instead of inheriting it.
- Images carry the version and commit they were built from.
- The portal shows the version it is running.
- Deploying means checking out a released tag and building it, and the
  documented procedure says so.

## Impact

- Affected specs: `release` (new), `container-runtime`, `deployment-target`
- Affected code: `noxfile.py`, `.github/workflows/release.yml`, `Dockerfile`,
  `docker-compose.yml`, `src/bonuschef/version.py` (new), the portal chrome,
  `docs/deployment.md`

## Out of scope

- Pushing images to a registry. The guest builds from source; a registry
  is a larger decision about where images live and who may pull them.
- Deploying automatically when a release is cut. Deployment stays a
  deliberate act.
- Rewriting the health probes, which were changed recently and work.
