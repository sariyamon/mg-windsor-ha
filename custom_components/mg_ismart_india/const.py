"""Constants for the MG iSMART India integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "mg_ismart_india"

CONF_PHONE = "phone"
CONF_VIN = "vin"
CONF_PIN_HASH = "pin_hash"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ACTIVE_INTERVAL = "active_scan_interval"
# Cloud sync paused: no polling and no logins (MG India allows one login per
# account, so syncing logs the phone app out). Last known values stay shown.
CONF_PAUSED = "sync_paused"

# Every poll makes MG's server wake the car's telematics unit (T-Box), which
# runs from the 12 V battery. Polling a parked car too often can drain it.
# Parked: 30 min is the recommended balance; never below 15.
DEFAULT_SCAN_INTERVAL_MIN = 30
MIN_SCAN_INTERVAL_MIN = 15
MAX_SCAN_INTERVAL_MIN = 240
# Charging or A/C running: the car is awake anyway, so polling costs nothing extra.
DEFAULT_ACTIVE_INTERVAL_MIN = 10
MIN_ACTIVE_INTERVAL_MIN = 5
MAX_ACTIVE_INTERVAL_MIN = 60
# 12 V battery saver: below this voltage, slow down to protect the battery.
LOW_12V_THRESHOLD = 12.2
LOW_12V_INTERVAL_MIN = 120

# Saved MG session, so a Home Assistant restart does not spend a daily login.
CONF_SESSION_UID = "session_uid"
CONF_SESSION_TOKEN = "session_token"

# A parked car's telematics unit can be in deep sleep and miss the client's
# short answer window. Ask again after a pause before giving up.
WAKE_RETRIES = 1
WAKE_RETRY_DELAY_S = 20
# The client polls one status request for only ~15 s (10 x 1.5 s). Waking a
# sleeping T-Box takes longer, and a new request restarts the wake-up, so keep
# polling the same request for up to ~60 s, as the MG app does.
STATUS_POLL_ATTEMPTS = 40

# First contact with MG after startup waits this long (never blocks startup).
STARTUP_REFRESH_DELAY = timedelta(seconds=30)

# After a remote command, give the car a moment before re-reading its status.
POST_COMMAND_REFRESH_DELAY = timedelta(seconds=20)

MANUFACTURER = "MG Motor India"
