# omada_export

Read-only **introspection** of the Omada SDN controller via the Open API
(Client Credentials grant). Authenticates, pulls sites and per-site device
inventory, and writes them to `services/omada/state/*.json` *in the runner
workspace for inspection*.

Makes **no changes** to the controller, and is **not a backup**. The exported
JSON is generated machine state, not source — it is not committed to the repo.
Its purpose is to show the controller's current shape so that **desired-state
declarations can be authored** for the reconcile phase.

## Why there is no "backup"
The repo is the source of truth and the recovery path. The controller is
rebuilt by declaring its config as code and reconciling it onto the OC200 —
factory-reset, re-adopt, run the reconcile playbook, restored. There is no
separate snapshot to keep current or to drift; the authored desired-state in
the repo *is* the recoverable definition.

## Auth
Single POST to `/openapi/authorize/token?grant_type=client_credentials`
with `{omadacId, client_id, client_secret}`. Response carries
`result.accessToken`. Subsequent calls send the header
`Authorization: AccessToken=<token>`.

## Variables
Defined in `ansible/vars/main.yml`, sourced from `ansible/vars/vault.yml`:

| Var | Meaning |
|-----|---------|
| `omada_api_base` | `https://<addr>:<port>` of the controller (`.0.7:443` pre-cutover, `.10.3:443` after) |
| `omada_id` | Controller (omadac) ID |
| `omada_client_id` | Open API app Client ID |
| `omada_client_secret` | Open API app Client Secret |
| `omada_validate_certs` | TLS verify; default `false` (OC200 self-signed) |

## Run
On the watchtower runner via **Actions → Deploy Omada Config → Run workflow**
(manual dispatch), or locally:
```bash
cd services/omada/ansible
ansible-playbook -i inventory.ini playbooks/export.yml
```
Writes `sites.json` and `devices-<siteId>.json` under `services/omada/state/`
for inspection. The workflow prints them to the run log; nothing is committed.

## Roadmap
- **Phase 2 — author desired-state:** use the introspected device/VLAN/DHCP
  shapes to write declarative desired-state files (reviewed on master like
  all IaC).
- **Phase 3 — reconcile:** diff desired-state against the live API, dry-run,
  then apply deltas via POST. New `reconcile.yml` playbook + `omada_reconcile`
  role. The controller becomes fully redeployable from the repo.

> Open API write-endpoint coverage for VLAN/DHCP/SSID is not yet confirmed on
> this controller build. The introspection output is what tells us which
> objects can be managed declaratively before reconcile logic is written.
