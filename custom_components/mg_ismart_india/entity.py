"""Base entity for the MG iSMART India integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from mg_ismart_india_client import Snapshot

from .const import DOMAIN, MANUFACTURER
from .coordinator import MgCoordinator


class MgEntity(CoordinatorEntity[MgCoordinator]):
    """An entity tied to one MG vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MgCoordinator, key: str) -> None:
        super().__init__(coordinator)
        vehicle = coordinator.data.vehicle
        self._attr_unique_id = f"{vehicle.vin}_{key}"
        name = " ".join(x for x in ("MG", vehicle.model or vehicle.name) if x)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vehicle.vin)},
            manufacturer=MANUFACTURER,
            model=vehicle.model or vehicle.name,
            name=name,
            serial_number=vehicle.vin,
            hw_version=vehicle.color_name,
            model_id=vehicle.series,
        )

    @property
    def snapshot(self) -> Snapshot:
        return self.coordinator.data
