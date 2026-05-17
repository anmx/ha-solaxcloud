# custom_components/solaxcloud/sensor.py
"""Sensor platform for SolaXCloud — inverter and battery telemetry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import BatteryRealtimeData, InverterRealtimeData, PlantRealtimeData
from .const import DOMAIN
from .coordinator import SolaxCloudCoordinator
from .entity import SolaxCloudEntity

_LOGGER = logging.getLogger(__name__)

# Typing alias for the value-extractor callables used in descriptions.
_InverterValueFn = Callable[[InverterRealtimeData], Any]
_BatteryValueFn = Callable[[BatteryRealtimeData], Any]
_PlantValueFn = Callable[[PlantRealtimeData], Any]


def _parse_data_time(value: str) -> datetime | None:
    """Parse a SolaXCloud ``dataTime`` string into an aware UTC datetime.

    The API returns timestamps in ISO 8601 format with an explicit offset,
    e.g. ``"2026-05-03T10:59:56.000+00:00"``.  Home Assistant requires
    ``TIMESTAMP`` sensors to provide timezone-aware ``datetime`` objects.

    Returns ``None`` if the string is empty or cannot be parsed, which causes
    HA to show the sensor as unavailable rather than raising an exception.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        # Normalise to UTC regardless of the offset in the string.
        return dt.astimezone(UTC)
    except ValueError:
        _LOGGER.debug("SolaXCloud: could not parse dataTime %r", value)
        return None


# ---------------------------------------------------------------------------
# Entity description dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True, frozen=True)
class SolaxCloudInverterSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Describes a single inverter sensor.

    ``value_fn`` extracts the sensor value from the realtime data object.
    """

    value_fn: _InverterValueFn = lambda _: None


@dataclass(slots=True, kw_only=True, frozen=True)
class SolaxCloudBatterySensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Describes a single battery sensor."""

    value_fn: _BatteryValueFn = lambda _: None


@dataclass(slots=True, kw_only=True, frozen=True)
class SolaxCloudPlantSensorDescription(SensorEntityDescription):  # type: ignore[misc]
    """Describes a single plant-level sensor."""

    value_fn: _PlantValueFn = lambda _: None


# ---------------------------------------------------------------------------
# Inverter sensor descriptions
# ---------------------------------------------------------------------------

INVERTER_SENSORS: tuple[SolaxCloudInverterSensorDescription, ...] = (
    SolaxCloudInverterSensorDescription(
        key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.grid_power,
    ),
    SolaxCloudInverterSensorDescription(
        key="today_import_energy",
        translation_key="today_import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.today_import_energy,
    ),
    SolaxCloudInverterSensorDescription(
        key="total_import_energy",
        translation_key="total_import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_import_energy,
    ),
    SolaxCloudInverterSensorDescription(
        key="today_export_energy",
        translation_key="today_export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.today_export_energy,
    ),
    SolaxCloudInverterSensorDescription(
        key="total_export_energy",
        translation_key="total_export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_export_energy,
    ),
    # AC phase voltages
    SolaxCloudInverterSensorDescription(
        key="ac_voltage1",
        translation_key="ac_voltage1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_voltage1,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_voltage2",
        translation_key="ac_voltage2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_voltage2,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_voltage3",
        translation_key="ac_voltage3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_voltage3,
    ),
    # AC phase currents
    SolaxCloudInverterSensorDescription(
        key="ac_current1",
        translation_key="ac_current1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_current1,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_current2",
        translation_key="ac_current2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_current2,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_current3",
        translation_key="ac_current3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_current3,
    ),
    # AC phase powers
    SolaxCloudInverterSensorDescription(
        key="ac_power1",
        translation_key="ac_power1",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_power1,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_power2",
        translation_key="ac_power2",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_power2,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_power3",
        translation_key="ac_power3",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_power3,
    ),
    # AC frequencies
    SolaxCloudInverterSensorDescription(
        key="ac_frequency1",
        translation_key="ac_frequency1",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_frequency1,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_frequency2",
        translation_key="ac_frequency2",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_frequency2,
    ),
    SolaxCloudInverterSensorDescription(
        key="ac_frequency3",
        translation_key="ac_frequency3",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.ac_frequency3,
    ),
    SolaxCloudInverterSensorDescription(
        key="total_power_factor",
        translation_key="total_power_factor",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value_fn=lambda d: d.total_power_factor,
    ),
    SolaxCloudInverterSensorDescription(
        key="inverter_temperature",
        translation_key="inverter_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.inverter_temperature,
    ),
    # Daily / total production
    SolaxCloudInverterSensorDescription(
        key="daily_ac_output",
        translation_key="daily_ac_output",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_ac_output,
    ),
    SolaxCloudInverterSensorDescription(
        key="total_ac_output",
        translation_key="total_ac_output",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_ac_output,
    ),
    SolaxCloudInverterSensorDescription(
        key="daily_yield",
        translation_key="daily_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_yield,
    ),
    SolaxCloudInverterSensorDescription(
        key="total_yield",
        translation_key="total_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_yield,
    ),
    # MPPT strings
    SolaxCloudInverterSensorDescription(
        key="mppt1_voltage",
        translation_key="mppt1_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt1_voltage,
    ),
    SolaxCloudInverterSensorDescription(
        key="mppt1_current",
        translation_key="mppt1_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt1_current,
    ),
    SolaxCloudInverterSensorDescription(
        key="mppt1_power",
        translation_key="mppt1_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt1_power,
    ),
    SolaxCloudInverterSensorDescription(
        key="mppt2_voltage",
        translation_key="mppt2_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt2_voltage,
    ),
    SolaxCloudInverterSensorDescription(
        key="mppt2_current",
        translation_key="mppt2_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt2_current,
    ),
    SolaxCloudInverterSensorDescription(
        key="mppt2_power",
        translation_key="mppt2_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.mppt.mppt2_power,
    ),
    SolaxCloudInverterSensorDescription(
        key="last_data_update",
        translation_key="last_data_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _parse_data_time(d.data_time),
    ),
)


