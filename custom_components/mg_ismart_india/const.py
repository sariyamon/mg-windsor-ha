"""Constants for the MG iSMART India integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "mg_ismart_india"

CONF_PHONE = "phone"
CONF_VIN = "vin"
CONF_PIN_HASH = "pin_hash"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ACTIVE_INTERVAL = "active_scan_interval"

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
WAKE_RETRIES = 2
WAKE_RETRY_DELAY_S = 20

# After a remote command, give the car a moment before re-reading its status.
POST_COMMAND_REFRESH_DELAY = timedelta(seconds=20)

MANUFACTURER = "MG Motor India"
