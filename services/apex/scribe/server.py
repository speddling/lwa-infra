"""
scribe — Claude's git control plane for apex

Gives Claude the full git workflow — branch, stage, commit, push, open a PR,
and sync back to main — without requiring manual terminal work. Counterpart to
Synapse: Synapse gives Claude eyes inside the cluster; Scribe gives Claude the
ability to commit what it builds.

Tools:
  git_status   Show current branch, staged/unstaged changes, and untracked files
  git_branch   Create and checkout a new branch (git checkout -b <name>)
  git_commit   Stage an explicit list of paths and commit with a message
  git_rm       Remove files from the working tree and stage the deletion
  git_push     Push the current branch to origin, setting upstream
  git_pr       Open a GitHub PR via gh pr create
  git_sync     Checkout main (or master) and pull — housekeeping after a merge

Transport: Streamable HTTP via FastMCP
Auth:      None — apex firewall restricts the port to LAN only
Security:
  - Repo-locked: SCRIBE_REPO_ROOTS env var; never a tool parameter
  - Branch-protected: mutating tools refuse main/master at the Python level
  - Merged-PR guard: mutating tools call 'gh pr view' and refuse to operate
    on a branch whose PR has already been merged — prevents writing to stale
    branches. Fails open if gh is unavailable or no PR exists.
  - Path-allowlisted staging: git_commit resolves every path inside the repo
    root before touching it — no wildcard git add .
  - No shell passthrough: every tool is a hardcoded, single-purpose function
"""

import logging
import os
import pathlib
import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("scribe")

# ---------------------------------------------------------------------------
# Configuration — all from environment; nothing is user-controlled at runtime
# ---------------------------------------------------------------------------

SCRIBE_PORT = int(os.environ.get("SCRIBE_PORT", "8765"))

# Colon-separated list of allowed absolute repo paths.
# Only paths in this list may be operated on — never a raw Claude parameter.
_raw_roots = os.environ.get("SCRIBE_REPO_ROOTS", "/Users/speddling/lwa-homelab")
REPO_ROOTS: list[pathlib.Path] = [
    pathlib.Path(p.strip()).resolve()
    for p in _raw_roots.split(":")
    if p.strip()
]

PROTECTED_BRANCHES = {"main", "master"}

logger.info(
    "Scribe starting on port %d — allowed repo roots: %s",
    SCRIBE_PORT,
    [str(r) for r in REPO_ROOTS],
)

mcp = FastMCP("scribe", host="0.0.0.0", port=SCRIBE_PORT)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_repo(repo: Optional[str]) -> pathlib.Path:
    """Map an optional repo hint to a validated path in REPO_ROOTS.

    If ``repo`` is None and there is exactly one root, that root is used.
    Otherwise ``repo`` must match a root exactly by full path or by basename.

    The returned path always comes from the server-side allowlist — the caller
    value is never used as a path directly.
    """
    if repo is None:
        if len(REPO_ROOTS) == 1:
            return REPO_ROOTS[0]
        names = ", ".join(r.name for r in REPO_ROOTS)
        raise ValueError(
            f"Multiple repo roots are configured — specify one of: {names}"
        )

    # Full-path match first (resolves symlinks), then basename match.
    candidate = pathlib.Path(repo).resolve()
    for root in REPO_ROOTS:
        if candidate == root or root.name == repo:
            return root  # always return from the allowlist, not from caller

    allowed = ", ".join(str(r) for r in REPO_ROOTS)
    raise ValueError(
        f"Repo '{repo}' is not in the allowed list. Allowed repos: {allowed}"
    )


def _current_branch(repo: pathlib.Path) -> str:
    """Return the name of the currently checked-out branch."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _default_branch(repo: pathlib.Path) -> str:
    """Detect whether the repo's primary branch is 'main' or 'master'."""
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        # refs/remotes/origin/HEAD -> refs/remotes/origin/main
        return result.stdout.strip().split("/")[-1]
    # Fallback: check which protected branch exists locally
    for branch in ("main", "master"):
        r = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=repo, capture_output=True, text=True,
        )
        if r.returncode == 0:
            return branch
    return "main"


