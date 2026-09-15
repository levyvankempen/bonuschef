# Tasks

## 1. Make the release gate the CI gate

- [x] 1.1 Replace the hand-picked session list in `release.yml` with `uvx nox`
- [x] 1.2 Test that asserts the release workflow runs the full default list,
      so a future subset cannot be reintroduced silently

## 2. Make every check runnable on its own

- [x] 2.1 Factor a `_dbt_parse(session)` helper in `noxfile.py` and call it
      from both `tests` and `lint_sql`
- [x] 2.2 Test that the tests session prepares the manifest it depends on

## 3. Stamp the version into the image

- [x] 3.1 `ARG BONUSCHEF_VERSION` / `BONUSCHEF_COMMIT` in the `Dockerfile`,
      exported as `ENV` and written as OCI labels
- [x] 3.2 Pass them from `docker-compose.yml` as build args
- [x] 3.3 `scripts/version.sh` deriving them from `git describe`
- [x] 3.4 Tests for the derivation, including the dirty and no-git cases

## 4. Report the version at runtime

- [x] 4.1 `src/bonuschef/version.py` with the documented fallback chain
- [x] 4.2 Show it in the portal
- [x] 4.3 Tests: env var wins, metadata fallback, never raises

## 5. Deploy a tag

- [x] 5.1 `scripts/deploy.sh` — refuses non-tags, refuses to rebuild with a
      run in flight, preserves `.env`
- [x] 5.2 Test the script's guards
- [x] 5.3 Rewrite the deployment section of `docs/deployment.md`

## 6. Convert the guest and prove it

- [ ] 6.1 Convert `/opt/bonuschef` to a git checkout, `.env` intact
- [ ] 6.2 Deploy a tag and confirm the portal reports that version
