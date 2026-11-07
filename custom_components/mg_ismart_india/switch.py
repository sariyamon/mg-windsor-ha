"""Switches for the MG iSMART India integration: cloud sync and air conditioning."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
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
    entities: list[SwitchEntity] = [MgSyncSwitch(coordinator, "cloud_sync")]
    if coordinator.has_pin:
        entities.append(MgClimateSwitch(coordinator, "climate"))
    async_add_entities(entities)


class MgSyncSwitch(MgEntity, SwitchEntity):
    """Turn all contact with MG's servers on or off.

    MG India allows one login per account, so syncing logs the phone app out.
    Off: no polling, no logins, no commands; the last known values stay shown.
    """

    _attr_name = "Cloud sync"
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        # Must stay usable even when the last refresh failed, so it can resume.
        return True

    @property
    def is_on(self) -> bool:
        return not self.coordinator.paused

    @property
    def icon(self) -> str:
        return "mdi:cloud-sync" if self.is_on else "mdi:cloud-off-outline"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_paused(False)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_paused(True)
        self.async_write_ha_state()


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
