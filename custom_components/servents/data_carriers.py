from __future__ import annotations

from typing import Any, Literal, TypeVar

from homeassistant.helpers.device_registry import DeviceInfo
from serde import from_dict

from servents.data_model.entity_configs import (
    BinarySensorConfig,
    ButtonConfig,
    DeviceConfig,
    EntityConfig,
    NumberConfig,
    SelectConfig,
    SensorConfig,
    SwitchConfig,
    ThresholdBinarySensorConfig,
)

from .const import (
    DOMAIN,
)

AllowedEntityTypes = Literal["sensor", "binary_sensor", "threshold", "switch", "number", "button", "select"]


EntityTypeToDataclassMap: dict[AllowedEntityTypes, type] = {
    "sensor": SensorConfig,
    "binary_sensor": BinarySensorConfig,
    "threshold": ThresholdBinarySensorConfig,
    "switch": SwitchConfig,
    "number": NumberConfig,
    "button": ButtonConfig,
    "select": SelectConfig,
}

T = TypeVar("T")


def deserialize(data: dict[str, Any]) -> EntityConfig:
    entity_type = data.get("entity_type", None)

    if not entity_type:
        raise Exception("Definition is missing the entity_type field")

    if entity_type not in EntityTypeToDataclassMap:
        raise Exception(f"entity type: {entity_type} is not supported")

    return from_dict(EntityTypeToDataclassMap[entity_type], data)


def get_hass_device_info(device_config: DeviceConfig) -> DeviceInfo | None:
    return DeviceInfo(
        identifiers={(DOMAIN, device_config.device_id)},
        name=device_config.name,
        manufacturer=device_config.manufacturer or "ServEnts",
        model=device_config.model or "Virtual Device",
        sw_version=device_config.version,
    )
