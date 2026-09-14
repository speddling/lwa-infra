#!/usr/bin/env python3
"""Back up Plane, apply only the reviewed migration gap, and verify startup."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

BACKEND = "sha256:90032ce088708889b60c00d491897916f4deb882facda27db59fd10fb68729ef"
EXPECTED = {
    "db.0122_alter_draftissue_assignees_alter_issue_assignees_and_more",
    "django_celery_beat.0019_alter_periodictasks_options",
}
SECRETS = ["plane-pgdb-secret", "plane-rabbitmq-secret", "plane-docstore-secret",
           "plane-app-env-secret", "plane-live-env-secret"]
BACKUP_ROOT = Path("/var/backups/lwa-plane")
LOCK_PATH = Path("/run/lock/lwa-plane-recovery.lock")


def command(*args):
    return ["k3s", "kubectl", "--request-timeout=20s", *args]


def run(*args, stdout=subprocess.PIPE, stdin=None, stderr=subprocess.PIPE, timeout=120):
    result = subprocess.run(command(*args), stdout=stdout, stdin=stdin,
                            stderr=stderr, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"kubectl {args[0]} failed (exit {result.returncode}); raw output withheld")
    return result.stdout


def get(kind, name):
    return json.loads(run("get", kind, name, "-n", "plane", "-o", "json"))


def api_pod():
    pods = json.loads(run("get", "pods", "-n", "plane", "-o", "json"))["items"]
    candidates = []
    for pod in pods:
        for status in pod["status"].get("containerStatuses", []):
            if status["name"] in {"plane-api", "plane-worker", "plane-beat-worker"} and "running" in status.get("state", {}):
                if not status.get("imageID", "").endswith("@" + BACKEND):
                    raise RuntimeError("Running backend image differs from reviewed v1.4.2 digest")
                if status["name"] == "plane-api":
                    candidates.append(pod)
    if not candidates:
        raise RuntimeError("No running API container")
    return max(candidates, key=lambda p: p["metadata"]["creationTimestamp"])


def pending(pod):
    output = run("exec", "-n", "plane", pod["metadata"]["name"], "-c", "plane-api", "--",
                 "env", "PGOPTIONS=-c default_transaction_read_only=on",
                 "python", "manage.py", "showmigrations", "--plan", "--no-color").decode()
    rows = re.findall(r"^\[(X| )\]  ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)\s*$", output, re.M)
    if not rows:
        raise RuntimeError("Unrecognized migration plan")
    result = {name for applied, name in rows if applied == " "}
    if result - EXPECTED:
        raise RuntimeError("Migration plan contains unreviewed changes")
    return result


def backup(directory):
    # Stream the custom archive directly to a root-only host file, never Actions logs.
    with (directory / "database.dump").open("xb") as output:
        run("exec", "-n", "plane", "plane-pgdb-wl-0", "-c", "plane-pgdb", "--",
            "sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom',
            stdout=output, timeout=600)
    if (directory / "database.dump").stat().st_size < 1024:
        raise RuntimeError("Database backup is unexpectedly small")
    # Decode the entire archive to /dev/null; this does not connect to a database.
    with (directory / "database.dump").open("rb") as archive:
        run("exec", "-i", "-n", "plane", "plane-pgdb-wl-0", "-c", "plane-pgdb", "--",
            "pg_restore", "--file=/dev/null", stdin=archive, timeout=600)
    for kind, names, filename in [
        ("secret", SECRETS, "secrets.json"),
        ("configmap", ["plane-app-vars", "plane-live-vars"], "configmaps.json"),
    ]:
        with (directory / filename).open("xb") as output:
            run("get", kind, *names, "-n", "plane", "-o", "json", stdout=output)
    hashes = {}
    for path in directory.iterdir():
        if path.is_file():
            with path.open("rb") as source:
                hashes[path.name] = hashlib.file_digest(source, "sha256").hexdigest()
    (directory / "sha256.json").write_text(json.dumps(hashes, indent=2))
    print(f"Backup saved and archive decoded successfully: {directory}", flush=True)


def verify():
    # A Kubernetes Ready worker can still be in wait_for_migrations. Check for Celery.
    process_check = (
        "from pathlib import Path; import sys; "
        "found=any(any(x.rsplit(b'/',1)[-1].startswith((b'celery',b'[celery')) "
        "for x in p.read_bytes().split(b'\\0')[:2]) "
        "for p in Path('/proc').glob('[0-9]*/cmdline') if p.exists()); "
        "sys.exit(0 if found else 1)"
    )
    for deployment in ("plane-api-wl", "plane-worker-wl", "plane-beat-worker-wl"):
        run("rollout", "status", "deployment/" + deployment, "-n", "plane", "--timeout=180s", timeout=200)
    for deployment, container in (("plane-worker-wl", "plane-worker"), ("plane-beat-worker-wl", "plane-beat-worker")):
        deadline = time.monotonic() + 120
        while True:
            try:
                run("exec", "-n", "plane", "deployment/" + deployment, "-c", container,
                    "--", "python", "-c", process_check)
                break
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(5)
    # Exercise the endpoint used by the UI through the API Service; discard its payload.
    run("exec", "-n", "plane", "deployment/plane-api-wl", "-c", "plane-api", "--",
        "python", "-c", "import urllib.request; r=urllib.request.urlopen(urllib.request.Request("
        "'http://plane-api:8000/api/instances/', headers={'Host':'plane.littlewolfacres.com'}), timeout=15); "
        "assert r.status == 200")


def recover(ack):
    if not ack or os.geteuid() != 0 or socket.gethostname().split(".")[0] != "monolith":
        raise RuntimeError("Requires explicit acknowledgement and root on Monolith")
    os.umask(0o077)
    with LOCK_PATH.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        job = get("job", "plane-api-migrate-1")
        if job.get("status", {}).get("active") or job.get("status", {}).get("succeeded") != 1:
            raise RuntimeError("Expected the existing completed migrator; inspect changed job state")
        pod = api_pod()
        plan = pending(pod)
        print(json.dumps({"pending": sorted(plan), "reviewed_backend": BACKEND}), flush=True)
        root = BACKUP_ROOT
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_uid != 0 or root.stat().st_mode & 0o077:
            raise RuntimeError("Backup directory must be root-owned and private")
        directory = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=root))
        backup(directory)
        # Recheck image, pod identity and schema after the backup, before any writes.
        current = api_pod()
        if current["metadata"]["uid"] != pod["metadata"]["uid"] or pending(current) != plan:
            raise RuntimeError("API pod or migration plan changed during backup; inspect before retry")
        if plan:
            with (directory / "migration.log").open("xb") as output:
                run("exec", "-n", "plane", pod["metadata"]["name"], "-c", "plane-api", "--",
                    "python", "manage.py", "migrate", "--noinput", "--no-color",
                    stdout=output, stderr=subprocess.STDOUT, timeout=600)
        if pending(api_pod()):
            raise RuntimeError("Migrations still pending after recovery")
        verify()
        (directory / "recovery-success.json").write_text(json.dumps({"backend": BACKEND, "pending": 0}))
        print("Plane migrations complete; API rollout, worker processes and instance endpoint passed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--maintenance-ack", action="store_true")
    recover(parser.parse_args().maintenance_ack)
