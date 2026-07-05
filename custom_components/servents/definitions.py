"""Parse-layer between service-call payloads and the shared servents-data-model.

Payloads are deserialized with ``serde.from_dict`` on the shared config
classes, so required-field and ``Literal`` validation happen at parse time
and the nested ``device_definition`` dict becomes a ``DeviceConfig``
natively. Unknown keys (e.g. Domovoy's ``app_name``/``is_global`` before
they were modeled) are ignored by pyserde, never rejected.
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.const import Platform
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from serde import SerdeError, from_dict
from servents.data_model.entity_configs import (
    BinarySensorConfig,
    ButtonConfig,
    ClimateConfig,
    CoverConfig,
    DateConfig,
    DatetimeConfig,
    DeviceConfig,
    EntityConfig,
    EventConfig,
    FanConfig,
    LightConfig,
    LockConfig,
    NumberConfig,
    SelectConfig,
    SensorConfig,
    SirenConfig,
    SwitchConfig,
    TextConfig,
    ThresholdBinarySensorConfig,
    TimeConfig,
    ValveConfig,
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
    EntityType.CLIMATE: ClimateConfig,
    EntityType.LIGHT: LightConfig,
    EntityType.COVER: CoverConfig,
    EntityType.FAN: FanConfig,
    EntityType.LOCK: LockConfig,
    EntityType.VALVE: ValveConfig,
    EntityType.SIREN: SirenConfig,
    EntityType.TEXT: TextConfig,
    EntityType.DATE: DateConfig,
    EntityType.TIME: TimeConfig,
    EntityType.DATETIME: DatetimeConfig,
    EntityType.EVENT: EventConfig,
}

ENTITY_TYPE_TO_HA_DOMAIN: dict[EntityType, str] = {
    EntityType.BINARY_SENSOR: Platform.BINARY_SENSOR,
    EntityType.BUTTON: Platform.BUTTON,
    EntityType.CLIMATE: Platform.CLIMATE,
    EntityType.COVER: Platform.COVER,
    EntityType.DATE: Platform.DATE,
    EntityType.DATETIME: Platform.DATETIME,
    EntityType.EVENT: Platform.EVENT,
    EntityType.FAN: Platform.FAN,
    EntityType.LIGHT: Platform.LIGHT,
    EntityType.LOCK: Platform.LOCK,
    EntityType.NUMBER: Platform.NUMBER,
    EntityType.SELECT: Platform.SELECT,
    EntityType.SENSOR: Platform.SENSOR,
    EntityType.SIREN: Platform.SIREN,
    EntityType.SWITCH: Platform.SWITCH,
    EntityType.TEXT: Platform.TEXT,
    EntityType.THRESHOLD_BINARY_SENSOR: Platform.BINARY_SENSOR,
    EntityType.TIME: Platform.TIME,
    EntityType.VALVE: Platform.VALVE,
}


def parse_entity_config(data: Mapping[str, Any]) -> EntityConfig:
    entity_type_raw = data.get("entity_type", None)

    if not entity_type_raw:
        raise ServiceValidationError("Definition is missing the entity_type field")

    try:
        entity_type = EntityType(entity_type_raw)
    except ValueError:
        raise ServiceValidationError(f"entity type: {entity_type_raw} is not supported") from None

    config_class = ENTITY_TYPE_TO_CONFIG_CLASS.get(entity_type)
    if config_class is None:
        raise ServiceValidationError(f"entity type: {entity_type_raw} is not supported")

    # Legacy alias: services.yaml historically documented the nested device
    # payload as `device_config`. Domovoy sends `device_definition`.
    if data.get("device_config") and not data.get("device_definition"):
        data = {**data, "device_definition": data["device_config"]}

    try:
        return from_dict(config_class, data)
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


def ha_domain_for_entity_type(entity_type: EntityType) -> str:
    """Return the Home Assistant platform domain for a ServEnt entity type."""
    return ENTITY_TYPE_TO_HA_DOMAIN[entity_type]


def ha_domain_for_definition(definition: EntityConfig) -> str:
    """Return the Home Assistant platform domain for a parsed definition."""
    return ha_domain_for_entity_type(EntityType(definition.entity_type))


def servent_unique_id(servent_id: str) -> str:
    """Return the frozen Home Assistant unique_id for a ServEnt entity."""
    return f"sensor-{servent_id}"


def get_device_info(device: DeviceConfig) -> DeviceInfo:
    info: DeviceInfo = {
        "identifiers": {(DOMAIN, get_device_id(device))},
        "name": device.name,
        "manufacturer": device.manufacturer or "ServEnts",
        "model": device.model or "Virtual Device",
    }

    optional_fields = {
        "configuration_url": device.configuration_url,
        "hw_version": device.hw_version,
        "serial_number": device.serial_number,
        "suggested_area": device.suggested_area,
        "sw_version": device.sw_version or device.version,
    }
    info.update({key: value for key, value in optional_fields.items() if value is not None})
    return info
