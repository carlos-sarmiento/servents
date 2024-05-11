from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from homeassistant.helpers.entity import DeviceInfo

from .const import (
    DOMAIN,
)

AllowedEntityTypes = Literal["sensor", "binary_sensor", "threshold", "switch", "number", "button", "select"]


@dataclass
class BaseServentEntityDefinition:
    entity_type: AllowedEntityTypes
    servent_id: str
    name: str
    device_definition: ServentDeviceDefinition | None = None
    entity_category: str | None = None
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
    options: list[str] | None = None


@dataclass
class ServentSwitchDefinition(BaseServentEntityDefinition):
    device_class: str | None = None


@dataclass
class ServentSelectDefinition(BaseServentEntityDefinition):
    options: list[str] = field(default_factory=list)


@dataclass
class ServentNumberDefinition(BaseServentEntityDefinition):
    device_class: str | None = None
    unit_of_measurement: str | None = None
    mode: str | None = None
    max_value: float | None = None
    min_value: float | None = None
    step: float | None = None


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
    "threshold": ServentThresholdBinarySensorDefinition,
    "switch": ServentSwitchDefinition,
    "number": ServentNumberDefinition,
    "button": ServentButtonDefinition,
    "select": ServentSelectDefinition,
}

T = TypeVar("T")
_LOGGER = logging.getLogger(__name__)


def to_dataclass(data: dict[str, Any]) -> BaseServentEntityDefinition:
    entity_type = data.get("entity_type", None)

    if not entity_type:
        raise Exception("Definition is missing the entity_type field")

    if entity_type not in EntityTypeToDataclassMap:
        raise Exception(f"entity type: {entity_type} is not supported")

    if "device_config" in data and data["device_config"]:
        data["device_definition"] = clean_params_and_build(ServentDeviceDefinition, data["device_config"])

    builder = EntityTypeToDataclassMap[entity_type]

    return clean_params_and_build(builder, data)


@dataclass
class ServentUpdateEntityDefinition:
    servent_id: str
    state: Any | None
    attributes: dict = field(default_factory=dict)


def clean_params_and_build(builder: type[T], data: dict) -> T:
    # remove whatever extraneous information might be on the dict that is not part of the constructor
    clean_data = {k: v for k, v in data.items() if k in inspect.signature(builder).parameters}
    return builder(**clean_data)
