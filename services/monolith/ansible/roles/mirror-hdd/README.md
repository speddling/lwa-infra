# mirror-hdd

Ansible role that sets up a nightly rsync mirror of `/mnt/hdd-c` → `/mnt/hdd-d` on Monolith via a systemd timer.

## What it does

- Installs `rsync`
- Deploys `/usr/local/bin/mirror-hdd.sh` — a hardened rsync wrapper with `--archive --delete`
- Deploys `mirror-hdd.service` (oneshot) and `mirror-hdd.timer` (nightly at 02:00)
- Enables and starts the timer

## Defaults

| Variable | Default | Description |
|---|---|---|
| `mirror_source` | `/mnt/hdd-c/` | rsync source (trailing slash is intentional) |
| `mirror_dest` | `/mnt/hdd-d/` | rsync destination |
| `mirror_on_calendar` | `*-*-* 02:00:00` | systemd OnCalendar schedule |
| `mirror_log` | `/var/log/mirror-hdd.log` | log file path on Monolith |

## Verify

```bash
# Check timer status
systemctl status mirror-hdd.timer

# See next run time
systemctl list-timers mirror-hdd.timer

# Trigger a manual run
sudo systemctl start mirror-hdd.service

# Watch the log
tail -f /var/log/mirror-hdd.log
```

## Notes

- `--delete` means files removed from hdd-c are also removed from hdd-d. This is intentional — hdd-d is a mirror, not an archive.
- `Persistent=true` ensures the timer fires on next boot if it missed its scheduled window (e.g. Monolith was off at 02:00).
- `RandomizedDelaySec=300` adds up to a 5-minute jitter to avoid stacking with other scheduled jobs.
- `TimeoutStartSec=21600` allows up to 6 hours for a full sync before systemd kills the service.
