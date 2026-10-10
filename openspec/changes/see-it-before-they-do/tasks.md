## 1. One image per version, so promotion means something

- [x] 1.1 Pin the Dockerfile base by digest: replace the floating
  `ghcr.io/astral-sh/uv:python3.12-bookworm` with `…@sha256:<digest>`, resolved
  once and committed, with a comment saying why a floating base makes two builds
  of one commit different artifacts. Test: a check that reads the Dockerfile and
  fails on a `FROM` without a digest, so the pin cannot be lost in a later edit.
- [x] 1.2 Add `scripts/build-image.sh <tag>`: verifies the tag exists, builds
  from it, and tags the result `bonuschef:<version>`. Refuses a tag that is not a
  tag, as `deploy.sh` already does for the same reason. Test: the refusal path,
  against a scratch repository.
- [x] 1.3 Change `docker-compose.yml` from `build:` to
  `image: bonuschef:${BONUSCHEF_VERSION:?}`, so a stack cannot start without
  naming a version. Test: parse the compose file and assert no service carries a
  `build:` key, with the reason in the failure message.
- [x] 1.4 Change `scripts/deploy.sh` to build the image via 1.2 and then
  `up -d` without `--build`, and to reuse an existing `bonuschef:<version>`
  rather than rebuilding it - which is what makes promotion run the watched
  artifact. Test: that deploy no longer passes `--build`, and that it skips the
  build when the tag is already present.

## 2. Let two stacks share one host

- [x] 2.1 Remove the four hardcoded `container_name` keys and let Compose derive
  names from the project. Test: assert no service declares `container_name`,
  naming the collision as the reason; and a guard that every place in the repo
  which referenced a container by its literal name (`pg_bonuschef`,
  `dagster_webserver`, `streamlit_portal`, `dagster_daemon`) has been updated -
  `docs/`, `scripts/`, and the autodeploy runner.
- [x] 2.2 Make every published port an environment variable with production's
  current value as the default, so the test stack can move them without a second
  copy of the list. Test: assert each `ports:` entry is a variable with a
  default, and that the defaults equal today's ports so production is unchanged.
- [x] 2.3 Set `COMPOSE_PROJECT_NAME` explicitly for production, rather than
  letting it come from the directory name - the directory is `/opt/bonuschef` on
  the host and the repository name locally, and the volume names follow it. Test:
  that the production project name is pinned somewhere committed.

## 3. The test stack

- [x] 3.1 Add `docker-compose.test.yml` as an override: its own project name, its
  own ports, its own named volumes, and `BONUSCHEF_ENVIRONMENT=test`.
- [x] 3.2 Omit `dagster-daemon` from it entirely, with a comment stating the rule
  and its reason - a rotated refresh token invalidates production's. Test: parse
  the test compose file and assert the daemon is absent, and that the assertion
  fails for a daemon that is merely present with no schedules.
- [x] 3.3 Add `.env.test.example` carrying no `AH_REFRESH_TOKEN` and its own
  `POSTGRES_PASSWORD`. Test: assert the example file names no retailer credential
  and that the test stack's environment does not reference one; assert the two
  example env files do not share a Postgres password default.
- [x] 3.4 Place the test Postgres volume on the SSD by bind-mounting a path
  under the new disk's mount point, and document the mount. Test: assert the test
  database's volume resolves outside production's data path, so a wrong edit
  cannot point them at one directory.
- [x] 3.5 Make a test stack unable to reach production's database: it carries its
  own `POSTGRES_HOST` pointing at its own service, and the production database's
  port is not published to it. Test: assert the test stack's database URL names
  its own service, and that production's Postgres stays bound to `127.0.0.1`.

## 4. The copy

- [x] 4.1 Add `scripts/copy-to-test.sh`: `pg_dump` from the production container
  to a timestamped file on the SSD, `pg_restore` into the test database, no
  production downtime. Refuses to run if the target is production. Test: the
  refusal, and the argument handling, against a scratch directory - no database.
- [x] 4.2 Write the copy's timestamp into a one-row table in the test database as
  the last step of the restore, so the age is the copy's age and not the data's.
  Test: the DDL is covered by the portal's own schema check; the reader returns
  the stored timestamp rather than a max over any data table.
- [x] 4.3 Make the copy idempotent: restoring over an existing database gives the
  same result as restoring into an empty one. Test: that the script drops and
  recreates rather than restoring into live tables.
- [x] 4.4 Keep the last N dump files and delete older ones, so the SSD does not
  fill with 1.1 GB files. Test: the retention arithmetic, with a list of names.

## 5. Saying which environment this is

- [x] 5.1 Add `BONUSCHEF_ENVIRONMENT` to `bonuschef/version.py` alongside the
  version and commit it already reads.
- [x] 5.2 Render a banner at the top of every page when the environment is
  anything other than production, naming the environment and when its data was
  copied. Test: present and at the top for `test`; absent for `production`;
  absent when unset; present even when the version matches production's, because
  the version does not identify the environment.
- [x] 5.3 Keep the version in the footer where it is. Test: a check that the
  banner did not become the version's new home, since the footer placement was a
  deliberate decision with its reasoning in the code.

## 6. So the test environment is not silently broken

- [x] 6.1 Add the test environment's state to the operator's Beheer page: whether
  it is running, which version, and how old its copy is. Read over the same host
  boundary, failing soft - an unreachable test environment is reported, never an
  exception on the operator's page. Test: the three states (running, stopped,
  unreachable), and that a failure does not break the rest of the page, which is
  the pattern the pipeline panel there already follows.
- [x] 6.2 Omit the panel entirely when no test environment is configured, so a
  single-environment deployment is not told something is wrong. Test: absent when
  unconfigured, rather than present and reporting a fault.

## 7. Write it down

- [x] 7.1 `docs/deployment.md`: what the test environment is for, how to copy
  data into it, how to reach it, and the two rules - it never holds the
  credential, and it is never published.
- [x] 7.2 Document the promotion sequence: build once, run in test, promote the
  same version to production. Including that promoting something never watched is
  allowed and why.
- [x] 7.3 Note the account data in the copy, so the next person placing it knows
  the test database holds real password hashes.
- [x] 7.4 State what must change when the cluster arrives and what does not, so
  `argocd-delivers-the-portal` inherits the requirements rather than re-deriving
  them.

## 8. Before calling it done

- [ ] 8.1 Full `nox` run; the suite stays free of database and network.
- [ ] 8.2 Production deployed from the new image path and confirmed unchanged -
  same version reported, same data, no environment banner.
- [ ] 8.3 One copy taken end to end, and the test portal opened against it.
- [ ] 8.4 Confirm from a device outside the tailnet that the test environment is
  unreachable, and that production still is.
