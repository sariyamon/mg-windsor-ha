"""Data coordinator for the MG iSMART India integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from mg_ismart_india_client import (
    MgIndiaApiError,
    MgIndiaClient,
    MgIndiaCommandIndeterminate,
    MgIndiaLoginRejected,
    Snapshot,
)

from .cache import SnapshotCache
from .const import (
    CONF_ACTIVE_INTERVAL,
    CONF_PAUSED,
    CONF_PHONE,
    CONF_PIN_HASH,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_TOKEN,
    CONF_SESSION_UID,
    CONF_VIN,
    DEFAULT_ACTIVE_INTERVAL_MIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    LOW_12V_INTERVAL_MIN,
    LOW_12V_THRESHOLD,
    MIN_ACTIVE_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
    POST_COMMAND_REFRESH_DELAY,
    WAKE_RETRIES,
    WAKE_RETRY_DELAY_S,
)

_NOT_READY = "not ready"

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
        self.paused: bool = bool(entry.options.get(CONF_PAUSED, False))
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
            _LOGGER.info("MG cloud sync paused; no further requests will be sent")
            self.async_update_listeners()
        else:
            self.update_interval = timedelta(minutes=self.parked_minutes)
            _LOGGER.info("MG cloud sync resumed")
            await self.async_request_refresh()

    def _ensure_active(self, label: str) -> None:
        if self.paused:
            raise HomeAssistantError(
                f"{label}: cloud sync is paused. Turn on 'Cloud sync' to contact the car."
            )

    async def _async_update_data(self) -> Snapshot:
        if self.paused:
            # Never touch the network while paused, not even for a manual refresh.
            if self.data is None:
                raise UpdateFailed("Cloud sync is paused and no saved data is available yet")
            return self.data
        async with self._lock:
            try:
                if self.client.vehicle is None:
                    await self.client.vehicles()
                vehicle = self.client.vehicle
                if vehicle is None:
                    raise UpdateFailed("No vehicle found on this MG account")
                if not self._capabilities_loaded:
                    try:
                        await self.client.refresh_capabilities()
                    except MgIndiaLoginRejected:
                        raise
                    except MgIndiaApiError as err:
                        _LOGGER.debug("Capability discovery failed: %s", err)
                    self._capabilities_loaded = True
                status = await self._status_with_wake(vehicle.is_electric)
            except MgIndiaLoginRejected as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (MgIndiaApiError, ValueError, TimeoutError) as err:
                if _NOT_READY in str(err) and self.data is not None:
                    # The car stayed asleep. Keep showing the last known values
                    # (their "Last update from car" time shows their age) rather
                    # than turning every entity unavailable.
                    _LOGGER.info("MG car did not answer this refresh; keeping last data")
                    self._save_session()
                    return self.data
                raise UpdateFailed(f"MG iSMART update failed: {err}") from err
            self._save_session()
            snapshot = Snapshot(vehicle, self.client.capabilities, status)
            self._adapt_interval(snapshot)
            self.cache.save(snapshot)
            return snapshot

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
        async with self._lock:
            try:
                await command()
            except MgIndiaCommandIndeterminate as err:
                # The car may or may not have acted; re-read rather than guess.
                self._schedule_refresh()
                raise HomeAssistantError(
                    f"{label}: the car did not confirm the command ({err}). "
                    "Status will refresh shortly."
                ) from err
            except MgIndiaLoginRejected as err:
                self.config_entry.async_start_reauth(self.hass)
                raise HomeAssistantError(f"{label}: login rejected ({err})") from err
            except MgIndiaApiError as err:
                raise HomeAssistantError(f"{label} failed: {err}") from err
        self._schedule_refresh()

    def _schedule_refresh(self) -> None:
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
