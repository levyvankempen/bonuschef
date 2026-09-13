## Why

Everything the stack needed to survive unattended now exists in the repo — restart policies, bounded logs, loopback-only ports, healthchecks, a credential heartbeat, failure alerting, correct data. None of it is doing anything, because the stack still only runs on a laptop. The AH refresh credential has already died twice for exactly that reason: nothing was running to exercise it.

The target is a Proxmox 9.2.2 node at 192.168.1.240, and it is smaller than the earlier plan assumed. Measured on the host: **4 cores, 8.2 GB RAM, of which 6.2 GB is already in use and 1.4 GB is free.** A Home Assistant OS VM holds 4 GB with ballooning disabled and is genuinely using 3.95 GB of it. Measured on the stack: **1.60 GB resident at idle** across its four containers, before a dbt build.

So the honest position is that bonuschef does not currently fit on this machine with any headroom, and the deployment has to say so rather than provision something that will swap under load or push Home Assistant into reclaim.

## What Changes

- The stack gets a defined home on the Proxmox node, sized against measured figures rather than assumed ones, with the resource decision stated explicitly rather than buried.
- Deployment becomes reproducible from the repository: clone, configure from the committed template, start. No step depends on remembering what was typed the first time.
- The one-time migrations are specified — the existing Postgres data, and the AH member credential, which cannot be recreated without a browser.
- The host-level preconditions the container-runtime capability silently depends on are made explicit, in particular that the container runtime must start at boot. Without it every restart policy in the repo is inert.
- Backup becomes the platform's job rather than a script, and what is recoverable from where is written down.

## Capabilities

### New Capabilities
- `deployment-target`: what the host must provide for the stack to run unattended — capacity, boot behaviour, network reachability, and the recoverability of the state that cannot be rebuilt from the repository.

### Modified Capabilities
<!-- None. `container-runtime` already covers how the stack behaves once running; this covers the machine underneath it. -->

## Impact

- New deployment documentation in the repository; no application code changes.
- The Proxmox node gains one guest and a backup schedule.
- **A resource decision is required before this can be completed**: 1.4 GB free against a 1.60 GB measured need. The spec covers the paths, but choosing between adding RAM, reclaiming it from Home Assistant, or running degraded is the operator's call and is not something this change makes on its own.
