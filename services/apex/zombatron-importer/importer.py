#!/usr/bin/env python3
"""
Zombatron Importer — Slack bot for Minecraft world imports.

Flow:
  1. .mcworld file shared in #zombatron → download and stage on Monolith
  2. Bot posts confirmation request in channel
  3. Any member replies "yes" → GitHub Actions workflow clears marker + bounces pod
  4. Bot reports outcome; members reconnect to zombatron.littlewolfacres.com:30132
"""

import logging
import os
import tempfile
import threading
from pathlib import Path

import paramiko
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN      = os.environ["SLACK_APP_TOKEN"]
ZOMBATRON_CHANNEL_ID = os.environ["ZOMBATRON_CHANNEL_ID"]

MONOLITH_HOST        = os.environ["MONOLITH_HOST"]
MONOLITH_USER        = os.environ["MONOLITH_USER"]
MONOLITH_SSH_KEY     = os.environ.get("MONOLITH_SSH_KEY", str(Path.home() / ".ssh/id_ed25519"))
MONOLITH_IMPORT_PATH = os.environ.get("MONOLITH_IMPORT_PATH", "/opt/minecraft/import/realm.mcworld")

GITHUB_TOKEN         = os.environ["GITHUB_TOKEN"]
GITHUB_REPO          = os.environ.get("GITHUB_REPO", "speddling/lwa-homelab")
IMPORT_WORKFLOW      = os.environ.get("IMPORT_WORKFLOW", "slack-minecraft-import.yml")

# ── State ─────────────────────────────────────────────────────────────────────
# { channel_id: { "filename": str, "size_mb": float } }
_pending: dict = {}
_lock = threading.Lock()

# ── App ───────────────────────────────────────────────────────────────────────
app = App(token=SLACK_BOT_TOKEN)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_zombatron(channel: str) -> bool:
    return channel == ZOMBATRON_CHANNEL_ID


def stage_on_monolith(local_path: str) -> None:
    """SCP the .mcworld file to Monolith's import directory."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(MONOLITH_HOST, username=MONOLITH_USER, key_filename=MONOLITH_SSH_KEY)
    try:
        ssh.exec_command(f"mkdir -p {str(Path(MONOLITH_IMPORT_PATH).parent)}")
        with paramiko.SFTPClient.from_transport(ssh.get_transport()) as sftp:
            sftp.put(local_path, MONOLITH_IMPORT_PATH)
        log.info("Staged world at %s:%s", MONOLITH_HOST, MONOLITH_IMPORT_PATH)
    finally:
        ssh.close()


def trigger_import_workflow() -> bool:
    """Dispatch the slack-minecraft-import workflow via GitHub API."""
    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}"
        f"/actions/workflows/{IMPORT_WORKFLOW}/dispatches"
    )
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": "master"},
        timeout=15,
    )
    ok = resp.status_code == 204
    log.info("Workflow dispatch → %s %s", resp.status_code, "OK" if ok else "FAILED")
    return ok


# ── Event handlers ────────────────────────────────────────────────────────────

@app.event("file_shared")
def handle_file_shared(event, client, say):
    channel_id = event.get("channel_id")
    if not is_zombatron(channel_id):
        return

    file_id = event.get("file_id")
    file_info = client.files_info(file=file_id)["file"]
    filename = file_info.get("name", "")

    if not filename.lower().endswith(".mcworld"):
        log.info("Ignoring non-.mcworld file: %s", filename)
        return

    size_mb = round(file_info.get("size", 0) / 1_048_576, 1)
    download_url = file_info.get("url_private_download")

    log.info("Downloading %s (%s MB)", filename, size_mb)
    resp = requests.get(
        download_url,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
        timeout=120,
    )
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=".mcworld", delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        stage_on_monolith(tmp_path)
    except Exception as exc:
        log.exception("Failed to stage world on Monolith")
        say(channel=channel_id, text=f":x: Could not stage `{filename}` on Monolith: `{exc}`")
        return
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    with _lock:
        _pending[channel_id] = {"filename": filename, "size_mb": size_mb}

    say(
        channel=channel_id,
        text=(
            f":package: `{filename}` ({size_mb} MB) downloaded and staged on Monolith.\n"
            f":warning: Replying *yes* will replace the current Zombatron world "
            f"and briefly disconnect everyone.\n"
            f"Reply `yes` to import or `no` to cancel."
        ),
    )


@app.message("yes")
def handle_yes(message, say):
    channel = message.get("channel")
    if not is_zombatron(channel):
        return

    with _lock:
        job = _pending.pop(channel, None)

    if not job:
        return

    say(channel=channel, text=":hourglass_flowing_sand: Import confirmed — bouncing Zombatron now...")

    if trigger_import_workflow():
        say(
            channel=channel,
            text=(
                f":white_check_mark: `{job['filename']}` is loading.\n"
                f"Give it ~60 seconds then reconnect to `zombatron.littlewolfacres.com:30132`."
            ),
        )
    else:
        say(
            channel=channel,
            text=":x: Workflow dispatch failed — check GitHub Actions for details.",
        )


@app.message("no")
def handle_no(message, say):
    channel = message.get("channel")
    if not is_zombatron(channel):
        return

    with _lock:
        job = _pending.pop(channel, None)

    if not job:
        return

    say(
        channel=channel,
        text=f":wastebasket: Cancelled. `{job['filename']}` discarded — current world is untouched.",
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Zombatron Importer starting (Socket Mode)")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
