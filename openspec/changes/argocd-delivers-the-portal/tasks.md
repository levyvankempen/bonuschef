## 0. Storage — done

*The disk is in and provisioned. Kept rather than deleted, because what it
assumed and what turned out to be true differ, and the difference matters to
whoever implements the rest.*

- [x] 0.1 Install the 500 GB M.2 and confirm Proxmox sees it. `/dev/sda`,
      Samsung 860 EVO M.2 500GB via an M.2-to-SATA adapter.
- [x] 0.2 Create an LVM-thin pool on it. Pool `ssd`, 456.3 GiB, created through
      the Proxmox API (`POST /nodes/proxmox/disks/lvmthin`) since there is no
      host shell. 427.7 GiB free.
- [x] 0.3 ~~Grow LXC 101's rootfs 16 → 48 GiB.~~ **Not needed, and not done.**
      The reason given was "at 67% with 4.9 GiB free"; the pressure was the
      image store, and the image store moved. `/var/lib/docker` and
      `/var/lib/containerd` are now volumes on the M.2, so the rootfs is at
      **1.5 GiB of 16, 10%**. Growing it would reserve 32 GiB to hold nothing.
- [x] 0.4 Confirm Postgres still starts and the portal still serves after the
      move, before anything cluster-shaped exists. Done the hard way: the move
      recreated every container. Production reports v1.42.0, the portal answers
      200, and the data is intact — 6 accounts, 3 saved recipes, 116k markdowns,
      3,776 opportunities.
- [x] 0.5 Restore the backup coverage the move broke. The Postgres volume used
      to sit inside the rootfs, where `vzdump` caught it for free; a mountpoint
      defaults to excluded, so moving it silently stopped backing up the one
      thing that cannot be rebuilt. `mp0` carries `backup=1` and a real backup
      was taken to confirm — `including mount point mp0`, archive 579 → 765 MB.
      Verify with `?current=1`: the plain config endpoint merges pending values
      and will report a flag that is not in effect.

## 1. Publish images, because a cluster cannot build them

- [ ] 1.1 Add a GHCR build-and-push to the release workflow, tagged
      `ghcr.io/<owner>/bonuschef:<version>`, one tag per build and never
      re-pointed.
- [ ] 1.2 Carry the version and the commit into the image, as the existing
      requirement already demands, and keep the modified-tree marking.
- [ ] 1.3 Test that the published tag's image reports the version it was built
      from, and that a tag is never reused.
- [ ] 1.4 Verify a pull works from the node before depending on it.

## 2. The cluster host

- [ ] 2.1 Create a VM on the new pool: 4 GiB RAM, 2 vCPU, 64 GiB disk.
- [ ] 2.2 Install k3s. Disable its default ingress only if the portal's own
      service does not need it.
- [ ] 2.3 Confirm the node survives a host reboot unattended, which is the one
      check the deployment doc calls decisive.
- [ ] 2.4 Make Postgres in LXC 101 reachable from the VM and from nowhere else,
      and prove the "nowhere else" half from another machine on the LAN.

## 3. The chart

- [ ] 3.1 Write `deploy/helm/bonuschef`: Dagster webserver, Dagster daemon,
      Streamlit. No Postgres.
- [ ] 3.2 Carry over every guarantee the compose stack meets, because the
      committed-path requirement binds a cluster too: restart on failure,
      bounded logs, health probes that reflect whether a service can do its
      work, and no port exposed beyond what is intended.
- [ ] 3.3 Reference secrets by name only. No value, and no placeholder that
      would function.
- [ ] 3.4 Pin the image tag from a value, so a release is a one-line change.
- [ ] 3.5 Test that the chart renders, that it names no credential value, and
      that a missing secret stops a workload rather than starting it half
      configured.

## 4. Secrets

- [ ] 4.1 Create the cluster secrets from the existing `.env`. Never printed,
      never committed, never logged.
