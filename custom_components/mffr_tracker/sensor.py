from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_SLOT_START,
    ATTR_SLOT_END,
    ATTR_MFFR_PRICE,
    ATTR_NORDPOOL_PRICE,
    ATTR_ENERGY_KWH,
    ATTR_DURATION_MIN,
    ATTR_WAS_BACKUP,
    ATTR_CANCELLED,
    ATTR_BASELINE_W,
    ATTR_MFFR_POWER_W,
)
from .coordinator import MFFRCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: MFFRCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    # Signal is read directly from the configured mode entity; no separate signal sensor is exposed.
    entities.append(MFFRPowerSensor(coordinator, entry))
    entities.append(MFFRSlotEnergySensor(coordinator, entry))
    entities.append(MFFRSlotProfitSensor(coordinator, entry))
    entities.append(MFFRTodayProfitSensor(coordinator, entry))
    entities.append(MFFRWeekProfitSensor(coordinator, entry))
    entities.append(MFFRMonthProfitSensor(coordinator, entry))
    entities.append(MFFRUpCountSensor(coordinator, entry))
    entities.append(MFFRDownCountSensor(coordinator, entry))
    entities.append(MFFRRecentSlotsSensor(coordinator, entry))
    async_add_entities(entities)


class BaseMFFRSensor(CoordinatorEntity[MFFRCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MFFRCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="MFFR Profit Tracker",
            manufacturer="MFFR",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        slot_start: datetime | None = data.get("slot_start")
        slot_end: datetime | None = data.get("slot_end")
        attrs = {
            ATTR_SLOT_START: slot_start.isoformat() if isinstance(slot_start, datetime) else None,
            ATTR_SLOT_END: slot_end.isoformat() if isinstance(slot_end, datetime) else None,
            ATTR_MFFR_PRICE: data.get("mffr_price"),
            ATTR_NORDPOOL_PRICE: data.get("nordpool_price"),
            ATTR_ENERGY_KWH: data.get("slot_energy_kwh"),
            ATTR_DURATION_MIN: data.get("duration_minutes"),
            ATTR_WAS_BACKUP: data.get("was_backup"),
            ATTR_CANCELLED: data.get("cancelled"),
            ATTR_BASELINE_W: data.get("baseline_w"),
            ATTR_MFFR_POWER_W: data.get("mffr_power_w"),
        }
        return attrs


class MFFRPowerSensor(BaseMFFRSensor):
    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_power"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("mffr_power_w")


class MFFRSlotEnergySensor(BaseMFFRSensor):
    _attr_name = "Slot Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_slot_energy"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("slot_energy_kwh")


class MFFRSlotProfitSensor(BaseMFFRSensor):
    _attr_name = "Slot Profit"
    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = "€"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_slot_profit"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("slot_profit")


class MFFRTodayProfitSensor(BaseMFFRSensor):
    _attr_name = "Today Profit"
    _attr_icon = "mdi:calendar-today"
    _attr_native_unit_of_measurement = "€"
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_today_profit"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("today_profit")


class MFFRWeekProfitSensor(BaseMFFRSensor):
    _attr_name = "Week Profit"
    _attr_icon = "mdi:calendar-week"
    _attr_native_unit_of_measurement = "€"
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_week_profit"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("week_profit")


class MFFRMonthProfitSensor(BaseMFFRSensor):
    _attr_name = "Month Profit"
    _attr_icon = "mdi:calendar-month"
    _attr_native_unit_of_measurement = "€"
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_month_profit"

    @property
    def native_value(self) -> float | None:
        return (self.coordinator.data or {}).get("month_profit")


class MFFRRecentSlotsSensor(BaseMFFRSensor):
    _attr_name = "Recent Slots"
    _attr_icon = "mdi:history"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_recent_slots"

    @property
    def native_value(self) -> int | None:
        rs = (self.coordinator.data or {}).get("recent_slots") or []
        return len(rs)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = super().extra_state_attributes or {}
        slots = (self.coordinator.data or {}).get("recent_slots") or []
        lines = [
            "| Timeslot | Signal | Energy (kWh) | Profit (€) | Backup | Cancelled |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for s in slots[:12]:
            lines.append(
                f"| {s.get('timeslot')} | {s.get('signal')} | {s.get('energy_kwh')} | {s.get('profit')} | {int(bool(s.get('was_backup')))} | {int(bool(s.get('cancelled')))} |"
            )
        attrs["slots_table"] = "\n".join(lines)
        return attrs


class MFFRUpCountSensor(BaseMFFRSensor):
    _attr_name = "UP Count Today"
    _attr_icon = "mdi:arrow-up-bold"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_up_count"

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("up_count")


class MFFRDownCountSensor(BaseMFFRSensor):
    _attr_name = "DOWN Count Today"
    _attr_icon = "mdi:arrow-down-bold"

    @property
    def unique_id(self) -> str:
        return f"{self._entry.entry_id}_down_count"

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("down_count")
