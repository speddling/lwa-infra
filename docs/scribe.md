# Scribe

> Claude's git control plane. Runs on apex. Puts things in writing.

---

## Purpose

Scribe is a FastMCP server that gives Claude the ability to do the full git workflow — branch, stage, commit, push, and open a PR — without requiring manual terminal work. It is the counterpart to Synapse: Synapse gives Claude eyes and hands inside the cluster; Scribe gives Claude the ability to commit what it builds.

**Division of labour**

| Service | Host | Role |
|---|---|---|
| Synapse | monolith (k3s pod) | Read/write access to the cluster, Prometheus, and the Monolith filesystem |
| Scribe | apex (launchd service) | Git workflow over the homelab repo (and any other configured repos) |

The human stays in the loop at exactly one point: the GitHub PR review and merge. Everything before that — branching, staging, committing, pushing, opening the PR — is handled by Scribe on Claude's behalf.

---

## Architecture

```
Claude (claude.ai)
  └── MCP connection → http://apex.littlewolfacres.com:<port>/mcp
        └── Scribe (FastMCP, launchd, apex)
              └── subprocess — git + gh CLI
                    └── ~/homelab repo (and other configured REPO_ROOTS)
```

**Key design decisions**

- No shell passthrough. Each tool is a hardcoded function that does exactly one thing. There is no `run_command` escape hatch.
- Repo-locked. `SCRIBE_REPO_ROOTS` is set at startup from an environment variable. No path parameter accepted from Claude — the repo path is never user-controlled.
- Branch-protected. All mutating tools (`git_commit`, `git_push`, `git_pr`) refuse to operate on `master` or `main`.
- Path-allowlisted staging. `git_commit` accepts an explicit list of relative paths and validates each one is inside the repo root before staging. No wildcard `git add .`.
- Runs as the `speddling` user on apex, inheriting the existing SSH key and `gh` auth — no new credentials required.

---

## Tools

| Tool | Description |
|---|---|
| `git_status` | Show current branch, staged/unstaged changes, and untracked files |
| `git_branch` | Create and checkout a new branch (`git checkout -b <name>`) |
| `git_commit` | Stage a specified list of paths and commit with a message |
| `git_push` | Push the current branch to origin and set upstream |
| `git_pr` | Open a GitHub PR via `gh pr create` with title and body |

`git_status` is read-only. All other tools require an active non-protected branch.

---

## Deployment

Scribe runs as a **launchd service** on apex (macOS). There is no Docker container and no Kubernetes involvement — apex is the workstation, not a server node.

### Repository layout

```
services/apex/
├── scribe/
│   ├── server.py            # FastMCP server — all five tools
│   └── requirements.txt
└── ansible/
    ├── ansible.cfg
    ├── inventory.ini
    ├── playbooks/
    │   └── scribe.yml
    └── roles/
        └── scribe/
            ├── defaults/main.yml
            ├── tasks/main.yml
            └── templates/
                └── com.littlewolfacres.scribe.plist.j2

.github/workflows/
└── deploy-scribe.yml
```

### Ansible role behaviour

1. Ensures Python venv exists at `~/.venv/scribe`
2. Pip-installs `requirements.txt` into the venv
3. Deploys the launchd plist to `~/Library/LaunchAgents/com.littlewolfacres.scribe.plist`
4. Loads/restarts the service via `launchctl`

### Key defaults

| Variable | Default | Notes |
|---|---|---|
| `scribe_port` | `8765` | Port Scribe listens on |
| `scribe_repo_roots` | `/Users/speddling/homelab` | Colon-separated list of allowed repo roots |
| `scribe_venv` | `~/.venv/scribe` | Python venv location |
| `scribe_log` | `~/Library/Logs/scribe.log` | launchd stdout/stderr target |

### Adding additional repos

Set `SCRIBE_REPO_ROOTS` to a colon-separated list of absolute paths in the launchd plist environment. Scribe will accept git operations against any repo in that list. Each repo must already have `gh` auth and a configured remote.

Example:
```
SCRIBE_REPO_ROOTS=/Users/speddling/homelab:/Users/speddling/client-project
```

---

## Security model

| Constraint | Mechanism |
|---|---|
| Repo lock | `SCRIBE_REPO_ROOTS` hardcoded in plist env — not a tool parameter |
| Branch protection | Tools refuse `master`/`main` at the Python level before any subprocess call |
| Staging allowlist | `git_commit` resolves and validates every path before `git add` |
| Network exposure | Port restricted to LAN only — add apex firewall rule to taste |
| Auth | Runs as `speddling`, inherits `~/.ssh/id_ed25519` and `gh` token — no additional secrets |

---

## Connecting Claude

Once deployed, add Scribe to Claude's MCP servers at:

```
http://apex.littlewolfacres.com:<scribe_port>/mcp
```

This follows the same pattern as the Synapse connection (`http://monolith.littlewolfacres.com:30800/mcp`).

---

## Verify

```bash
# Check launchd service status
launchctl list | grep scribe

# View logs
tail -f ~/Library/Logs/scribe.log

# Confirm server is responding
curl http://localhost:8765/mcp
```

---

## Workflow — what a full cycle looks like

1. Claude reads the repo via the filesystem MCP (already connected)
2. Claude makes changes to files via the filesystem MCP
3. Claude calls `git_branch` to create a feature branch
4. Claude calls `git_status` to confirm what changed
5. Claude calls `git_commit` with explicit paths and a conventional commit message
6. Claude calls `git_push` to push the branch
7. Claude calls `git_pr` with a title and structured body
8. Human reviews the diff on GitHub and merges

The human's only required action is the GitHub review and merge click.

---

## Relationship to Synapse

Synapse and Scribe are complementary, not overlapping. Synapse never touches git. Scribe never touches the cluster. A new chat should load both docs if the work involves both cluster changes and repo commits.

| Need | Use |
|---|---|
| Inspect k3s pods / Prometheus / Monolith filesystem | Synapse |
| Branch, commit, push, open PR | Scribe |
| Both in one session | Reference both docs |

---

## Build status

> ⚠️ **Not yet deployed.** This document is the specification. Scribe has been designed and named but not yet built. A dedicated chat should use this doc as the source of truth to implement `services/apex/scribe/server.py`, the Ansible role, the launchd plist template, and the GitHub Actions workflow.
