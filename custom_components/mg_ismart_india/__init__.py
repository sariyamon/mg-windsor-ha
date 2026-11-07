"""The MG iSMART India integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from mg_ismart_india_client import Capabilities, Snapshot, Status, Vehicle

from .cache import SnapshotCache
from .const import CONF_VIN, STARTUP_REFRESH_DELAY
from .coordinator import MgConfigEntry, MgCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _placeholder(entry: MgConfigEntry) -> Snapshot:
    """Enough to create the entities while paused before any data was saved."""
    name = entry.title.removeprefix("MG ").strip() or "Car"
    vehicle = Vehicle(vin=entry.data[CONF_VIN], name=name, model=name)
    return Snapshot(vehicle, Capabilities(), Status())


async def async_setup_entry(hass: HomeAssistant, entry: MgConfigEntry) -> bool:
    """Set up MG iSMART India from a config entry."""
    coordinator = MgCoordinator(hass, entry)
    cached = await coordinator.cache.async_load()

    # Never block startup on MG's servers: draw the dashboard from the saved
    # snapshot (or an empty placeholder) at once. While paused, nothing else
    # happens. Otherwise the first contact with MG waits STARTUP_REFRESH_DELAY,
    # leaving time to switch Cloud sync off before any login is made.
    coordinator.data = cached or _placeholder(entry)
    if not coordinator.paused:

        async def _first_refresh(_now: Any) -> None:
            if not coordinator.paused:
                await coordinator.async_refresh()

        entry.async_on_unload(
            async_call_later(hass, STARTUP_REFRESH_DELAY, _first_refresh)
        )

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MgConfigEntry) -> bool:
    """Unload a config entry (the options flow reloads it itself)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MgConfigEntry) -> None:
    """Delete the saved snapshot when the integration is removed."""
    await SnapshotCache(hass, entry.entry_id).async_remove()
