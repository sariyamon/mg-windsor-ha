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

from .const import (
    CONF_PHONE,
    CONF_PIN_HASH,
    CONF_SCAN_INTERVAL,
    CONF_VIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    POST_COMMAND_REFRESH_DELAY,
)

_LOGGER = logging.getLogger(__name__)

type MgConfigEntry = ConfigEntry[MgCoordinator]


class MgCoordinator(DataUpdateCoordinator[Snapshot]):
    """Poll one MG vehicle and run its remote commands.

    The client is single-flight, so every call into it goes through ``_lock``.
    """

    config_entry: MgConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MgConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = MgIndiaClient(
            async_get_clientsession(hass),
            phone=entry.data[CONF_PHONE],
            password=entry.data[CONF_PASSWORD],
            vin=entry.data.get(CONF_VIN),
            pin_hash=entry.data.get(CONF_PIN_HASH),
        )
        self._lock = asyncio.Lock()
        self._capabilities_loaded = False
        self._cancel_refresh: Callable[[], None] | None = None

    @property
    def has_pin(self) -> bool:
        """True when remote commands are configured."""
        return self.client.has_pin

    async def _async_update_data(self) -> Snapshot:
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
                status = await self.client.status(include_charge=vehicle.is_electric)
            except MgIndiaLoginRejected as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except (MgIndiaApiError, ValueError, TimeoutError) as err:
                raise UpdateFailed(f"MG iSMART update failed: {err}") from err
            return Snapshot(vehicle, self.client.capabilities, status)

    async def async_run_command(
        self, label: str, command: Callable[[], Awaitable[Any]]
    ) -> None:
        """Run a remote command, then refresh the status shortly after."""
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
