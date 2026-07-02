"""Parse-layer between service-call payloads and the shared servents-data-model.

Payloads are deserialized with ``serde.from_dict`` on the shared config
classes, so required-field and ``Literal`` validation happen at parse time
and the nested ``device_definition`` dict becomes a ``DeviceConfig``
natively. Unknown keys (e.g. Domovoy's ``app_name``/``is_global`` before
they were modeled) are ignored by pyserde, never rejected.
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from serde import SerdeError, from_dict
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
from servents.data_model.entity_types import EntityType
from servents.data_model.update_entity import ServentUpdateEntity

from .const import (
    DOMAIN,
)

ENTITY_TYPE_TO_CONFIG_CLASS: dict[EntityType, type[EntityConfig]] = {
    EntityType.SENSOR: SensorConfig,
    EntityType.BINARY_SENSOR: BinarySensorConfig,
    EntityType.THRESHOLD_BINARY_SENSOR: ThresholdBinarySensorConfig,
    EntityType.SWITCH: SwitchConfig,
    EntityType.NUMBER: NumberConfig,
    EntityType.BUTTON: ButtonConfig,
    EntityType.SELECT: SelectConfig,
}


def parse_entity_config(data: Mapping[str, Any]) -> EntityConfig:
    entity_type_raw = data.get("entity_type", None)

    if not entity_type_raw:
        raise ServiceValidationError("Definition is missing the entity_type field")

    try:
        entity_type = EntityType(entity_type_raw)
    except ValueError:
        raise ServiceValidationError(f"entity type: {entity_type_raw} is not supported") from None

    # Legacy alias: services.yaml historically documented the nested device
    # payload as `device_config`. Domovoy sends `device_definition`.
    if data.get("device_config") and not data.get("device_definition"):
        data = {**data, "device_definition": data["device_config"]}

    try:
        return from_dict(ENTITY_TYPE_TO_CONFIG_CLASS[entity_type], data)
    except (SerdeError, ValueError) as err:
        raise ServiceValidationError(f"Invalid {entity_type.value} entity definition: {err}") from err


def parse_update_entity(data: Mapping[str, Any]) -> ServentUpdateEntity:
    try:
        return from_dict(ServentUpdateEntity, data)
    except (SerdeError, ValueError) as err:
        raise ServiceValidationError(f"Invalid update_state payload: {err}") from err


def get_device_id(device: DeviceConfig) -> str:
    # The "device-" prefix is frozen wire format: existing registry entries
    # and automations reference it, and Domovoy relies on it staying stable.
    return f"device-{device.device_id}"


def get_device_info(device: DeviceConfig) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, get_device_id(device))},
        name=device.name,
        manufacturer=device.manufacturer or "ServEnts",
        model=device.model or "Virtual Device",
        sw_version=device.version,
    )