# ---------------------------------------------------------------------------
# Battery sensor descriptions
# ---------------------------------------------------------------------------

BATTERY_SENSORS: tuple[SolaxCloudBatterySensorDescription, ...] = (
    SolaxCloudBatterySensorDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_soc,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_soh",
        translation_key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_soh,
    ),
    SolaxCloudBatterySensorDescription(
        key="charge_discharge_power",
        translation_key="charge_discharge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.charge_discharge_power,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_voltage,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_current",
        translation_key="battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_current,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_temperature",
        translation_key="battery_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_temperature,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_cycle_times",
        translation_key="battery_cycle_times",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.battery_cycle_times,
    ),
    SolaxCloudBatterySensorDescription(
        key="total_device_discharge",
        translation_key="total_device_discharge",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_device_discharge,
    ),
    SolaxCloudBatterySensorDescription(
        key="total_device_charge",
        translation_key="total_device_charge",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_device_charge,
    ),
    SolaxCloudBatterySensorDescription(
        key="battery_remainings",
        translation_key="battery_remainings",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery_remainings,
    ),
    SolaxCloudBatterySensorDescription(
        key="last_data_update",
        translation_key="last_data_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _parse_data_time(d.data_time),
    ),
)


# ---------------------------------------------------------------------------
# Plant sensor descriptions
# ---------------------------------------------------------------------------

