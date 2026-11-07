"""Constants for the MG iSMART India integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "mg_ismart_india"

CONF_PHONE = "phone"
CONF_VIN = "vin"
CONF_PIN_HASH = "pin_hash"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL_MIN = 10
MIN_SCAN_INTERVAL_MIN = 5
MAX_SCAN_INTERVAL_MIN = 120

# After a remote command, give the car a moment before re-reading its status.
POST_COMMAND_REFRESH_DELAY = timedelta(seconds=20)

MANUFACTURER = "MG Motor India"
