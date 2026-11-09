"""Data coordinator for the MG iSMART India integration."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from mg_ismart_india_client import (
    MgIndiaApiError,
    MgIndiaClient,
    MgIndiaCommandIndeterminate,
    MgIndiaLoginRejected,
    Snapshot,
)
from mg_ismart_india_client import client as _mg_client

from .cache import SnapshotCache
from .const import (
    CONF_ACTIVE_INTERVAL,
    CONF_PAUSED,
    CONF_PHONE,
    CONF_PIN_HASH,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_TOKEN,
    CONF_SESSION_UID,
    CONF_SYNC_TIMEOUT,
    CONF_VIN,
    DEFAULT_ACTIVE_INTERVAL_MIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DEFAULT_SYNC_TIMEOUT_S,
    DOMAIN,
    LOW_12V_INTERVAL_MIN,
    LOW_12V_THRESHOLD,
    MAX_SYNC_TIMEOUT_S,
    MIN_ACTIVE_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
    MIN_SYNC_TIMEOUT_S,
    POST_COMMAND_REFRESH_DELAY,
    REJECTED_BACKOFF_MIN,
    STATUS_POLL_ATTEMPTS,
    SYNC_COMMAND,
    SYNC_CONNECTING,
    SYNC_ERROR,
    SYNC_LOGIN_FAILED,
    SYNC_NO_RESPONSE,
    SYNC_OK,
    SYNC_PAUSED,
    SYNC_REJECTED,
    SYNC_SCHEDULED,
    SYNC_TIMED_OUT,
    SYNC_WAITING,
    WAKE_RETRIES,
    WAKE_RETRY_DELAY_S,
)

_NOT_READY = "not ready"
# A non-pending dispatcher result: MG refused the request outright.
_REJECTED = re.compile(r"failed: result \d+")

# Give a sleeping car longer to answer one status request (see const).
if getattr(_mg_client, "STATUS_ATTEMPTS", 0) < STATUS_POLL_ATTEMPTS:
    _mg_client.STATUS_ATTEMPTS = STATUS_POLL_ATTEMPTS

_LOGGER = logging.getLogger(__name__)

type MgConfigEntry = ConfigEntry[MgCoordinator]


class MgCoordinator(DataUpdateCoordinator[Snapshot]):
    """Poll one MG vehicle and run its remote commands.

    The client is single-flight, so every call into it goes through ``_lock``.
    """

    config_entry: MgConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MgConfigEntry) -> None:
        # Clamp to the safe floors even if older options stored a shorter value.
        self.parked_minutes = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)),
            MIN_SCAN_INTERVAL_MIN,
        )
        self.active_minutes = max(
            int(entry.options.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL_MIN)),
            MIN_ACTIVE_INTERVAL_MIN,
        )
        self.battery_saver = False
        self.sync_timeout = min(
            max(int(entry.options.get(CONF_SYNC_TIMEOUT, DEFAULT_SYNC_TIMEOUT_S)), MIN_SYNC_TIMEOUT_S),
            MAX_SYNC_TIMEOUT_S,
        )
        self.paused: bool = bool(entry.options.get(CONF_PAUSED, False))
        # Sync status shown to the user (see SYNC_STATES in const).
        self.sync_state: str = SYNC_PAUSED if self.paused else SYNC_SCHEDULED
        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.rejected_backoff = False
        self.first_refresh_at: datetime | None = None  # the delayed first sync after start-up
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None if self.paused else timedelta(minutes=self.parked_minutes),
        )
        self.cache = SnapshotCache(hass, entry.entry_id)
        self.client = MgIndiaClient(
            async_get_clientsession(hass),
            phone=entry.data[CONF_PHONE],
            password=entry.data[CONF_PASSWORD],
            vin=entry.data.get(CONF_VIN),
            pin_hash=entry.data.get(CONF_PIN_HASH),
        )
        # Reuse the saved session: MG India counts every fresh login against a
        # daily quota. An expired session is refreshed by the client itself.
        if entry.data.get(CONF_SESSION_UID) and entry.data.get(CONF_SESSION_TOKEN):
            self.client.uid = entry.data[CONF_SESSION_UID]
            self.client.token = entry.data[CONF_SESSION_TOKEN]
        self._lock = asyncio.Lock()
        self._capabilities_loaded = False
        self._cancel_refresh: Callable[[], None] | None = None

    @property
    def busy(self) -> bool:
        """True while a sync or a remote command is talking to MG."""
        return self._lock.locked()

    async def async_request_refresh(self) -> None:
        """Ignore extra refresh requests while one is already running."""
        if self.busy:
            _LOGGER.debug("MG sync already in progress; ignoring extra refresh request")
            return
        await super().async_request_refresh()

    @property
    def has_pin(self) -> bool:
        """True when remote commands are configured."""
        return self.client.has_pin

    async def async_set_paused(self, paused: bool) -> None:
        """Pause or resume all contact with MG's servers (persists across restarts)."""
        entry = self.config_entry
        self.paused = paused
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PAUSED: paused}
        )
        if paused:
            if self._cancel_refresh:
                self._cancel_refresh()
                self._cancel_refresh = None
            self.update_interval = None
            self.sync_state = SYNC_PAUSED
            _LOGGER.info("MG cloud sync paused; no further requests will be sent")
            self.async_update_listeners()
        else:
            self.update_interval = timedelta(minutes=self.parked_minutes)
            self.rejected_backoff = False
            self._set_state(SYNC_SCHEDULED)
            _LOGGER.info("MG cloud sync resumed")
            await self.async_request_refresh()

    async def async_sync_once(self) -> None:
        """Sync now. If cloud sync is off, sync this one time and leave it off afterwards."""
        if self.busy:
            return  # already syncing; the result will show when it finishes
        if not self.paused:
            await self.async_refresh()
            return
        _LOGGER.info("MG one-time sync while cloud sync is off")
        self.paused = False  # in memory only: the saved setting stays "off"
        self.rejected_backoff = False
        try:
            await self.async_refresh()
        finally:
            self.paused = True
            self.update_interval = None
            if self._cancel_refresh:
                self._cancel_refresh()
                self._cancel_refresh = None
            unsub = getattr(self, "_async_unsub_refresh", None)
            if callable(unsub):
                unsub()
            if self.sync_state == SYNC_OK:
                self.sync_state = SYNC_PAUSED  # result is in last_success / the message
            self.async_update_listeners()

    def _ensure_active(self, label: str) -> None:
        if self.paused:
            raise HomeAssistantError(
                f"{label}: cloud sync is paused. Turn on 'Cloud sync' to contact the car."
            )

    def _set_state(self, state: str, error: str | None = None) -> None:
        self.sync_state = state
        if error is not None:
            self.last_error = error
        self.async_update_listeners()

    @property
    def next_refresh(self) -> datetime | None:
        if self.paused or self.update_interval is None:
            return None
        if self.last_attempt is None:
            return self.first_refresh_at
        return self.last_attempt + self.update_interval

    def _keep_or_fail(self, state: str, message: str, err: Exception) -> Snapshot:
        """Show the last known values with an explanatory status, if we have any."""
        self._set_state(state, message)
        if self.data is not None:
            return self.data
        raise UpdateFailed(message) from err

    async def _async_update_data(self) -> Snapshot:
        if self.paused:
            # Never touch the network while paused, not even for a manual refresh.
            if self.data is None:
                raise UpdateFailed("Cloud sync is paused and no saved data is available yet")
            return self.data
        async with self._lock:
            self.last_attempt = dt_util.utcnow()
            self._set_state(SYNC_CONNECTING)
            try:
                async with asyncio.timeout(self.sync_timeout):
                    vehicle, status = await self._fetch()
            except MgIndiaLoginRejected as err:
                self._set_state(SYNC_LOGIN_FAILED, f"MG rejected the login: {err}")
                raise ConfigEntryAuthFailed(str(err)) from err
            except TimeoutError as err:
                self._save_session()
                _LOGGER.info("MG sync timed out after %d s; keeping last data", self.sync_timeout)
                return self._keep_or_fail(
                    SYNC_TIMED_OUT,
                    f"No answer from MG within {self.sync_timeout} s; will try again at the next refresh",
                    err,
                )
            except (MgIndiaApiError, ValueError, aiohttp.ClientError) as err:
                return self._handle_failure(err)
            self._save_session()
            snapshot = Snapshot(vehicle, self.client.capabilities, status)
            self.rejected_backoff = False
            self._adapt_interval(snapshot)
            self.cache.save(snapshot)
            self.last_success = dt_util.utcnow()
            self.last_error = None
            self._set_state(SYNC_OK)
            return snapshot

    async def _fetch(self):
        """Log in if needed, find the car, and read its status."""
        if self.client.vehicle is None:
            await self.client.vehicles()
        vehicle = self.client.vehicle
        if vehicle is None:
            raise MgIndiaApiError("No vehicle found on this MG account")
        if not self._capabilities_loaded:
            try:
                await self.client.refresh_capabilities()
            except MgIndiaLoginRejected:
                raise
            except MgIndiaApiError as err:
                _LOGGER.debug("Capability discovery failed: %s", err)
            self._capabilities_loaded = True
        self._set_state(SYNC_WAITING)
        status = await self._status_with_wake(vehicle.is_electric)
        return vehicle, status

    def _handle_failure(self, err: Exception) -> Snapshot:
        text = str(err) or type(err).__name__
        self._save_session()
        if _NOT_READY in text:
            # The car stayed asleep. Keep the last known values; their
            # "Last update from car" time shows how old they are.
            _LOGGER.info("MG car did not answer this refresh; keeping last data")
            return self._keep_or_fail(
                SYNC_NO_RESPONSE,
                "The car did not answer (it may be asleep or out of mobile signal)",
                err,
            )
        if _REJECTED.search(text):
            # MG refused the request outright (e.g. result 7). Back off so
            # repeated requests do not make it worse.
            self.rejected_backoff = True
            self.update_interval = timedelta(minutes=REJECTED_BACKOFF_MIN)
            _LOGGER.warning(
                "MG rejected the request (%s); next try in %d min", text, REJECTED_BACKOFF_MIN
            )
            return self._keep_or_fail(
                SYNC_REJECTED,
                f"MG refused the request ({text}); retrying in {REJECTED_BACKOFF_MIN} min",
                err,
            )
        return self._keep_or_fail(SYNC_ERROR, f"Could not reach MG: {text}", err)

    async def _status_with_wake(self, include_charge: bool):
        """Read status, giving a deep-sleeping telematics unit time to wake."""
        for attempt in range(WAKE_RETRIES + 1):
            try:
                return await self.client.status(include_charge=include_charge)
            except MgIndiaApiError as err:
                if _NOT_READY not in str(err) or attempt == WAKE_RETRIES:
                    raise
                _LOGGER.debug("MG car still waking (attempt %d); retrying", attempt + 1)
                await asyncio.sleep(WAKE_RETRY_DELAY_S)
        raise MgIndiaApiError("Vehicle status was not ready after polling")

    def _save_session(self) -> None:
        """Persist a new MG session so restarts reuse it instead of logging in."""
        uid, token = self.client.uid, self.client.token
        data = self.config_entry.data
        if not uid or not token or (
            data.get(CONF_SESSION_UID) == uid and data.get(CONF_SESSION_TOKEN) == token
        ):
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**data, CONF_SESSION_UID: uid, CONF_SESSION_TOKEN: token},
        )

    def _adapt_interval(self, snapshot: Snapshot) -> None:
        """Poll often only while the car is awake anyway; protect a low 12 V battery."""
        if self.paused:
            self.update_interval = None
            return
        if self.rejected_backoff:
            return
        status = snapshot.status
        charge = status.charge
        awake = bool(charge is not None and charge.is_charging) or bool(
            status.climate_running
        )
        volts = status.aux_battery_voltage
        low_12v = volts is not None and 0 < volts < LOW_12V_THRESHOLD and not awake
        if low_12v and not self.battery_saver:
            _LOGGER.warning(
                "MG 12 V battery is low (%.1f V): slowing refresh to every %d min "
                "to avoid draining it",
                volts,
                LOW_12V_INTERVAL_MIN,
            )
        elif self.battery_saver and not low_12v:
            _LOGGER.info("MG 12 V battery recovered; normal refresh resumed")
        self.battery_saver = low_12v
        if awake:
            minutes = self.active_minutes
        elif low_12v:
            minutes = max(self.parked_minutes, LOW_12V_INTERVAL_MIN)
        else:
            minutes = self.parked_minutes
        self.update_interval = timedelta(minutes=minutes)

    async def async_run_command(
        self, label: str, command: Callable[[], Awaitable[Any]]
    ) -> None:
        """Run a remote command, then refresh the status shortly after."""
        self._ensure_active(label)
        if not self.has_pin:
            raise HomeAssistantError(
                "Remote commands need the 4-digit MG app PIN; add it in the integration options"
            )
        if self.busy:
            raise HomeAssistantError(f"{label}: the car is busy with another request, try again shortly")
        previous = self.sync_state
        try:
            async with self._lock:
                self._set_state(SYNC_COMMAND)  # greys out the controls meanwhile
                try:
                    async with asyncio.timeout(self.sync_timeout):
                        await command()
                except TimeoutError as err:
                    self._schedule_post_command_refresh()
                    raise HomeAssistantError(
                        f"{label}: the car did not answer within {self.sync_timeout} s. "
                        "Status will refresh shortly."
                    ) from err
                except MgIndiaCommandIndeterminate as err:
                    # The car may or may not have acted; re-read rather than guess.
                    self._schedule_post_command_refresh()
                    raise HomeAssistantError(
                        f"{label}: the car did not confirm the command ({err}). "
                        "Status will refresh shortly."
                    ) from err
                except MgIndiaLoginRejected as err:
                    self.config_entry.async_start_reauth(self.hass)
                    raise HomeAssistantError(f"{label}: login rejected ({err})") from err
                except MgIndiaApiError as err:
                    raise HomeAssistantError(f"{label} failed: {err}") from err
        finally:
            # Lock released: restore the status and re-enable the controls.
            self._set_state(previous)
        self._schedule_post_command_refresh()

    def _schedule_post_command_refresh(self) -> None:
        if self._cancel_refresh:
            self._cancel_refresh()

        async def _refresh(_now: Any) -> None:
            self._cancel_refresh = None
            await self.async_request_refresh()

        self._cancel_refresh = async_call_later(
            self.hass, POST_COMMAND_REFRESH_DELAY, _refresh
        )

    async def async_shutdown(self) -> None:
        """Cancel any pending post-command refresh."""
        if self._cancel_refresh:
            self._cancel_refresh()
            self._cancel_refresh = None
        await super().async_shutdown()
