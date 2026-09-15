# Design

## The gate

`release.yml` stops naming sessions and runs `uvx nox`, which runs the
project's default session list from `noxfile.py`. CI does the same. The
list lives in one place, so a session added to it is picked up by both
without anyone remembering to edit a second file.

CI keeps its sessions as separate steps, because a named step that goes
red tells you which check failed without opening a log. That is a
presentation difference over the same list, not a second definition of
passing.

## The manifest

`nox -s tests` currently fails on a clean checkout: the suite imports the
Dagster definitions, which need `target/manifest.json`, which only
`lint_sql` produces. Rather than documenting an order, both sessions call
a shared helper that runs `dbt deps` and `dbt parse`. `dbt parse` needs no
database — it resolves refs and writes the manifest — so this keeps the
suite network-free and DB-free.

Making it idempotent matters more than making it fast: any session may run
first, and running it twice must be harmless.

## What the version is

A build arg, from `git describe --tags --always --dirty`:

| checkout                      | reports                      |
| ----------------------------- | ---------------------------- |
| at tag v1.3.0                 | `v1.3.0`                     |
| 5 commits past v1.3.0         | `v1.3.0-5-gabc1234`          |
| with uncommitted changes      | `v1.3.0-5-gabc1234-dirty`    |
| no git (tarball, CI archive)  | falls back to package version|

`git describe` is the whole reason this design satisfies "an image built
from a modified tree says so". A version read from `pyproject.toml` cannot
distinguish a release from a laptop three commits past it with unsaved
edits, which is precisely the failure this change exists to prevent.

The value reaches a running container two ways, because two different
people ask the question:

- `ENV BONUSCHEF_VERSION`, for code and for `docker compose exec`
- OCI labels (`org.opencontainers.image.version`, `.revision`), for
  `docker inspect` without starting anything

## Reading it at runtime

`bonuschef.version.get_version()` resolves in order: the environment
variable, then the installed package's metadata, then `"unknown"`. The
fallback chain means the portal renders a version outside Docker too,
where the build arg was never set.

It returns a string and never raises. A version banner that can take the
page down with it is worse than no banner.

## Deploying

The guest becomes a git checkout. `git init` in place, add the remote,
fetch, `reset --hard` to the tag:

- `.env` is untracked, so it survives, which is the one thing on that host
  that cannot be recreated from the repository
- Docker volumes are not in the directory at all, so data is untouched
- leftover files from the rsync era stay visible in `git status` rather
  than being silently deleted

Deploying is then `git fetch --tags && git checkout <tag> && docker compose
up -d --build`, wrapped in `scripts/deploy.sh` so the sequence is one
command and the ordering lessons already in `docs/deployment.md` — never
rebuild with a run in flight — are enforced rather than remembered.

The script refuses to deploy a ref that is not a tag. Deploying a branch
is how you get back to not knowing what is running.

## What this does not do

The guest still builds its own images. Pushing to a registry would make
deployment a pull rather than a build, but it raises questions about where
images live and who may pull them that this change does not need to answer
to make a version knowable.

Nothing deploys automatically when a release is cut.
