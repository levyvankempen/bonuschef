# Design

## Decisions

### Delete `k8s/` rather than fix it

Fixing means: loopback-only services, a probe that asserts the code location loaded, removing the liveness probes, and a secret template with no working value. That is most of a rewrite, for a deployment nobody runs, on manifests that predate every spec they would have to satisfy.

Git history keeps them. If Kubernetes is ever wanted, writing it against the current `container-runtime` and `deployment-target` specs will produce something better than resurrecting this — those specs did not exist when these manifests were written, and they encode things learned since, including the `/server_info` probe that these still use.

The argument for keeping it is that deleting removes an option. But an option that violates four requirements is not one anybody should take, and leaving it committed makes it look supported.

### Stop dlt retaining completed packages, rather than relocating them

Two fixes were available: point `DLT_DATA_DIR` at a volume so the growth is visible and backed up, or set `delete_completed_jobs` so there is no growth.

The second. A completed load package is a copy of data that is now in Postgres — backing it up means backing the same rows up twice, and making it visible does not make it useful. Failed packages are left intact either way, which is the case where the artefacts are the diagnosis rather than litter.

## Risks / Trade-offs

**Deleting a tracked directory is the kind of thing someone later wishes they had.** It is one `git show` away, and the proposal names the commit that removed it. Weighed against a committed path that publishes both UIs on every interface, the deletion is the safer state.

**`delete_completed_jobs` is dlt configuration, read from the environment.** If dlt renames it, the setting silently stops applying and the growth resumes — invisibly, since it is in the container layer. There is no clean way to assert a third-party config key is still honoured without running a load and inspecting the filesystem, which the offline test suite cannot do. Recorded here as a known limitation rather than papered over with a test that does not test it.