PLANT_SENSORS: tuple[SolaxCloudPlantSensorDescription, ...] = (
    # Production
    SolaxCloudPlantSensorDescription(
        key="plant_daily_yield",
        translation_key="plant_daily_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_yield,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_yield",
        translation_key="plant_total_yield",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_yield,
    ),
    # Battery
    SolaxCloudPlantSensorDescription(
        key="plant_daily_charged",
        translation_key="plant_daily_charged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_charged,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_charged",
        translation_key="plant_total_charged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_charged,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_daily_discharged",
        translation_key="plant_daily_discharged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_discharged,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_discharged",
        translation_key="plant_total_discharged",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_discharged,
    ),
    # Grid exchange
    SolaxCloudPlantSensorDescription(
        key="plant_daily_imported",
        translation_key="plant_daily_imported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_imported,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_imported",
        translation_key="plant_total_imported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_imported,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_daily_exported",
        translation_key="plant_daily_exported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_exported,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_exported",
        translation_key="plant_total_exported",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_exported,
    ),
    # Earnings (dimensionless — currency unit varies per plant)
    SolaxCloudPlantSensorDescription(
        key="plant_daily_earnings",
        translation_key="plant_daily_earnings",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.daily_earnings,
    ),
    SolaxCloudPlantSensorDescription(
        key="plant_total_earnings",
        translation_key="plant_total_earnings",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_earnings,
    ),
)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SolaXCloud sensor entities from a config entry."""
    from . import SolaxCloudRuntimeData  # local import to avoid circular

    runtime: SolaxCloudRuntimeData = entry.runtime_data
    coordinator = runtime.coordinator
    data = coordinator.data

    entities: list[SolaxCloudEntity] = []

    # --- Inverter sensors ---------------------------------------------------
    # Build a lookup: device_sn -> InverterInfo (for stable device metadata).
    inverter_info_map = {inv.device_sn: inv for inv in data.inverters}

    for rt in data.inverter_realtime:
        inv_info = inverter_info_map.get(rt.device_sn)
        device_info = DeviceInfo(
            identifiers={(DOMAIN, rt.device_sn)},
            name=f"solax_inverter_{rt.device_sn}",
            manufacturer="SolaX Power",
            model=str(inv_info.device_model) if inv_info else None,
            sw_version=(
                f"ARM {inv_info.arm_version} / DSP {inv_info.dsp_version}"
                if inv_info
                else None
            ),
            serial_number=inv_info.register_no if inv_info else None,
            configuration_url=entry.data.get("base_url"),
        )
        for description in INVERTER_SENSORS:
            entities.append(
                SolaxCloudInverterSensor(
                    coordinator=coordinator,
                    description=description,
                    device_sn=rt.device_sn,
                    device_info=device_info,
                )
            )

    # --- Battery sensors ----------------------------------------------------
    battery_info_map = {bat.device_sn: bat for bat in data.batteries}

    for rt in data.battery_realtime:
        bat_info = battery_info_map.get(rt.device_sn)
        device_info = DeviceInfo(
            identifiers={(DOMAIN, rt.device_sn)},
            name=f"solax_battery_{rt.device_sn}",
            manufacturer="SolaX Power",
            model=str(bat_info.device_model) if bat_info else None,
            sw_version=bat_info.software_version if bat_info else None,
            hw_version=bat_info.hardware_version if bat_info else None,
            serial_number=bat_info.register_no if bat_info else None,
            configuration_url=entry.data.get("base_url"),
        )
        for description in BATTERY_SENSORS:
            entities.append(
                SolaxCloudBatterySensor(
                    coordinator=coordinator,
                    description=description,
                    device_sn=rt.device_sn,
                    device_info=device_info,
                )
            )

    # --- Plant sensors ------------------------------------------------------
    plant_info_map = {p.plant_id: p for p in data.plants}

    for rt in data.plant_realtime:
        plant_info = plant_info_map.get(rt.plant_id)
        plant_name = plant_info.plant_name if plant_info else rt.plant_id
        device_info = DeviceInfo(
            identifiers={(DOMAIN, rt.plant_id)},
            name=f"solax_plant_{plant_name}",
            manufacturer="SolaX Power",
            configuration_url=entry.data.get("base_url"),
        )
        for description in PLANT_SENSORS:
            entities.append(
                SolaxCloudPlantSensor(
                    coordinator=coordinator,
                    description=description,
                    plant_id=rt.plant_id,
                    device_info=device_info,
                )
            )

    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Entity classes
# ---------------------------------------------------------------------------


class SolaxCloudInverterSensor(SolaxCloudEntity, SensorEntity):  # type: ignore[misc]
    """A sensor tracking one field of an inverter's realtime data."""

    entity_description: SolaxCloudInverterSensorDescription

    def __init__(
        self,
        coordinator: SolaxCloudCoordinator,
        description: SolaxCloudInverterSensorDescription,
        device_sn: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_sn = device_sn
        self._attr_unique_id = f"{device_sn}_{description.key}"
        self._attr_device_info = device_info

    @property
    def _realtime(self) -> InverterRealtimeData | None:
        """Return the latest realtime record for this device, or None."""
        for rt in self.coordinator.data.inverter_realtime:
            if rt.device_sn == self._device_sn:
                return rt  # type: ignore[no-any-return]
        return None

    @property
    def native_value(self) -> Any:
        """Return the sensor value extracted from the realtime data."""
        rt = self._realtime
        if rt is None:
            return None
        return self.entity_description.value_fn(rt)

    @property
    def available(self) -> bool:
        """Return True only when the coordinator has data for this device."""
        return self.coordinator.last_update_success and self._realtime is not None


class SolaxCloudBatterySensor(SolaxCloudEntity, SensorEntity):  # type: ignore[misc]
    """A sensor tracking one field of a battery's realtime data."""

    entity_description: SolaxCloudBatterySensorDescription

    def __init__(
        self,
        coordinator: SolaxCloudCoordinator,
        description: SolaxCloudBatterySensorDescription,
        device_sn: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_sn = device_sn
        self._attr_unique_id = f"{device_sn}_{description.key}"
        self._attr_device_info = device_info

    @property
    def _realtime(self) -> BatteryRealtimeData | None:
        """Return the latest realtime record for this device, or None."""
        for rt in self.coordinator.data.battery_realtime:
            if rt.device_sn == self._device_sn:
                return rt  # type: ignore[no-any-return]
        return None

    @property
    def native_value(self) -> Any:
        """Return the sensor value extracted from the realtime data."""
        rt = self._realtime
        if rt is None:
            return None
        return self.entity_description.value_fn(rt)

    @property
    def available(self) -> bool:
        """Return True only when the coordinator has data for this device."""
        return self.coordinator.last_update_success and self._realtime is not None


class SolaxCloudPlantSensor(SolaxCloudEntity, SensorEntity):  # type: ignore[misc]
    """A sensor tracking one field of a plant's realtime data."""

    entity_description: SolaxCloudPlantSensorDescription

    def __init__(
        self,
        coordinator: SolaxCloudCoordinator,
        description: SolaxCloudPlantSensorDescription,
        plant_id: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._plant_id = plant_id
        self._attr_unique_id = f"{plant_id}_{description.key}"
        self._attr_device_info = device_info

    @property
    def _realtime(self) -> PlantRealtimeData | None:
        """Return the latest realtime record for this plant, or None."""
        for rt in self.coordinator.data.plant_realtime:
            if rt.plant_id == self._plant_id:
                return rt  # type: ignore[no-any-return]
        return None

    @property
    def native_value(self) -> Any:
        """Return the sensor value extracted from the realtime data."""
        rt = self._realtime
        if rt is None:
            return None
        return self.entity_description.value_fn(rt)

    @property
    def available(self) -> bool:
        """Return True only when the coordinator has data for this plant."""
        return self.coordinator.last_update_success and self._realtime is not None
