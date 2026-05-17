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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

NVR_HOST      = os.environ.get("NVR_HOST", "192.168.0.4")
NVR_USER      = os.environ.get("NVR_USER", "admin")
NVR_PASSWORD  = os.environ["NVR_PASSWORD"]
SCRAPE_PORT   = int(os.environ.get("SCRAPE_PORT", "9720"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))

BASE_URL = f"http://{NVR_HOST}/api.cgi"

_token     = None
_token_exp = 0

# --- Metrics -----------------------------------------------------------------

nvr_up         = Gauge("reolink_nvr_up", "1 if the NVR API is reachable")
channel_online = Gauge("reolink_nvr_channel_online", "1 if camera channel is online", ["channel"])
hdd_capacity_mb = Gauge("reolink_nvr_hdd_capacity_mb", "HDD capacity in MB", ["id"])
hdd_used_mb     = Gauge("reolink_nvr_hdd_used_mb",     "HDD used space in MB", ["id"])
hdd_mounted     = Gauge("reolink_nvr_hdd_mounted",     "1 if HDD is mounted", ["id"])
nvr_info        = Info("reolink_nvr", "Static device info from the NVR")

# --- Auth --------------------------------------------------------------------

def login():
    global _token, _token_exp
    try:
        resp = requests.post(
            BASE_URL,
            params={"cmd": "Login"},
            json=[{"cmd": "Login", "action": 0, "param": {"User": {"userName": NVR_USER, "password": NVR_PASSWORD}}}],
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        code = data[0].get("code", -1)
        if code != 0:
            logging.error("Login failed (code %d): %s", code, data[0].get("error", {}).get("detail", ""))
            return False
        token_info = data[0]["value"]["Token"]
        _token     = token_info["name"]
        _token_exp = time.time() + token_info.get("leaseTime", 3600) - 60
        logging.info("Logged in — token valid for %ds", token_info.get("leaseTime", 3600))
        return True
    except Exception as e:
        logging.error("Login exception: %s", e)
        return False

def ensure_token():
    if not _token or time.time() >= _token_exp:
        return login()
    return True

# --- API ---------------------------------------------------------------------

def api_post(cmd, param=None):
    global _token
    if not ensure_token():
        return None
    payload = [{"cmd": cmd, "action": 0, "param": param or {}}]
    for attempt in range(2):
        try:
            resp = requests.post(BASE_URL, params={"cmd": cmd, "token": _token}, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            code = data[0].get("code", 0)
            if code == 0:
                return data
            if code == 2 and attempt == 0:
                logging.warning("Token expired, re-logging in")
                _token = None
                if login():
                    continue
            logging.warning("cmd=%s error code %d: %s", cmd, code, data[0].get("error", {}).get("detail", ""))
            return None
        except Exception as e:
            logging.error("cmd=%s exception: %s", cmd, e)
            return None
    return None

# --- Collection --------------------------------------------------------------

def collect():
    data = api_post("GetDevInfo")
    if data is None:
        nvr_up.set(0)
        return
    nvr_up.set(1)
    try:
        dev = data[0]["value"]["DevInfo"]
        nvr_info.info({"model": dev.get("model", "unknown"), "firmware": dev.get("firmVer", "unknown"),
                       "hardware": dev.get("hardVer", "unknown"), "name": dev.get("name", "unknown")})
    except (KeyError, IndexError) as e:
        logging.warning("Failed to parse DevInfo: %s — raw: %s", e, data)

    for cmd in ("GetChannelstatus", "GetChannelStatus"):
        chan_data = api_post(cmd)
        if chan_data:
            try:
                for ch in chan_data[0]["value"]["status"]:
                    cid = str(ch.get("channel", ch.get("ch", "?")))
                    channel_online.labels(channel=cid).set(int(ch.get("online", 0)))
                break
            except (KeyError, IndexError, TypeError) as e:
                logging.warning("Failed to parse %s: %s — raw: %s", cmd, e, chan_data)

    hdd_data = api_post("GetHddInfo")
    if hdd_data:
        try:
            for disk in hdd_data[0]["value"]["HddInfo"]:
                did = str(disk.get("id", "?"))
                hdd_capacity_mb.labels(id=did).set(disk.get("capacity", 0))
                hdd_used_mb.labels(id=did).set(disk.get("size", 0))
                hdd_mounted.labels(id=did).set(int(disk.get("mount", 0)))
        except (KeyError, IndexError, TypeError) as e:
            logging.warning("Failed to parse HddInfo: %s — raw: %s", e, hdd_data)

# --- Main --------------------------------------------------------------------

if __name__ == "__main__":
    logging.info("Starting Reolink NVR exporter on :%d (NVR: %s)", SCRAPE_PORT, NVR_HOST)
    start_http_server(SCRAPE_PORT)
    time.sleep(2)
    while True:
        collect()
        time.sleep(POLL_INTERVAL)