def _assert_not_protected(branch: str) -> None:
    """Raise if the branch is main or master."""
    if branch in PROTECTED_BRANCHES:
        protected = " or ".join(sorted(PROTECTED_BRANCHES))
        raise ValueError(
            f"Branch '{branch}' is protected. Scribe refuses to mutate "
            f"{protected}. Create a feature branch with git_branch first."
        )


def _assert_pr_not_merged(branch: str, repo: pathlib.Path) -> None:
    """Raise if the branch has a merged PR on GitHub.

    Calls 'gh pr view' to check the PR state. If the PR is merged, raises
    ValueError with instructions to run git_sync and start a fresh branch.
    Fails open (allows the operation) if gh is unavailable or no PR exists.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "state", "--jq", ".state"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == "MERGED":
            raise ValueError(
                f"Branch '{branch}' has a merged PR on GitHub. "
                "Run git_sync to return to master, then create a new branch "
                "before making further changes."
            )
    except FileNotFoundError:
        # gh CLI not available — skip the check rather than blocking all commits
        logger.warning("gh CLI not found; skipping merged-PR guard for branch '%s'", branch)


def _run(cmd: list[str], cwd: pathlib.Path) -> str:
    """Run a subprocess command, raise on non-zero exit, return combined output."""
    logger.info("$ %s  (cwd=%s)", " ".join(cmd), cwd)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return (result.stdout + result.stderr).strip()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def git_status(repo: Optional[str] = None) -> str:
    """Show current branch, staged/unstaged changes, and untracked files.

    Args:
        repo: Repo name or full path. Optional when only one repo root is
              configured (the common case).
    """
    repo_path = _resolve_repo(repo)
    branch = _current_branch(repo_path)
    status = _run(["git", "status", "--short", "--branch"], repo_path)
    return f"Repo:   {repo_path}\nBranch: {branch}\n\n{status}"


@mcp.tool()
def git_branch(branch: str, repo: Optional[str] = None) -> str:
    """Create and checkout a new branch (git checkout -b <branch>).

    The new branch name must not be 'main' or 'master'.

    Args:
        branch: Name for the new branch. Use kebab-case conventional names,
                e.g. 'feat/add-scribe' or 'fix/plist-env'.
        repo:   Repo name or full path. Optional when only one root is configured.
    """
    branch = (branch or "").strip()
    if not branch:
        raise ValueError("Branch name must not be empty.")
    _assert_not_protected(branch)

    repo_path = _resolve_repo(repo)
    out = _run(["git", "checkout", "-b", branch], repo_path)
    return f"Created and checked out branch '{branch}'.\n{out}"


@mcp.tool()
def git_commit(paths: list[str], message: str, repo: Optional[str] = None) -> str:
    """Stage an explicit list of paths and commit with a message.

    Every path is resolved and validated to be inside the repo root before
    staging. No wildcard staging — only the listed files are touched.
    Refuses to commit on main or master.

    Args:
        paths:   List of file paths to stage. Relative paths are resolved
                 relative to the repo root; absolute paths must still resolve
                 inside the repo root.
        message: Commit message. Use conventional commit format, e.g.
                 'feat(scribe): add git_pr tool'.
        repo:    Repo name or full path. Optional when only one root is configured.
    """
    if not paths:
        raise ValueError("paths must not be empty.")
    message = (message or "").strip()
    if not message:
        raise ValueError("Commit message must not be empty.")

    repo_path = _resolve_repo(repo)
    branch = _current_branch(repo_path)
    _assert_not_protected(branch)
    _assert_pr_not_merged(branch, repo_path)

    # Resolve and validate every path before touching the index.
    resolved: list[pathlib.Path] = []
    for p in paths:
        raw = pathlib.Path(p)
        candidate = (repo_path / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if not str(candidate).startswith(str(repo_path) + os.sep) and candidate != repo_path:
            raise ValueError(
                f"Path '{p}' resolves outside the repo root '{repo_path}'. "
                "Scribe will not stage it."
            )
        resolved.append(candidate)

    # Stage each file individually — no wildcards.
    for rp in resolved:
        _run(["git", "add", "--", str(rp)], repo_path)

    out = _run(["git", "commit", "-m", message], repo_path)
    return f"Committed on branch '{branch}'.\n{out}"


@mcp.tool()
def git_rm(paths: list[str], repo: Optional[str] = None) -> str:
    """Remove files from the working tree and stage the deletion.

    Equivalent to `git rm` — deletes the file(s) from disk and stages the
    removal in one step. Subject to the same path validation as git_commit:
    every path must resolve inside the repo root. Refuses to operate on
    main or master.

    Use this when you need to delete tracked files as part of a commit, e.g.
    removing docs that have been consolidated elsewhere.

    Args:
        paths: List of file paths to remove. Relative paths are resolved
               relative to the repo root; absolute paths must still resolve
               inside the repo root.
        repo:  Repo name or full path. Optional when only one root is configured.
    """
    if not paths:
        raise ValueError("paths must not be empty.")

    repo_path = _resolve_repo(repo)
    branch = _current_branch(repo_path)
    _assert_not_protected(branch)
    _assert_pr_not_merged(branch, repo_path)

    # Resolve and validate every path before touching anything.
    resolved: list[pathlib.Path] = []
    for p in paths:
        raw = pathlib.Path(p)
        candidate = (repo_path / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if not str(candidate).startswith(str(repo_path) + os.sep) and candidate != repo_path:
            raise ValueError(
                f"Path '{p}' resolves outside the repo root '{repo_path}'. "
                "Scribe will not remove it."
            )
        resolved.append(candidate)

    out = _run(["git", "rm", "--"] + [str(rp) for rp in resolved], repo_path)
    return f"Removed and staged deletions on branch '{branch}'.\n{out}"


@mcp.tool()
def git_push(repo: Optional[str] = None) -> str:
    """Push the current branch to origin and set the upstream tracking ref.

    Refuses to push main or master.

    Args:
        repo: Repo name or full path. Optional when only one root is configured.
    """
    repo_path = _resolve_repo(repo)
    branch = _current_branch(repo_path)
    _assert_not_protected(branch)
    _assert_pr_not_merged(branch, repo_path)
    out = _run(["git", "push", "--set-upstream", "origin", branch], repo_path)
    return f"Pushed '{branch}' to origin.\n{out}"


@mcp.tool()
def git_pr(title: str, body: str, repo: Optional[str] = None) -> str:
    """Open a GitHub PR for the current branch via gh pr create.

    Requires gh CLI to be authenticated (the running user's existing gh auth
    is inherited — no new credentials needed).

    Args:
        title: PR title. Keep it concise and descriptive.
        body:  PR description. Include what changed and why. Markdown is fine.
        repo:  Repo name or full path. Optional when only one root is configured.
    """
    title = (title or "").strip()
    if not title:
        raise ValueError("PR title must not be empty.")

    repo_path = _resolve_repo(repo)
    branch = _current_branch(repo_path)
    _assert_not_protected(branch)
    _assert_pr_not_merged(branch, repo_path)

    out = _run(
        ["gh", "pr", "create", "--title", title, "--body", body or ""],
        repo_path,
    )
    return f"PR opened from branch '{branch}'.\n{out}"


@mcp.tool()
def git_sync(repo: Optional[str] = None) -> str:
    """Checkout the default branch (main/master) and pull latest from origin.

    Run this after a PR is merged to leave the repo in a clean, up-to-date
    state for the next session. Safe to call at any time — it will not lose
    uncommitted work (git will refuse to switch branches if the working tree
    is dirty).

    Args:
        repo: Repo name or full path. Optional when only one root is configured.
    """
    repo_path = _resolve_repo(repo)
    default = _default_branch(repo_path)
    _run(["git", "checkout", default], repo_path)
    out = _run(["git", "pull", "--ff-only", "origin", default], repo_path)
    return f"Synced to '{default}'.\n{out}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
