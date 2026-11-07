"""Buttons for the MG iSMART India integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from mg_ismart_india_client import MgIndiaClient

from .coordinator import MgConfigEntry, MgCoordinator
from .entity import MgEntity


@dataclass(frozen=True, kw_only=True)
class MgButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[MgIndiaClient], Awaitable[Any]]
    available_fn: Callable[[MgCoordinator], bool] = lambda c: True


COMMANDS: tuple[MgButtonDescription, ...] = (
    MgButtonDescription(
        key="find_my_car",
        name="Find my car",
        icon="mdi:car-search",
        press_fn=lambda c: c.find_my_car(),
    ),
    MgButtonDescription(
        key="tailgate",
        name="Open tailgate",
        icon="mdi:car-back",
        press_fn=lambda c: c.release_tailgate(),
        available_fn=lambda co: co.client.capabilities.tailgate,
    ),
    MgButtonDescription(
        key="windows_close",
        name="Close windows",
        icon="mdi:car-door-lock",
        press_fn=lambda c: c.control_windows(False, c.capabilities.window_param_ids),
        available_fn=lambda co: bool(co.client.capabilities.window_param_ids),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [MgRefreshButton(coordinator, "refresh")]
    if coordinator.has_pin:
        entities.extend(
            MgCommandButton(coordinator, d)
            for d in COMMANDS
            if d.available_fn(coordinator)
        )
    async_add_entities(entities)


class MgRefreshButton(MgEntity, ButtonEntity):
    """Ask the car for fresh status now, outside the normal schedule."""

    _attr_name = "Refresh status"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        # Greyed out while a sync or command is in progress, to avoid repeats.
        return super().available and not self.coordinator.busy

    async def async_press(self) -> None:
        # Asking a sleeping car can take a minute; return at once and let the
        # entities update when the answer arrives.
        self.coordinator._ensure_active("Refresh")
        if self.coordinator.busy:
            return  # already syncing; the result will show when it finishes
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self.coordinator.async_refresh(), "mg_ismart_india manual refresh"
        )


class MgCommandButton(MgEntity, ButtonEntity):
    entity_description: MgButtonDescription

    @property
    def available(self) -> bool:
        # Greyed out while a sync or command is in progress, to avoid repeats.
        return super().available and not self.coordinator.busy

    def __init__(self, coordinator: MgCoordinator, description: MgButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        client = self.coordinator.client
        await self.coordinator.async_run_command(
            str(self.entity_description.name),
            lambda: self.entity_description.press_fn(client),
        )
