"""Characterization tests for entity.py: shared entity configuration behavior.

ServEntSensor is used as the concrete vehicle since the base classes rely on
subclass hooks (update_specific_entity_config / set_new_state_and_attributes).
"""

from homeassistant.const import EntityCategory
from servents.data_model.entity_configs import DeviceConfig

from custom_components.servents.entity import SERVENT_ATTRIBUTES_STORE_KEY, ServentExtraData
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

    def test_unrecorded_attributes_excludes_only_servent_id(self):
        # H3 (WP7, revised): the old instance-level assignment in __init__ was
        # provably ignored (Entity.__init_subclass__ folds the CLASS attribute
        # into __combined_unrecorded_attributes at class-creation time). The
        # policy excludes ONLY servent_id (a routing constant) from the
        # recorder; the app-pushed dynamic attributes and the fixed_attributes
        # are recorded — that data must not be dropped from history.
        assert ServEntSensor._unrecorded_attributes == frozenset({"servent_id"})
        # It must land in the combined set HA actually reads — the exact thing
        # the instance-level assignment failed to do.
        assert "servent_id" in ServEntSensor._Entity__combined_unrecorded_attributes
        # Fixed-attribute keys must NOT be excluded (they stay in history).
        assert "zone" not in ServEntSensor._Entity__combined_unrecorded_attributes
        sensor = make_sensor(fixed_attributes={"zone": "kitchen"})
        assert sensor._unrecorded_attributes == frozenset({"servent_id"})

    def test_enabled_by_default(self):
        assert make_sensor()._attr_entity_registry_enabled_default is True

    def test_disabled_by_default(self):
        sensor = make_sensor(disabled_by_default=True)
        assert sensor._attr_entity_registry_enabled_default is False


class TestUpdateConfig:
    # Reconfigure is now the single apply_config hook (WP6), called both on
    # initial setup and on re-create; it replaced _update_servent_entity_config.
    def test_update_replaces_config_and_name(self):
        sensor = make_sensor()
        new_config = make_definition("sensor", "s1", name="Renamed", fixed_attributes={"a": 1})
        sensor.apply_config(new_config)

        assert sensor.servent_config is new_config
        assert sensor._attr_name == "Renamed"
        assert sensor.fixed_attributes == {"a": 1, "servent_id": "s1"}

    def test_update_does_not_touch_current_state(self):
        sensor = make_sensor()
        sensor.set_new_state_and_attributes(10, {})
        sensor.apply_config(make_definition("sensor", "s1", name="Renamed"))
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


def stored_extra(data: dict):
    """Simulate async_get_last_extra_data returning the given stored dict."""

    async def _get():
        return ServentExtraData(data)

    return _get


class TestAttributePersistence:
    """H4/L7 (WP7): owned attributes persist via extra_restore_state_data."""

    def test_extra_restore_state_data_stores_owned_attributes_and_native_value(self):
        # Write side: the owned attributes live under the store key, and the
        # RestoreSensor native-value keys stay in the same dict (invariant 4).
        sensor = make_sensor(fixed_attributes={"zone": "kitchen"}, unit_of_measurement="°C")
        sensor.set_new_state_and_attributes(21.5, {"note": "hi"})

        stored = sensor.extra_restore_state_data.as_dict()
        assert stored[SERVENT_ATTRIBUTES_STORE_KEY] == {"zone": "kitchen", "note": "hi", "servent_id": "s1"}
        assert stored["native_value"] == 21.5
        assert stored["native_unit_of_measurement"] == "°C"

    async def test_restore_round_trip_keeps_only_owned_keys(self):
        # What one instance persists, a fresh instance restores — nothing more.
        old = make_sensor(fixed_attributes={"zone": "kitchen"})
        old.set_new_state_and_attributes(1, {"note": "hi"})
        stored = old.extra_restore_state_data.as_dict()

        new = make_sensor(fixed_attributes={"zone": "kitchen"})
        new.async_get_last_extra_data = stored_extra(stored)
        await new.restore_attributes()

        assert new._attr_extra_state_attributes == {"zone": "kitchen", "note": "hi", "servent_id": "s1"}

    async def test_restore_does_not_resurrect_ha_generated_keys(self):
        # H4: a legacy/foreign stored dict (the pre-WP7 code persisted nothing,
        # so the extra data can only be another integration's leftovers or the
        # historical full-attribute dict) must not leak into the live
        # attributes — restore reads ONLY the store key.
        sensor = make_sensor(fixed_attributes={"zone": "kitchen"})
        sensor.async_get_last_extra_data = stored_extra(
            {"friendly_name": "My Sensor", "icon": "mdi:thermometer", "unit_of_measurement": "°C"}
        )
        await sensor.restore_attributes()

        assert sensor._attr_extra_state_attributes == {"zone": "kitchen", "servent_id": "s1"}

    async def test_updated_fixed_attribute_wins_over_stale_restore(self):
        # H4: current fixed_attributes are merged LAST, so a fixed attribute
        # updated before the restart is not reverted by the stale stored value.
        sensor = make_sensor(fixed_attributes={"zone": "attic"})
        sensor.async_get_last_extra_data = stored_extra(
            {SERVENT_ATTRIBUTES_STORE_KEY: {"zone": "kitchen", "note": "hi", "servent_id": "s1"}}
        )
        await sensor.restore_attributes()

        assert sensor._attr_extra_state_attributes["zone"] == "attic"
        assert sensor._attr_extra_state_attributes["note"] == "hi"

    async def test_restore_with_no_stored_data_keeps_servent_id(self):
        # Constraint 1: first start (nothing persisted) — servent_id stays.
        sensor = make_sensor()

        async def none_extra():
            return None

        sensor.async_get_last_extra_data = none_extra
        await sensor.restore_attributes()

        assert sensor._attr_extra_state_attributes["servent_id"] == "s1"
