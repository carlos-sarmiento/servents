"""Characterization tests for data_carriers.py: dict → dataclass conversion."""

import pytest

from custom_components.servents.data_carriers import (
    BaseServentEntityDefinition,
    EntityTypeToDataclassMap,
    ServentBinarySensorDefinition,
    ServentButtonDefinition,
    ServentDeviceDefinition,
    ServentNumberDefinition,
    ServentSelectDefinition,
    ServentSensorDefinition,
    ServentSwitchDefinition,
    ServentThresholdBinarySensorDefinition,
    ServentUpdateEntityDefinition,
    clean_params_and_build,
    to_dataclass,
)


class TestToDataclass:
    def test_missing_entity_type_raises(self):
        with pytest.raises(Exception, match="missing the entity_type field"):
            to_dataclass({"servent_id": "x", "name": "X"})

    def test_empty_entity_type_raises(self):
        with pytest.raises(Exception, match="missing the entity_type field"):
            to_dataclass({"entity_type": "", "servent_id": "x", "name": "X"})

    def test_unsupported_entity_type_raises(self):
        with pytest.raises(Exception, match="entity type: light is not supported"):
            to_dataclass({"entity_type": "light", "servent_id": "x", "name": "X"})

    @pytest.mark.parametrize(
        ("entity_type", "expected_class"),
        [
            ("sensor", ServentSensorDefinition),
            ("binary_sensor", ServentBinarySensorDefinition),
            ("threshold", ServentThresholdBinarySensorDefinition),
            ("switch", ServentSwitchDefinition),
            ("number", ServentNumberDefinition),
            ("button", ServentButtonDefinition),
            ("select", ServentSelectDefinition),
        ],
    )
    def test_maps_entity_type_to_dataclass(self, entity_type, expected_class):
        result = to_dataclass({"entity_type": entity_type, "servent_id": "x", "name": "X"})
        assert type(result) is expected_class
        assert isinstance(result, BaseServentEntityDefinition)
        assert result.servent_id == "x"
        assert result.name == "X"

    def test_map_covers_all_seven_types(self):
        assert set(EntityTypeToDataclassMap.keys()) == {
            "sensor",
            "binary_sensor",
            "threshold",
            "switch",
            "number",
            "button",
            "select",
        }

    def test_extraneous_keys_are_dropped(self):
        result = to_dataclass(
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
        result = to_dataclass(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "device_config": {"device_id": "dev1", "name": "My Device", "manufacturer": "Acme"},
            }
        )
        assert isinstance(result.device_definition, ServentDeviceDefinition)
        assert result.device_definition.device_id == "dev1"
        assert result.device_definition.name == "My Device"
        assert result.device_definition.manufacturer == "Acme"

    def test_empty_device_config_is_ignored(self):
        result = to_dataclass(
            {"entity_type": "sensor", "servent_id": "x", "name": "X", "device_config": {}}
        )
        assert result.device_definition is None

    def test_none_device_config_is_ignored(self):
        result = to_dataclass(
            {"entity_type": "sensor", "servent_id": "x", "name": "X", "device_config": None}
        )
        assert result.device_definition is None

    def test_base_defaults(self):
        result = to_dataclass({"entity_type": "sensor", "servent_id": "x", "name": "X"})
        assert result.device_definition is None
        assert result.entity_category is None
        assert result.fixed_attributes == {}
        assert result.default_state is None
        assert result.disabled_by_default is False

    def test_sensor_specific_fields(self):
        result = to_dataclass(
            {
                "entity_type": "sensor",
                "servent_id": "x",
                "name": "X",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
                "options": ["a", "b"],
            }
        )
        assert result.device_class == "temperature"
        assert result.unit_of_measurement == "°C"
        assert result.state_class == "measurement"
        assert result.options == ["a", "b"]

    def test_number_specific_fields(self):
        result = to_dataclass(
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

    def test_button_specific_fields_and_defaults(self):
        result = to_dataclass({"entity_type": "button", "servent_id": "x", "name": "X"})
        assert result.event == ""
        assert result.event_data == {}

        result = to_dataclass(
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

    def test_threshold_specific_fields_and_defaults(self):
        result = to_dataclass({"entity_type": "threshold", "servent_id": "x", "name": "X"})
        assert result.entity_id == ""
        assert result.lower is None
        assert result.upper is None
        assert result.hysteresis == 0

        result = to_dataclass(
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

    def test_select_options_default_to_empty_list(self):
        result = to_dataclass({"entity_type": "select", "servent_id": "x", "name": "X"})
        assert result.options == []

    def test_missing_required_field_raises_type_error(self):
        # servent_id and name are positional dataclass fields with no default
        with pytest.raises(TypeError):
            to_dataclass({"entity_type": "sensor", "name": "X"})


class TestServentDeviceDefinition:
    def test_get_device_id_is_prefixed(self):
        assert ServentDeviceDefinition(device_id="abc").get_device_id() == "device-abc"

    def test_get_device_id_with_empty_id(self):
        assert ServentDeviceDefinition().get_device_id() == "device-"

    def test_get_device_info_defaults(self):
        info = ServentDeviceDefinition(device_id="abc", name="Dev").get_device_info()
        assert info["identifiers"] == {("servents", "device-abc")}
        assert info["name"] == "Dev"
        assert info["manufacturer"] == "ServEnts"
        assert info["model"] == "Virtual Device"
        assert info["sw_version"] is None

    def test_get_device_info_explicit_values(self):
        info = ServentDeviceDefinition(
            device_id="abc", name="Dev", manufacturer="Acme", model="M1", version="1.2.3"
        ).get_device_info()
        assert info["manufacturer"] == "Acme"
        assert info["model"] == "M1"
        assert info["sw_version"] == "1.2.3"

    def test_from_dict_drops_extraneous_keys(self):
        dev = ServentDeviceDefinition.from_dict({"device_id": "d", "name": "N", "bogus": 1})
        assert dev.device_id == "d"
        assert dev.name == "N"


class TestCleanParamsAndBuild:
    def test_filters_to_constructor_params(self):
        result = clean_params_and_build(
            ServentUpdateEntityDefinition,
            {"servent_id": "x", "state": 5, "attributes": {"a": 1}, "junk": True},
        )
        assert result.servent_id == "x"
        assert result.state == 5
        assert result.attributes == {"a": 1}

    def test_update_definition_state_is_required(self):
        # `state` has no default — an update call without it raises TypeError
        with pytest.raises(TypeError):
            clean_params_and_build(ServentUpdateEntityDefinition, {"servent_id": "x"})

    def test_update_definition_attributes_default(self):
        result = clean_params_and_build(
            ServentUpdateEntityDefinition, {"servent_id": "x", "state": None}
        )
        assert result.attributes == {}
