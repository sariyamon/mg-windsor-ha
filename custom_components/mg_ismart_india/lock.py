"""Door lock for the MG iSMART India integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
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
        async_add_entities([MgDoorLock(coordinator, "door_lock")])


class MgDoorLock(MgEntity, LockEntity):
    _attr_name = "Doors"

    @property
    def available(self) -> bool:
        # Greyed out while a sync or command is in progress, to avoid repeats.
        return super().available and not self.coordinator.busy

    @property
    def is_locked(self) -> bool | None:
        return self.snapshot.status.locked

    async def async_lock(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_command(
            "Lock", lambda: self.coordinator.client.control_door_lock(True)
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        await self.coordinator.async_run_command(
            "Unlock", lambda: self.coordinator.client.control_door_lock(False)
        )
