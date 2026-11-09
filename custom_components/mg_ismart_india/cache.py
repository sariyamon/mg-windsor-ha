"""Keep the last good car snapshot on disk.

Used while cloud sync is paused and right after a restart, so the dashboard
shows the last known values instead of "unavailable" and nothing has to log
in to MG just to draw it.
"""

from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store
from mg_ismart_india_client import (
    Capabilities,
    ChargeStatus,
    GpsPosition,
    GpsStatus,
    Snapshot,
    Status,
    Vehicle,
)

from .const import DOMAIN

STORAGE_VERSION = 1


def _plain(obj: Any, drop: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in asdict(obj).items() if k not in drop}


def serialize(snapshot: Snapshot) -> dict[str, Any]:
    vehicle = snapshot.vehicle
    status = snapshot.status
    data = _plain(status, ("raw", "gps", "charge"))
    data["gps"] = None if status.gps is None else _plain(status.gps, ("raw",))
    data["charge"] = None if status.charge is None else _plain(status.charge, ("_raw",))
    caps = asdict(snapshot.capabilities)
    caps["window_param_ids"] = list(caps["window_param_ids"])
    return {
        "vehicle": {
            "vin": vehicle.vin,
            "name": vehicle.name,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "model_year": vehicle.model_year,
            "color_name": vehicle.color_name,
            "series": vehicle.series,
            "is_electric": vehicle.is_electric,
        },
        "capabilities": caps,
        "status": data,
    }


def _known(cls: type, values: dict[str, Any]) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in values.items() if k in names}


def deserialize(data: dict[str, Any]) -> Snapshot:
    v = dict(data["vehicle"])
    is_ev = v.pop("is_electric", False)
    vehicle = Vehicle(
        **_known(Vehicle, v), raw={"configuration": {"EV": "1"}} if is_ev else {}
    )
    caps_data = dict(data.get("capabilities") or {})
    caps_data["window_param_ids"] = tuple(caps_data.get("window_param_ids") or ())
    caps = Capabilities(**_known(Capabilities, caps_data))
    s = dict(data["status"])
    gps = s.pop("gps", None)
    charge = s.pop("charge", None)
    if gps is not None:
        if gps.get("gps_status") is not None:
            gps["gps_status"] = GpsStatus(gps["gps_status"])
        gps = GpsPosition(**_known(GpsPosition, gps))
    if charge is not None:
        charge = ChargeStatus(**_known(ChargeStatus, charge))
    status = Status(**_known(Status, s), gps=gps, charge=charge)
    return Snapshot(vehicle, caps, status)


class SnapshotCache:
    """Disk-backed last snapshot for one config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.last_snapshot"
        )
        self.saved_at: datetime | None = None  # when that snapshot was synced

    async def async_load(self) -> Snapshot | None:
        data = await self._store.async_load()
        if not data:
            return None
        self.saved_at = dt_util.parse_datetime(data.get("saved_at") or "")
        try:
            return deserialize(data)
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, snapshot: Snapshot) -> None:
        data = serialize(snapshot)
        data["saved_at"] = dt_util.utcnow().isoformat()
        self._store.async_delay_save(lambda: data, 5)

    async def async_remove(self) -> None:
        await self._store.async_remove()
