"""GPS location for the MG iSMART India integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MgConfigEntry
from .entity import MgEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([MgTracker(entry.runtime_data, "location")])


class MgTracker(MgEntity, TrackerEntity):
    """Where the car last reported a GPS fix."""

    _attr_name = "Location"
    _attr_icon = "mdi:car-electric"
    _last: tuple[float, float] | None = None

    def _gps(self):
        gps = self.snapshot.status.gps
        if gps is not None and gps.has_fix:
            self._last = (gps.latitude, gps.longitude)
        return gps

    @property
    def latitude(self) -> float | None:
        self._gps()
        return self._last[0] if self._last else None

    @property
    def longitude(self) -> float | None:
        self._gps()
        return self._last[1] if self._last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        gps = self._gps()
        if gps is None:
            return {}
        return {
            "speed_kmh": gps.speed_kmh,
            "heading": gps.heading_deg,
            "satellites": gps.satellites,
            "gps_fix": gps.has_fix,
        }
