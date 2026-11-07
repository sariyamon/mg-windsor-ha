"""The MG iSMART India integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import MgConfigEntry, MgCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: MgConfigEntry) -> bool:
    """Set up MG iSMART India from a config entry."""
    coordinator = MgCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MgConfigEntry) -> bool:
    """Unload a config entry (the options flow reloads it itself)."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
