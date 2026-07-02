"""Tests for definitions.py: dict → shared-model config parsing.

Successor to the data_carriers.py characterization tests. The parse layer
now uses serde.from_dict on servents-data-model classes, which is stricter
than the old hand-rolled dataclasses: the lenient-default tests from the
old suite were consciously flipped per the behavioral-deltas table in
FABLE-AUDIT.md (WP3).
"""

import pytest
from homeassistant.exceptions import ServiceValidationError
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

from custom_components.servents.definitions import (
    ENTITY_TYPE_TO_CONFIG_CLASS,
    get_device_id,
    get_device_info,
    parse_entity_config,
    parse_update_entity,
)


class TestParseEntityConfig:
    def test_missing_entity_type_raises(self):
        with pytest.raises(ServiceValidationError, match="missing the entity_type field"):
            parse_entity_config({"servent_id": "x", "name": "X"})

    def test_empty_entity_type_raises(self):
        with pytest.raises(ServiceValidationError, match="missing the entity_type field"):
            parse_entity_config({"entity_type": "", "servent_id": "x", "name": "X"})

    def test_unsupported_entity_type_raises(self):
        with pytest.raises(ServiceValidationError, match="entity type: light is not supported"):
            parse_entity_config({"entity_type": "light", "servent_id": "x", "name": "X"})

    @pytest.mark.parametrize(
        ("payload_extra", "entity_type", "expected_class"),
        [
            ({}, "sensor", SensorConfig),
            ({}, "binary_sensor", BinarySensorConfig),
            ({"entity_id": "sensor.src", "lower": 1.0}, "threshold", ThresholdBinarySensorConfig),
            ({}, "switch", SwitchConfig),
            ({"mode": "auto"}, "number", NumberConfig),
            ({"event": "e"}, "button", ButtonConfig),
            ({"options": ["a"]}, "select", SelectConfig),
        ],
    )
    def test_maps_entity_type_to_config_class(self, payload_extra, entity_type, expected_class):
        result = parse_entity_config({"entity_type": entity_type, "servent_id": "x", "name": "X", **payload_extra})
        assert type(result) is expected_class
        assert isinstance(result, EntityConfig)
        assert result.servent_id == "x"
        assert result.name == "X"

    def test_dispatch_map_covers_every_entity_type(self):
        assert set(ENTITY_TYPE_TO_CONFIG_CLASS.keys()) == set(EntityType)

    def test_extraneous_keys_are_ignored(self):
        # pyserde silently ignores unknown keys — same lenience as the old
        # clean_params_and_build (Domovoy constraint 8: never reject extras).
        result = parse_entity_config(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "not_a_field": "ignored",
                "another_bogus": 42,
            }
        )
        assert not hasattr(result, "not_a_field")
        assert result.servent_id == "x"

    def test_device_config_key_builds_device_definition(self):
        # Legacy alias documented in services.yaml; Domovoy itself sends
        # device_definition.
        result = parse_entity_config(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "device_config": {"device_id": "dev1", "name": "My Device", "manufacturer": "Acme"},
            }
        )
        assert isinstance(result.device_definition, DeviceConfig)
        assert result.device_definition.device_id == "dev1"
        assert result.device_definition.name == "My Device"
        assert result.device_definition.manufacturer == "Acme"

    def test_device_definition_key_builds_device_definition_natively(self):
        # H8 fixed structurally: from_dict deserializes the nested dict that
        # Domovoy sends under device_definition — no coercion step needed.
        result = parse_entity_config(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "device_definition": {"device_id": "dev1", "name": "My Device", "bogus": 1},
            }
        )
        assert isinstance(result.device_definition, DeviceConfig)
        assert result.device_definition.device_id == "dev1"
        assert not hasattr(result.device_definition, "bogus")

    def test_empty_device_config_is_ignored(self):
        result = parse_entity_config({"entity_type": "sensor", "servent_id": "x", "name": "X", "device_config": {}})
        assert result.device_definition is None

    def test_none_device_config_is_ignored(self):
        result = parse_entity_config({"entity_type": "sensor", "servent_id": "x", "name": "X", "device_config": None})
        assert result.device_definition is None

    def test_base_defaults(self):
        result = parse_entity_config({"entity_type": "sensor", "servent_id": "x", "name": "X"})
        assert result.device_definition is None
        assert result.entity_category is None
        assert result.fixed_attributes == {}
        assert result.default_state is None
        assert result.disabled_by_default is False

    def test_sensor_specific_fields(self):
        result = parse_entity_config(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
            }
        )
        assert result.device_class == "temperature"
        assert result.unit_of_measurement == "°C"
        assert result.state_class == "measurement"

    def test_sensor_options_force_enum_device_class(self):
        # Flipped (WP3): options and device_class were independent; the shared
        # model couples them — options implies device_class "enum".
        result = parse_entity_config({"entity_type": "sensor", "servent_id": "x", "name": "X", "options": ["a", "b"]})
        assert result.options == ["a", "b"]
        assert result.device_class == "enum"

        with pytest.raises(ServiceValidationError, match="device class should be `enum`"):
            parse_entity_config(
                {
                    "entity_type": "sensor",
                    "servent_id": "x",
                    "name": "X",
                    "options": ["a", "b"],
                    "device_class": "temperature",
                }
            )

    def test_invalid_literal_value_raises_at_parse_time(self):
        # Flipped (WP3): device_class etc. are validated Literals at parse
        # time instead of raising mid-build during entity configuration.
        with pytest.raises(ServiceValidationError, match="Can not deserialize"):
            parse_entity_config({"entity_type": "sensor", "servent_id": "x", "name": "X", "device_class": "bogus"})

    def test_number_specific_fields(self):
        result = parse_entity_config(
            {
                "entity_type": "number",
                "servent_id": "x",
                "name": "X",
                "mode": "slider",
                "max_value": 100.0,
                "min_value": 0.0,
                "step": 0.5,
            }
        )
        assert result.mode == "slider"
        assert result.max_value == 100.0
        assert result.min_value == 0.0
        assert result.step == 0.5

    def test_number_mode_is_required(self):
        # Flipped (WP3): mode was optional (None → HA default); now required.
        with pytest.raises(ServiceValidationError, match="mode"):
            parse_entity_config({"entity_type": "number", "servent_id": "x", "name": "X"})

    def test_button_event_is_required(self):
        # Flipped (WP3): event no longer defaults to "" (which fired the
        # literal event "servent."); it is now required.
        with pytest.raises(ServiceValidationError, match="event"):
            parse_entity_config({"entity_type": "button", "servent_id": "x", "name": "X"})

    def test_button_specific_fields_and_defaults(self):
        result = parse_entity_config(
            {
                "entity_type": "button",
                "servent_id": "x",
                "name": "X",
                "event": "my_event",
                "event_data": {"k": "v"},
            }
        )
        assert result.event == "my_event"
        assert result.event_data == {"k": "v"}

        result = parse_entity_config({"entity_type": "button", "servent_id": "x", "name": "X", "event": "e"})
        assert result.event_data == {}

    def test_threshold_entity_id_is_required(self):
        # Flipped (WP3): entity_id no longer defaults to "".
        with pytest.raises(ServiceValidationError, match="entity_id"):
            parse_entity_config({"entity_type": "threshold", "servent_id": "x", "name": "X", "lower": 1.0})

    def test_threshold_requires_lower_or_upper(self):
        # Flipped (WP3): a threshold sensor with no bounds is meaningless and
        # is now rejected by the shared model's __post_init__.
        with pytest.raises(ServiceValidationError, match="lower or an upper"):
            parse_entity_config(
                {"entity_type": "threshold", "servent_id": "x", "name": "X", "entity_id": "sensor.source"}
            )

    def test_threshold_specific_fields_and_defaults(self):
        result = parse_entity_config(
            {
                "entity_type": "threshold",
                "servent_id": "x",
                "name": "X",
                "entity_id": "sensor.source",
                "lower": 1.5,
                "upper": 9.5,
                "hysteresis": 0.25,
            }
        )
        assert result.entity_id == "sensor.source"
        assert result.lower == 1.5
        assert result.upper == 9.5
        assert result.hysteresis == 0.25

        result = parse_entity_config(
            {"entity_type": "threshold", "servent_id": "x", "name": "X", "entity_id": "sensor.source", "lower": 1.0}
        )
        assert result.upper is None
        assert result.hysteresis == 0

    def test_select_options_are_required(self):
        # Flipped (WP3): options no longer defaults to [].
        with pytest.raises(ServiceValidationError, match="options"):
            parse_entity_config({"entity_type": "select", "servent_id": "x", "name": "X"})

    def test_binary_sensor_rejects_config_entity_category(self):
        # Flipped (WP3): any string used to be accepted and checked at build;
        # the shared model rejects "config" for binary sensors at parse time.
        with pytest.raises(ServiceValidationError, match="'config' entity category"):
            parse_entity_config(
                {"entity_type": "binary_sensor", "servent_id": "x", "name": "X", "entity_category": "config"}
            )

    def test_missing_required_field_raises_service_validation_error(self):
        # Flipped (WP3): was a bare TypeError from the dataclass constructor;
        # now a ServiceValidationError wrapping the SerdeError.
        with pytest.raises(ServiceValidationError, match="servent_id"):
            parse_entity_config({"entity_type": "sensor", "name": "X"})

    def test_app_name_and_is_global_parse_without_rejection(self):
        # Domovoy constraint 8: these fields are real in the shared model and
        # must always be accepted.
        result = parse_entity_config(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "app_name": "my_app",
                "device_definition": {"device_id": "d", "name": "D", "app_name": "my_app", "is_global": True},
            }
        )
        assert result.app_name == "my_app"
        assert result.device_definition.is_global is True


