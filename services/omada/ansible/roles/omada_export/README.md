# omada_export

Read-only export of Omada SDN controller state via the Open API
(Client Credentials grant). Phase 1 of the Omada GitOps rollout.

Makes **no changes** to the controller. Authenticates, pulls sites and
per-site device inventory, and writes them to `services/omada/state/*.json`
for config-as-backup and endpoint-coverage verification.

## Auth
Single POST to `/openapi/authorize/token?grant_type=client_credentials`
with `{omadacId, client_id, client_secret}`. Response carries
`result.accessToken`. Subsequent calls send the header
`Authorization: AccessToken=<token>`.

## Variables
Defined in `ansible/vars/main.yml`, sourced from `ansible/vars/vault.yml`:

| Var | Meaning |
|-----|---------|
| `omada_api_base` | `https://<addr>:<port>` of the controller (e.g. `https://192.168.0.3:443` pre-cutover, `https://192.168.10.3:443` after) |
| `omada_id` | Controller (omadac) ID |
| `omada_client_id` | Open API app Client ID |
| `omada_client_secret` | Open API app Client Secret |
| `omada_validate_certs` | TLS verify; default `false` (OC200 self-signed) |

## Run
```bash
cd services/omada/ansible
ansible-playbook -i inventory.ini playbooks/export.yml
```
Outputs `sites.json` and `devices-<siteId>.json` under `services/omada/state/`.

## Roadmap
- **Phase 2 — reconcile:** diff desired-state files against the live API,
  dry-run, then apply deltas via POST. New `reconcile.yml` playbook +
  `omada_reconcile` role.
- **Phase 3 — migrate:** express the hand-built VLAN / DHCP / SSID config
  as declarative desired-state so the controller is fully redeployable.

> Endpoint coverage on the Open API is not yet confirmed for every
> VLAN/DHCP write operation. Phase 1's export verifies what this specific
> controller build exposes before any reconcile logic is written.
