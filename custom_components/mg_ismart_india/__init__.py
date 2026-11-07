"""The MG iSMART India integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from mg_ismart_india_client import Capabilities, Snapshot, Status, Vehicle

from .cache import SnapshotCache
from .const import CONF_VIN
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

    if coordinator.paused:
        # No network at all while paused: show the last known values.
        coordinator.data = cached or _placeholder(entry)
    elif cached is not None:
        # Draw the dashboard from the saved snapshot at once, then refresh in
        # the background so a slow or sleeping car never blocks startup.
        coordinator.data = cached
        entry.async_create_background_task(
            hass, coordinator.async_refresh(), "mg_ismart_india first refresh"
        )
    else:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MgConfigEntry) -> bool:
    """Unload a config entry (the options flow reloads it itself)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: MgConfigEntry) -> None:
    """Delete the saved snapshot when the integration is removed."""
    await SnapshotCache(hass, entry.entry_id).async_remove()
