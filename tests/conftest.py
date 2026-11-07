"""Fixtures for MG iSMART India tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from mg_ismart_india_client import Capabilities, ChargeStatus, GpsPosition, GpsStatus, Status, Vehicle
import pytest

VIN = "MZ7TESTVIN0000001"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_charge(**kw) -> ChargeStatus:
    base = dict(
        is_charging=True, is_plugged_in=True, charging_type=2, charging_electricity_phase=1,
        soc=72.0, range_km=245.0, charging_voltage=380.0, charging_current=17.5,
        battery_energy_kwh=27.1, working_voltage=380.0, working_current=17.5,
        charge_time_elapsed_s=1200, start_time=1794040000, end_time=1794050000,
        charge_time_remaining_min=95, charging_pile_id=None, charging_pile_supplier=None,
        odometer_km=8450.0, distance_since_last_charge_km=42.3,
        power_usage_since_last_charge_kwh=5.6, mileage_of_day_raw=None,
        power_usage_of_day_raw=None, static_energy_consumption_raw=None,
        total_battery_capacity_kwh=None, last_charge_ending_power_kwh=27.1,
        fota_lowest_voltage_raw=None, status_time=1794043000,
    )
    base.update(kw)
    return ChargeStatus(**base)


def make_status(**kw) -> Status:
    base = dict(
        status_time=1794043000, locked=True, driver_door_open=False,
        passenger_door_open=False, rear_left_door_open=False, rear_right_door_open=False,
        boot_open=False, bonnet_open=False, driver_window_open=False,
        passenger_window_open=False, rear_left_window_open=False,
        rear_right_window_open=False, climate_running=False,
        interior_temperature=31.0, exterior_temperature=29.0, fuel_level=72,
        range_km=240, odometer_km=8450, aux_battery_voltage=12.6,
        front_left_tyre_psi=36.0, front_right_tyre_psi=36.2,
        rear_left_tyre_psi=35.8, rear_right_tyre_psi=36.0,
        gps=GpsPosition(latitude=11.05, longitude=76.07, gps_status=GpsStatus.FIX_3D, speed_kmh=0.0),
        charge=make_charge(),
    )
    base.update(kw)
    return Status(**base)


@pytest.fixture
def mock_client():
    vehicle = Vehicle(vin=VIN, name="Windsor", brand="MG", model="Windsor", color_name="Clay Beige", series="EQ100")
    client = MagicMock()
    client.vehicle = None
    client.uid = None
    client.token = None
    client.has_pin = True
    client.capabilities = Capabilities(climate=True, door_lock=True, find_my_car=True, tailgate=True)

    async def _vehicles():
        client.vehicle = vehicle
        client.vin = VIN
        return [vehicle]

    client.login = AsyncMock()
    client.vehicles = AsyncMock(side_effect=_vehicles)
    client.verify_pin = AsyncMock()
    client.refresh_capabilities = AsyncMock(return_value=client.capabilities)
    client.status = AsyncMock(return_value=make_status())
    client.control_door_lock = AsyncMock()
    client.control_climate = AsyncMock()
    client.find_my_car = AsyncMock()
    client.release_tailgate = AsyncMock()
    with (
        patch("custom_components.mg_ismart_india.coordinator.MgIndiaClient", return_value=client),
        patch("custom_components.mg_ismart_india.config_flow.MgIndiaClient", return_value=client),
    ):
        yield client
