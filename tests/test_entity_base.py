"""Characterization tests for entity.py: shared entity configuration behavior.

ServEntSensor is used as the concrete vehicle since the base classes rely on
subclass hooks (update_specific_entity_config / set_new_state_and_attributes).
"""

from homeassistant.const import EntityCategory
from servents.data_model.entity_configs import DeviceConfig

from custom_components.servents.entity import ServentExtraData
from custom_components.servents.sensor import ServEntSensor
from tests.conftest import make_definition


def make_sensor(**extra) -> ServEntSensor:
    return ServEntSensor(make_definition("sensor", "s1", name="My Sensor", **extra))


class TestServentConfigure:
    def test_fixed_entity_flags(self):
        sensor = make_sensor()
        assert sensor._attr_should_poll is False
        assert sensor._attr_has_entity_name is True

    def test_unique_id_uses_sensor_prefix_for_all_types(self):
        # Note: the prefix is literally "sensor-" regardless of entity type.
        sensor = make_sensor()
        assert sensor._attr_unique_id == "sensor-s1"
        assert sensor.servent_id == "s1"

    def test_name_comes_from_definition(self):
        assert make_sensor()._attr_name == "My Sensor"

    def test_default_state_is_applied_as_initial_value(self):
        sensor = make_sensor(default_state=42)
        assert sensor._attr_native_value == 42

    def test_no_default_state_means_none(self):
        assert make_sensor()._attr_native_value is None

    def test_entity_category_parsed(self):
        sensor = make_sensor(entity_category="diagnostic")
        assert sensor._attr_entity_category is EntityCategory.DIAGNOSTIC

    def test_entity_category_none_when_absent(self):
        assert make_sensor()._attr_entity_category is None

    def test_fixed_attributes_merged_with_servent_id(self):
        sensor = make_sensor(fixed_attributes={"zone": "kitchen"})
        assert sensor.fixed_attributes == {"zone": "kitchen", "servent_id": "s1"}
        assert sensor._attr_extra_state_attributes == {"zone": "kitchen", "servent_id": "s1"}

    def test_unrecorded_attributes_contains_config_and_fixed_keys(self):
        sensor = make_sensor(fixed_attributes={"zone": "kitchen"})
        assert sensor._unrecorded_attributes == frozenset(["servent_config", "zone", "servent_id"])

    def test_enabled_by_default(self):
        assert make_sensor()._attr_entity_registry_enabled_default is True

    def test_disabled_by_default(self):
        sensor = make_sensor(disabled_by_default=True)
        assert sensor._attr_entity_registry_enabled_default is False


class TestUpdateConfig:
    def test_update_replaces_config_and_name(self):
        sensor = make_sensor()
        new_config = make_definition("sensor", "s1", name="Renamed", fixed_attributes={"a": 1})
        sensor._update_servent_entity_config(new_config)

        assert sensor.servent_config is new_config
        assert sensor._attr_name == "Renamed"
        assert sensor.fixed_attributes == {"a": 1, "servent_id": "s1"}

    def test_update_does_not_touch_current_state(self):
        sensor = make_sensor()
        sensor.set_new_state_and_attributes(10, {})
        sensor._update_servent_entity_config(make_definition("sensor", "s1", name="Renamed"))
        assert sensor._attr_native_value == 10


class TestDeviceInfo:
    def test_no_device_definition_returns_none(self):
        assert make_sensor().device_info is None

    def test_device_definition_returns_device_info(self):
        sensor = make_sensor(device_config={"device_id": "d1", "name": "Dev"})
        info = sensor.device_info
        assert info["identifiers"] == {("servents", "device-d1")}
        assert info["name"] == "Dev"

    def test_device_info_getter_has_no_side_effects(self):
        # Fixed (L6, WP3): coercion happens at parse time only; the getter
        # just reads. A DeviceConfig set on the config is used as-is.
        sensor = make_sensor()
        device = DeviceConfig(device_id="d2", name="DictDev")
        sensor.servent_config.device_definition = device

        info = sensor.device_info
        assert sensor.servent_config.device_definition is device
        assert info["identifiers"] == {("servents", "device-d2")}


class TestVerifiedScheduleUpdate:
    def test_no_hass_does_not_schedule(self):
        sensor = make_sensor()
        assert sensor.hass is None
        # Must not raise even though the entity was never added to hass
        sensor.verified_schedule_update_ha_state()

    def test_with_hass_schedules(self, mock_hass):
        sensor = make_sensor()
        sensor.hass = mock_hass
        called = []
        sensor.schedule_update_ha_state = lambda *_args, **_kwargs: called.append(True)
        sensor.verified_schedule_update_ha_state()
        assert called == [True]


class TestServentExtraData:
    def test_as_dict_round_trip(self):
        data = {"a": 1, "b": "two"}
        assert ServentExtraData(data).as_dict() is data
