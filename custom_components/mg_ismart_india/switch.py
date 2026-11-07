"""Air-conditioning control for the MG iSMART India integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MgConfigEntry
from .entity import MgEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.has_pin:
        async_add_entities([MgClimateSwitch(coordinator, "climate")])


class MgClimateSwitch(MgEntity, SwitchEntity):
    """Remote pre-conditioning (air conditioning) on or off."""

    _attr_name = "Air conditioning"
    _attr_icon = "mdi:air-conditioner"

    @property
    def is_on(self) -> bool | None:
        return self.snapshot.status.climate_running

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_command(
            "Air conditioning on", lambda: self.coordinator.client.control_climate(True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_command(
            "Air conditioning off",
            lambda: self.coordinator.client.control_climate(False),
        )