class TestDeviceHelpers:
    def test_get_device_id_is_prefixed(self):
        # The "device-" prefix is frozen wire format (Domovoy constraint 7).
        assert get_device_id(DeviceConfig(device_id="abc", name="Dev")) == "device-abc"

    def test_get_device_id_with_empty_id(self):
        assert get_device_id(DeviceConfig(device_id="", name="")) == "device-"

    def test_get_device_info_defaults(self):
        info = get_device_info(DeviceConfig(device_id="abc", name="Dev"))
        assert info["identifiers"] == {("servents", "device-abc")}
        assert info["name"] == "Dev"
        assert info["manufacturer"] == "ServEnts"
        assert info["model"] == "Virtual Device"
        assert info["sw_version"] is None

    def test_get_device_info_explicit_values(self):
        info = get_device_info(
            DeviceConfig(device_id="abc", name="Dev", manufacturer="Acme", model="M1", version="1.2.3")
        )
        assert info["manufacturer"] == "Acme"
        assert info["model"] == "M1"
        assert info["sw_version"] == "1.2.3"


class TestParseUpdateEntity:
    def test_extraneous_keys_are_ignored(self):
        result = parse_update_entity({"servent_id": "x", "state": 5, "attributes": {"a": 1}, "junk": True})
        assert result.servent_id == "x"
        assert result.state == 5
        assert result.attributes == {"a": 1}

    def test_missing_state_defaults_to_none(self):
        # Changed (WP3): the old parse raised TypeError when state was absent;
        # state is Any | None in the shared model and deserializes as None.
        result = parse_update_entity({"servent_id": "x"})
        assert result.state is None

    def test_servent_id_is_required(self):
        with pytest.raises(ServiceValidationError, match="servent_id"):
            parse_update_entity({"state": 1})

    def test_attributes_default(self):
        result = parse_update_entity({"servent_id": "x", "state": None})
        assert result.attributes == {}