- [ ] 4.2 Write down that the cluster cannot be rebuilt from the repository
      alone without this step. That is the cost of keeping credentials out of
      git and it should not be a surprise later.

## 5. ArgoCD

- [ ] 5.1 Install ArgoCD in the cluster.
- [ ] 5.2 Add the Application manifest pointing at the chart path, with
      automated sync and self-heal, so a hand-edited workload loses to the
      repository.
- [ ] 5.3 Keep its console reachable only from the host. It can change what runs
      and read what it is configured with.
- [ ] 5.4 Verify: a commit that changes the image tag converges with no shell on
      the cluster; a hand-edited replica count is reverted; a tag that does not
      exist leaves the previous version serving and reports the failure rather
      than leaving nothing running.

## 6. Cutover

- [ ] 6.1 Run the cluster's portal alongside compose and compare them on the
      same data before moving any traffic.
- [ ] 6.2 Point the Funnel at the cluster's portal service. The address people
      were given keeps working; it has been shared.
- [ ] 6.3 Verify from outside the tailnet: HTTPS, the sign-in wall, and that
      neither Dagster nor ArgoCD is reachable.
- [ ] 6.4 Stop the systemd timer from managing the portal, and record which
      mechanism owns what. Two managers for one workload is how a deploy is
      undone ten minutes later.
- [ ] 6.5 Keep compose able to serve for one week, then decide whether to retire
      it. Until it is retired it is the rollback.

## 7. Documentation

- [ ] 7.1 Write the cluster path into `docs/deployment.md`: what it replaces,
      what owns Postgres, the secret step, and how to get back to compose.
- [ ] 7.2 Record what this does not provide. One node means a control plane that
      can fail without anywhere to reschedule to, and the doc should say so
      rather than let a reader infer resilience from the word Kubernetes.

## 7b. Both environments, and one place to see them

- [ ] 7b.1 One chart, two value files. Production and test differ by values -
      ports, database, the environment marker, which version is described - and
      not by a second copy of the templates, so a fix cannot land in one and be
      forgotten in the other. The duplication that
      `tests/unit/test_the_test_environment.py` currently guards against stops
      being possible, and that guard is replaced by one asserting the values
      differ only where they are meant to.
- [ ] 7b.2 Carry the test environment's rules into its values, and assert each:
      no retailer credential and no scheduled job that could use one; no
      internet-facing address; `BONUSCHEF_ENVIRONMENT=test`; its own database,
      with production's unreachable from it. None of these is a property of
      Compose, so none of them survives the migration by itself.
- [ ] 7b.3 Make the ArgoCD application set describe both environments, so the
      second is not something an operator remembers to create.
- [ ] 7b.4 Confirm one surface reports version, converged-or-not, and healthy
      for both environments, and that it is not either of them. Converged and
      healthy must read as different states: they fail independently and have
      different fixes.
- [ ] 7b.5 Remove the cross-environment route this replaces: the
      `bonuschef-monitor` network, production's `BONUSCHEF_TEST_DATABASE_URL`,
      `read_test_environment_state`, and the Beheer panel that uses it. Keep
      Beheer's own panels - accounts, pipeline health, flagged ingredients -
      which are production reporting on itself.
      `tests/unit/test_monitoring_both_environments.py` goes with the network it
      describes; the one-way-route assertions in
      `test_the_test_environment.py` stay, because the rule outlives the
      mechanism.
- [ ] 7b.6 Note in docs/deployment.md that the monitoring question was
      deliberately deferred to here, with the numbers that made a metrics stack
      premature, so it is not re-litigated from scratch.

## 8. Verify

- [ ] 8.1 Full suite, ruff, ty and sqlfluff clean. No application code changes
      here, so a failure means the chart or CI touched something it should not.
- [ ] 8.2 Confirm every container-runtime requirement holds against the cluster,
      one by one, rather than assuming declarative configuration inherits them.
- [ ] 8.3 Reboot the Proxmox host. Both guests and the cluster return
      unattended, and the portal serves.
