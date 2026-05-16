#!/usr/bin/env python3
"""
Reolink NVR Prometheus Exporter
Scrapes channel status, HDD info, and device info from the Reolink HTTP API.
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

# --- Metrics ---

nvr_up = Gauge(
    "reolink_nvr_up",
    "1 if the NVR API is reachable, 0 otherwise"
)

channel_online = Gauge(
    "reolink_nvr_channel_online",
    "1 if the camera channel is online, 0 otherwise",
    ["channel"]
)

hdd_capacity_mb = Gauge(
    "reolink_nvr_hdd_capacity_mb",
    "Total HDD capacity in MB",
    ["id"]
)

hdd_used_mb = Gauge(
    "reolink_nvr_hdd_used_mb",
    "Used HDD space in MB",
    ["id"]
)

hdd_mounted = Gauge(
    "reolink_nvr_hdd_mounted",
    "1 if the HDD is mounted, 0 otherwise",
    ["id"]
)

nvr_info = Info(
    "reolink_nvr",
    "Static device information from the NVR"
)


def api_get(cmd):
    """
    Hit the NVR CGI API and return parsed JSON, or None on failure.

    Reolink NVRs accept requests in two formats depending on firmware:
      GET /api.cgi?cmd=Cmd&user=u&password=p   (older firmware)
      POST /api.cgi  with JSON body             (newer firmware)
    This exporter uses the GET format. If the NVR returns HTTP 4xx/5xx or
    a JSON error code, log it and return None so collect() marks nvr_up=0
    for that cycle rather than crashing the exporter.
    """
    try:
        resp = requests.get(
            BASE_URL,
            params={"cmd": cmd, "user": NVR_USER, "password": NVR_PASSWORD},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        logging.debug("cmd=%s response: %s", cmd, data)

        # Reolink wraps errors in the response body even on HTTP 200.
        # Check for a top-level error code in the first element.
        if isinstance(data, list) and data:
            code = data[0].get("code", 0)
            if code != 0:
                logging.warning("cmd=%s returned error code %d: %s",
                                cmd, code, data[0].get("error", {}).get("detail", ""))
                return None
        return data

    except requests.exceptions.HTTPError as e:
        logging.error("HTTP error for cmd=%s: %s", cmd, e)
    except requests.exceptions.ConnectionError as e:
        logging.error("Connection error for cmd=%s: %s", cmd, e)
    except requests.exceptions.Timeout:
        logging.error("Timeout for cmd=%s (NVR at %s unresponsive)", cmd, NVR_HOST)
    except Exception as e:
        logging.error("Unexpected error for cmd=%s: %s", cmd, e)
    return None


def collect():
    # ── Device info + reachability ──────────────────────────────────────────
    data = api_get("GetDevInfo")
    if data is None:
        nvr_up.set(0)
        logging.warning("NVR unreachable — marking nvr_up=0")
        return

    nvr_up.set(1)

    try:
        dev = data[0]["value"]["DevInfo"]
        nvr_info.info({
            "model":    dev.get("model",    "unknown"),
            "firmware": dev.get("firmVer",  "unknown"),
            "hardware": dev.get("hardVer",  "unknown"),
            "name":     dev.get("name",     "unknown"),
        })
    except (KeyError, IndexError) as e:
        logging.warning("Failed to parse DevInfo: %s — raw: %s", e, data)

    # ── Channel status ──────────────────────────────────────────────────────
    # Reolink uses "GetChannelstatus" (lowercase 's') on some firmware and
    # "GetChannelStatus" (uppercase 'S') on others. Try both.
    chan_data = api_get("GetChannelstatus") or api_get("GetChannelStatus")
    if chan_data:
        try:
            channels = chan_data[0]["value"]["status"]
            logging.info("Channel status: %s", channels)
            for ch in channels:
                cid = str(ch.get("channel", ch.get("ch", "?")))
                online = int(ch.get("online", 0))
                channel_online.labels(channel=cid).set(online)
        except (KeyError, IndexError, TypeError) as e:
            logging.warning("Failed to parse ChannelStatus: %s — raw: %s", e, chan_data)
    else:
        logging.warning("GetChannelstatus returned no data — channel metrics unavailable")

    # ── HDD info ────────────────────────────────────────────────────────────
    hdd_data = api_get("GetHddInfo")
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
        logging.warning("GetHddInfo returned no data — HDD metrics unavailable")


if __name__ == "__main__":
    logging.info("Starting Reolink NVR exporter on port %d (NVR: %s)", SCRAPE_PORT, NVR_HOST)
    start_http_server(SCRAPE_PORT)
    # Give the exporter a moment to start, then run the first collection
    # so metrics are populated before Prometheus first scrapes us.
    time.sleep(2)
    while True:
        collect()
        time.sleep(POLL_INTERVAL)
