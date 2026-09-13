"""Constants."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "bluetti_charger_bridge"
NAME = "BLUETTI Charger Bridge"
PLATFORMS = ["sensor", "binary_sensor", "select"]
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 15
DEFAULT_TIMEOUT = 10
UPDATE_INTERVAL = timedelta(seconds=DEFAULT_POLL_INTERVAL)
