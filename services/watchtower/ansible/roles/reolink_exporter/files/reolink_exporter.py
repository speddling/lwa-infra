#!/usr/bin/env python3
"""
Reolink NVR Prometheus Exporter

Authenticates via the Reolink login-token API (POST-based) which is required
on NVR firmware that no longer accepts per-request user/password parameters.

Flow:
  1. POST Login → receive session token (leaseTime seconds)
  2. Use token on all subsequent API calls
  3. Re-login automatically when token expires or a call returns code 2 (token invalid)
"""

import os
import time
import logging
import requests
from prometheus_client import start_http_server, Gauge, Info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

NVR_HOST      = os.environ.get("NVR_HOST", "192.168.0.4")
NVR_USER      = os.environ.get("NVR_USER", "admin")
NVR_PASSWORD  = os.environ["NVR_PASSWORD"]
SCRAPE_PORT   = int(os.environ.get("SCRAPE_PORT", "9720"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))

BASE_URL = f"http://{NVR_HOST}/api.cgi"

# --- Session state -----------------------------------------------------------
_token      = None
_token_exp  = 0   # epoch seconds when the current token expires


# --- Metrics -----------------------------------------------------------------
nvr_up = Gauge("reolink_nvr_up", "1 if the NVR API is reachable, 0 otherwise")

channel_online = Gauge(
    "reolink_nvr_channel_online",
    "1 if the camera channel is online, 0 otherwise",
    ["channel"]
)

hdd_capacity_mb = Gauge("reolink_nvr_hdd_capacity_mb", "Total HDD capacity in MB", ["id"])
hdd_used_mb     = Gauge("reolink_nvr_hdd_used_mb",     "Used HDD space in MB",      ["id"])
hdd_mounted     = Gauge("reolink_nvr_hdd_mounted",     "1 if HDD is mounted",        ["id"])

nvr_info = Info("reolink_nvr", "Static device information from the NVR")


# --- Auth --------------------------------------------------------------------

def login():
    """Obtain a session token from the NVR. Returns True on success."""
    global _token, _token_exp
    try:
        resp = requests.post(
            BASE_URL,
            params={"cmd": "Login"},
            json=[{
                "cmd":    "Login",
                "action": 0,
                "param":  {"User": {"userName": NVR_USER, "password": NVR_PASSWORD}}
            }],
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        logging.debug("Login response: %s", data)

        code = data[0].get("code", -1)
        if code != 0:
            detail = data[0].get("error", {}).get("detail", "unknown")
            logging.error("Login failed (code %d): %s", code, detail)
            return False

        token_info = data[0]["value"]["Token"]
        _token     = token_info["name"]
        _token_exp = time.time() + token_info.get("leaseTime", 3600) - 60  # 60s buffer
        logging.info("Logged in — token valid for %ds", token_info.get("leaseTime", 3600))
        return True

    except Exception as e:
        logging.error("Login exception: %s", e)
        return False


def ensure_token():
    """Re-login if the token is missing or about to expire."""
    if not _token or time.time() >= _token_exp:
        return login()
    return True


# --- API calls ---------------------------------------------------------------

def api_post(cmd, param=None):
    """
    POST a command to the NVR using the current session token.
    Returns the parsed response list, or None on failure.
    Automatically re-authenticates once on token expiry (code 2).
    """
    global _token

    if not ensure_token():
        return None

    payload = [{"cmd": cmd, "action": 0, "param": param or {}}]

    for attempt in range(2):
        try:
            resp = requests.post(
                BASE_URL,
                params={"cmd": cmd, "token": _token},
                json=payload,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            logging.debug("cmd=%s response: %s", cmd, data)

            code = data[0].get("code", 0)

            if code == 0:
                return data

            # code 2 = token invalid/expired — re-login and retry once
            if code == 2 and attempt == 0:
                logging.warning("Token expired, re-logging in")
                _token = None
                if login():
                    continue

            detail = data[0].get("error", {}).get("detail", "")
            logging.warning("cmd=%s error code %d: %s", cmd, code, detail)
            return None

        except Exception as e:
            logging.error("cmd=%s exception: %s", cmd, e)
            return None

    return None


# --- Collection --------------------------------------------------------------

def collect():
    # ── Device info ──────────────────────────────────────────────────────────
    data = api_post("GetDevInfo")
    if data is None:
        nvr_up.set(0)
        logging.warning("NVR unreachable — marking nvr_up=0")
        return

    nvr_up.set(1)

    try:
        dev = data[0]["value"]["DevInfo"]
        nvr_info.info({
            "model":    dev.get("model",   "unknown"),
            "firmware": dev.get("firmVer", "unknown"),
            "hardware": dev.get("hardVer", "unknown"),
            "name":     dev.get("name",    "unknown"),
        })
    except (KeyError, IndexError) as e:
        logging.warning("Failed to parse DevInfo: %s — raw: %s", e, data)

    # ── Channel status ───────────────────────────────────────────────────────
    for cmd in ("GetChannelstatus", "GetChannelStatus"):
        chan_data = api_post(cmd)
        if chan_data:
            try:
                channels = chan_data[0]["value"]["status"]
                logging.info("Channel status (%s): %s", cmd, channels)
                for ch in channels:
                    cid    = str(ch.get("channel", ch.get("ch", "?")))
                    online = int(ch.get("online", 0))
                    channel_online.labels(channel=cid).set(online)
                break
            except (KeyError, IndexError, TypeError) as e:
                logging.warning("Failed to parse %s: %s — raw: %s", cmd, e, chan_data)
    else:
        logging.warning("GetChannelstatus returned no data")

    # ── HDD info ─────────────────────────────────────────────────────────────
    hdd_data = api_post("GetHddInfo")
    if hdd_data:
        try:
            disks = hdd_data[0]["value"]["HddInfo"]
            logging.info("HDD info: %s", disks)
            for disk in disks:
                did = str(disk.get("id", "?"))
                hdd_capacity_mb.labels(id=did).set(disk.get("capacity", 0))
                hdd_used_mb.labels(id=did).set(disk.get("size", 0))
                hdd_mounted.labels(id=did).set(int(disk.get("mount", 0)))
        except (KeyError, IndexError, TypeError) as e:
            logging.warning("Failed to parse HddInfo: %s — raw: %s", e, hdd_data)
    else:
        logging.warning("GetHddInfo returned no data")


# --- Main --------------------------------------------------------------------

if __name__ == "__main__":
    logging.info("Starting Reolink NVR exporter on :%d (NVR: %s)", SCRAPE_PORT, NVR_HOST)
    start_http_server(SCRAPE_PORT)
    time.sleep(2)
    while True:
        collect()
        time.sleep(POLL_INTERVAL)
