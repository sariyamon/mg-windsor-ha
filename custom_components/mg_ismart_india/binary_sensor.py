"""Binary sensors for the MG iSMART India integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from mg_ismart_india_client import Snapshot

from .coordinator import MgConfigEntry
from .entity import MgEntity


@dataclass(frozen=True, kw_only=True)
class MgBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[Snapshot], bool | None]
    ev_only: bool = False


def _status(attr: str) -> Callable[[Snapshot], bool | None]:
    return lambda s: getattr(s.status, attr)


def _charge(attr: str) -> Callable[[Snapshot], bool | None]:
    def get(s: Snapshot) -> bool | None:
        charge = s.status.charge
        return None if charge is None else getattr(charge, attr)

    return get


BINARY_SENSORS: tuple[MgBinaryDescription, ...] = (
    MgBinaryDescription(
        key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_charge("is_charging"),
        ev_only=True,
    ),
    MgBinaryDescription(
        key="plugged_in",
        name="Charger plugged in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_charge("is_plugged_in"),
        ev_only=True,
    ),
    MgBinaryDescription(
        key="climate_running",
        name="Climate running",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:air-conditioner",
        value_fn=_status("climate_running"),
    ),
    MgBinaryDescription(
        key="doors",
        name="Doors",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda s: _any(
            s.status.driver_door_open,
            s.status.passenger_door_open,
            s.status.rear_left_door_open,
            s.status.rear_right_door_open,
        ),
    ),
    MgBinaryDescription(
        key="windows",
        name="Windows",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda s: _any(
            s.status.driver_window_open,
            s.status.passenger_window_open,
            s.status.rear_left_window_open,
            s.status.rear_right_window_open,
        ),
    ),
    *(
        MgBinaryDescription(
            key=key,
            name=name,
            device_class=cls,
            entity_registry_enabled_default=False,
            value_fn=_status(attr),
        )
        for key, name, cls, attr in (
            ("driver_door", "Driver door", BinarySensorDeviceClass.DOOR, "driver_door_open"),
            ("passenger_door", "Passenger door", BinarySensorDeviceClass.DOOR, "passenger_door_open"),
            ("rear_left_door", "Rear left door", BinarySensorDeviceClass.DOOR, "rear_left_door_open"),
            ("rear_right_door", "Rear right door", BinarySensorDeviceClass.DOOR, "rear_right_door_open"),
            ("driver_window", "Driver window", BinarySensorDeviceClass.WINDOW, "driver_window_open"),
            ("passenger_window", "Passenger window", BinarySensorDeviceClass.WINDOW, "passenger_window_open"),
            ("rear_left_window", "Rear left window", BinarySensorDeviceClass.WINDOW, "rear_left_window_open"),
            ("rear_right_window", "Rear right window", BinarySensorDeviceClass.WINDOW, "rear_right_window_open"),
        )
    ),
    MgBinaryDescription(
        key="boot",
        name="Boot",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:car-back",
        value_fn=_status("boot_open"),
    ),
    MgBinaryDescription(
        key="bonnet",
        name="Bonnet",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:car-select",
        value_fn=_status("bonnet_open"),
    ),
    MgBinaryDescription(
        key="lights",
        name="Lights",
        device_class=BinarySensorDeviceClass.LIGHT,
        value_fn=lambda s: _any(
            s.status.side_lights_on, s.status.dipped_beam_on, s.status.main_beam_on
        ),
    ),
)


def _any(*values: bool | None) -> bool | None:
    known = [v for v in values if v is not None]
    return any(known) if known else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    is_ev = coordinator.data.vehicle.is_electric
    async_add_entities(
        MgBinarySensor(coordinator, d)
        for d in BINARY_SENSORS
        if is_ev or not d.ev_only
    )


class MgBinarySensor(MgEntity, BinarySensorEntity):
    entity_description: MgBinaryDescription

    def __init__(self, coordinator, description: MgBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.snapshot)
