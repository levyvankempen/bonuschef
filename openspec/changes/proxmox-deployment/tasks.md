## 1. Capacity

- [ ] 1.1 Confirm the measured position on the node: free memory against the stack's 1.60 GB resident idle footprint; verify by reading the node's current memory and the stack's `docker stats`, and record both figures rather than estimating
- [x] 1.2 **Resolved without buying capacity.** The stack measured 1.74 GB against 1.4 GB free. Removing the `uv run` wrapper from each service (177-189 MB each, purely a parent process) and sizing Dagster's workers to the instigators that exist brought it to 798 MB, leaving ~400 MB spare. No RAM purchase, no reclaim from Home Assistant
- [ ] 1.3 Verify `local-lvm` has room for the 1.73 GB image plus the database and its growth, and `local` has room for nightly guest backups alongside the existing guest's

## 2. The guest

- [ ] 2.1 Download a Debian 13 LXC template to `local` and create an unprivileged container on `local-lvm` at the next free VMID, sized per the design; verify it starts and has network via `vmbr0`
- [ ] 2.2 Enable `nesting=1` and `keyctl=1` on the container, without which Docker will not run inside it; verify by starting a container inside the guest
- [ ] 2.3 Set the guest to start on boot, and give it a startup delay after the Home Assistant guest so the two do not contend during boot; verify the setting is persisted in the guest config
- [ ] 2.4 Install Docker and the compose plugin inside the guest; verify `docker compose version` reports the plugin, not the legacy binary

## 3. Start on boot, verified rather than configured

- [ ] 3.1 Run `systemctl enable docker` inside the guest; without it every `restart: unless-stopped` in `docker-compose.yml` is inert and the stack silently never returns from a power cut
- [ ] 3.2 Reboot the guest and confirm the stack comes back with nobody logging in; verify all four containers reach their healthy state unaided. This is the requirement the container-runtime capability depends on and it is only observable on a reboot
- [ ] 3.3 Reboot the Proxmox host itself and confirm both the guest and the stack return; verify Home Assistant also returns, since this is the first host reboot in 44 days

## 4. The application

- [ ] 4.1 Clone the repository into the guest and copy `.env.example` to `.env`, filling every key including `POSTGRES_PASSWORD`; verify `docker compose config -q` succeeds, which it will not while a required variable is unset
- [ ] 4.2 Set `DBT_THREADS` appropriately for the guest's core count — 2 on this host, where Postgres does the same ~21 CPU-seconds of work whatever the thread count
- [ ] 4.3 Run `docker compose up -d --build` and confirm all four services reach healthy; verify the Dagster webserver and portal healthchecks pass, since this is the first time they run anywhere but the laptop

## 5. State that cannot be rebuilt

- [ ] 5.1 Take a `pg_dump` on the laptop covering the irreplaceable tables — `ah__store_markdowns` (append-only, holds the intraday markdown curve, cannot be back-filled because AH publishes only the present), `public.recipes` and `public.recipe_ingredients` (typed by hand) — and restore it into the guest; verify the row counts match and `fct_store_clearance_history` rebuilds with its full snapshot history
- [ ] 5.2 Bootstrap the AH member credential inside the guest with an interactive browser login, since a rotated refresh token cannot be copied and the current one is consumed on first use; verify the token file lands on the `dagster_home` volume and a `markdowns_refresh` run succeeds against the live API
- [ ] 5.3 Confirm the derived marts rebuild from sources with a full `dbt build`, establishing that nothing else in the database needs migrating

## 6. Recoverability

- [ ] 6.1 Schedule a nightly `vzdump` of the guest to `local`, capturing the database volume, the credential on `dagster_home`, and the configuration in one artifact
- [ ] 6.2 Restore that backup once to a scratch VMID and confirm it produces a working guest; an unverified backup is a belief, and the spec requires the restore to have been exercised. Destroy the scratch guest afterwards
- [ ] 6.3 Document what is recoverable from where — repository, sources, backup — and note explicitly that the credential needs a browser and cannot be recovered unattended

## 7. Access

- [ ] 7.1 Establish a route to the loopback-bound interfaces from the operator's phone and laptop, using Tailscale on the guest or `ssh -L` as the immediate fallback; verify the portal loads from a phone
- [ ] 7.2 Verify an unrelated device on the LAN cannot reach ports 3000, 8501 or 5455 directly, and that nothing is forwarded from the router
- [ ] 7.3 Set `NTFY_TOPIC` to a long random value and subscribe the phone, so a failed run is known within the hour rather than whenever the portal is next opened

## 8. Cutover

- [ ] 8.1 Stop the laptop stack once the guest is serving, so two schedulers are not scraping the same store and rotating the same credential against each other
- [ ] 8.2 Confirm over the following days that the schedules fire on the guest — the clearance scrape hourly, the daily refresh at 17:30, the credential heartbeat twice daily — and that `fct_store_clearance_history` starts accumulating the intraday curve that has been missing since July
- [ ] 8.3 Add the deployment procedure to the repository so the second deployment needs no knowledge held only by whoever did the first
