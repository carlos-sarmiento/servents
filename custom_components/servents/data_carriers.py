from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
)

AllowedEntityTypes = Literal[
    "sensor", "binary_sensor", "threshold_binary_sensor", "switch", "number", "button", "select"
]


@dataclass
class BaseServentEntityDefinition:
    entity_type: AllowedEntityTypes
    servent_id: str
    name: str
    device_definition: ServentDeviceDefinition | None
    entity_category: str | None
    fixed_attributes: dict[str, Any] = field(default_factory=dict)
    default_state: Any | None = None
    disabled_by_default: bool = False


@dataclass
class ServentDeviceDefinition:
    device_id: str = ""
    name: str = ""
    manufacturer: str | None = None
    model: str | None = None
    version: str | None = None

    def get_device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, self.get_device_id())},
            name=self.name,
            manufacturer=self.manufacturer or "ServEnts",
            model=self.model or "Virtual Device",
            sw_version=self.version,
        )

    def get_device_id(self) -> str:
        return f"device-{self.device_id}"


@dataclass
class ServentSensorDefinition(BaseServentEntityDefinition):
    device_class: str | None = None
    unit_of_measurement: str | None = None
    state_class: str | None = None
    enum_options: list[str] | None = None


@dataclass
class ServentSwitchDefinition(BaseServentEntityDefinition):
    device_class: str | None = None


@dataclass
class ServentSelectDefinition(BaseServentEntityDefinition):
    enum_options: list[str] = field(default_factory=list)


@dataclass
class ServentNumberDefinition(BaseServentEntityDefinition):
    device_class: str | None = None
    unit_of_measurement: str | None = None
    number_mode: str = "auto"
    max_value: float = 100
    min_value: float = 0
    step: float = 1


@dataclass
class ServentButtonDefinition(BaseServentEntityDefinition):
    device_class: str | None = None
    event: str = ""
    event_data: dict = field(default_factory=dict)


@dataclass
class ServentBinarySensorDefinition(BaseServentEntityDefinition):
    device_class: str | None = None


@dataclass
class ServentThresholdBinarySensorDefinition(BaseServentEntityDefinition):
    device_class: str | None = None
    entity_id: str = ""
    lower: float | None = None
    upper: float | None = None
    hysteresis: float = 0


EntityTypeToDataclassMap: dict[AllowedEntityTypes, type] = {
    "sensor": ServentSensorDefinition,
    "binary_sensor": ServentBinarySensorDefinition,
    "threshold_binary_sensor": ServentThresholdBinarySensorDefinition,
    "switch": ServentSwitchDefinition,
    "number": ServentNumberDefinition,
    "button": ServentButtonDefinition,
    "select": ServentSelectDefinition,
}


def to_dataclass(data: dict[str, Any]) -> BaseServentEntityDefinition:
    entity_type = data.get("entity_type", None)

    if not entity_type:
        raise Exception("Definition is missing the entity_type field")

    if entity_type not in EntityTypeToDataclassMap:
        raise Exception(f"entity type: {entity_type} is not supported")

    if "device_definition" in data and data["device_definition"]:
        data["device_definition"] = ServentDeviceDefinition(**data["device_definition"])

    builder = EntityTypeToDataclassMap[entity_type]

    return builder(**data)
