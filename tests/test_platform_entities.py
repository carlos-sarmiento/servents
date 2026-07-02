"""Characterization tests for each platform's entity class."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number.const import NumberMode
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass

from custom_components.servents.binary_sensor import (
    ServEntBinarySensor,
    ServEntHassIsReady,
    ServEntThresholdBinarySensor,
)
from custom_components.servents.button import ServEntButton
from custom_components.servents.number import ServEntNumber
from custom_components.servents.select import ServEntSelect
from custom_components.servents.sensor import ServEntSensor
from custom_components.servents.switch import ServEntSwitch
from tests.conftest import make_definition


class TestServEntSensor:
    def test_device_class_and_units(self):
        sensor = ServEntSensor(
            make_definition(
                "sensor",
                "s1",
                device_class="temperature",
                unit_of_measurement="°C",
                state_class="measurement",
            )
        )
        assert sensor._attr_device_class is SensorDeviceClass.TEMPERATURE
        assert sensor._attr_native_unit_of_measurement == "°C"
        assert sensor._attr_state_class == "measurement"

    def test_no_device_class(self):
        sensor = ServEntSensor(make_definition("sensor", "s1"))
        assert sensor._attr_device_class is None
        assert sensor._attr_options is None

    def test_enum_options(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", options=["low", "high"]))
        assert sensor._attr_options == ["low", "high"]

    def test_invalid_device_class_raises(self):
        with pytest.raises(ValueError):
            ServEntSensor(make_definition("sensor", "s1", device_class="not-a-class"))

    def test_set_state_and_attributes(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", fixed_attributes={"fixed": 1}))
        sensor.set_new_state_and_attributes(42, {"extra": 2})
        assert sensor._attr_native_value == 42
        assert sensor._attr_extra_state_attributes == {"fixed": 1, "extra": 2, "servent_id": "s1"}

    def test_set_state_with_none_attributes(self):
        sensor = ServEntSensor(make_definition("sensor", "s1"))
        sensor.set_new_state_and_attributes(1, None)
        assert sensor._attr_extra_state_attributes == {"servent_id": "s1"}

    def test_attributes_cannot_override_servent_id(self):
        sensor = ServEntSensor(make_definition("sensor", "s1"))
        sensor.set_new_state_and_attributes(1, {"servent_id": "spoofed"})
        assert sensor._attr_extra_state_attributes["servent_id"] == "s1"

    @pytest.mark.parametrize("device_class", ["timestamp", "date"])
    def test_timestamp_and_date_states_convert_from_epoch(self, device_class):
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class=device_class))
        sensor.set_new_state_and_attributes(1700000000, {})
        assert sensor._attr_native_value == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_timestamp_state_accepts_stringified_epoch(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="timestamp"))
        sensor.set_new_state_and_attributes("1700000000", {})
        assert sensor._attr_native_value == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_timestamp_none_state_stays_none(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="timestamp"))
        sensor.set_new_state_and_attributes(None, {})
        assert sensor._attr_native_value is None


class TestServEntBinarySensor:
    def test_device_class(self):
        ent = ServEntBinarySensor(make_definition("binary_sensor", "b1", device_class="motion"))
        assert ent._attr_device_class is BinarySensorDeviceClass.MOTION

    def test_set_state(self):
        ent = ServEntBinarySensor(make_definition("binary_sensor", "b1"))
        ent.set_new_state_and_attributes(True, None)
        assert ent._attr_is_on is True
        assert ent._attr_extra_state_attributes == {"servent_id": "b1"}


class TestServEntSwitch:
    def test_device_class(self):
        ent = ServEntSwitch(make_definition("switch", "sw1", device_class="outlet"))
        assert ent._attr_device_class is SwitchDeviceClass.OUTLET

    def test_turn_on_off_without_hass(self):
        ent = ServEntSwitch(make_definition("switch", "sw1"))
        ent.turn_on()
        assert ent._attr_is_on is True
        ent.turn_off()
        assert ent._attr_is_on is False

    def test_set_state(self):
        ent = ServEntSwitch(make_definition("switch", "sw1"))
        ent.set_new_state_and_attributes(True, {"a": 1})
        assert ent._attr_is_on is True
        assert ent._attr_extra_state_attributes == {"a": 1, "servent_id": "sw1"}


class TestServEntNumber:
    def test_full_config(self):
        ent = ServEntNumber(
            make_definition(
                "number",
                "n1",
                device_class="temperature",
                unit_of_measurement="°C",
                mode="slider",
                max_value=100.0,
                min_value=1.0,
                step=0.5,
            )
        )
        assert ent._attr_device_class is NumberDeviceClass.TEMPERATURE
        assert ent._attr_native_unit_of_measurement == "°C"
        assert ent._attr_mode is NumberMode.SLIDER
        assert ent._attr_native_max_value == 100.0
        assert ent._attr_native_min_value == 1.0
        assert ent._attr_native_step == 0.5

    def test_falsy_bounds_are_ignored(self):
        # min_value=0 and step=0 are falsy, so they do NOT set the attrs —
        # HA falls back to its defaults. This is current (quirky) behavior.
        ent = ServEntNumber(make_definition("number", "n1", min_value=0.0, max_value=0.0, step=0.0))
        assert "_attr_native_min_value" not in ent.__dict__
        assert "_attr_native_max_value" not in ent.__dict__
        assert "_attr_native_step" not in ent.__dict__

    def test_set_native_value(self):
        ent = ServEntNumber(make_definition("number", "n1"))
        ent.set_native_value(7.5)
        assert ent._attr_native_value == 7.5

    def test_set_state(self):
        ent = ServEntNumber(make_definition("number", "n1"))
        ent.set_new_state_and_attributes(3.2, None)
        assert ent._attr_native_value == 3.2
        assert ent._attr_extra_state_attributes == {"servent_id": "n1"}


class TestServEntSelect:
    def test_options(self):
        ent = ServEntSelect(make_definition("select", "sel1", options=["a", "b", "c"]))
        assert ent.options == ["a", "b", "c"]
        assert ent._attr_options == ["a", "b", "c"]

    def test_select_option(self):
        ent = ServEntSelect(make_definition("select", "sel1", options=["a", "b"]))
        ent.select_option("b")
        assert ent._attr_current_option == "b"

    def test_set_state(self):
        ent = ServEntSelect(make_definition("select", "sel1", options=["a", "b"]))
        ent.set_new_state_and_attributes("a", None)
        assert ent._attr_current_option == "a"
        assert ent._attr_extra_state_attributes == {"servent_id": "sel1"}


class TestServEntButton:
    def make_button(self, hass=None, **extra):
        return ServEntButton(make_definition("button", "btn1", **extra), hass or MagicMock())

    def test_event_config(self):
        ent = self.make_button(event="pressed", event_data={"k": "v"}, device_class="restart")
        assert ent.servent_event == "pressed"
        assert ent.event_data == {"k": "v"}
        assert ent._attr_device_class is ButtonDeviceClass.RESTART

    async def test_press_fires_prefixed_event(self):
        hass = MagicMock()
        ent = self.make_button(hass=hass, event="my_event", event_data={"a": 1})
        await ent.async_press()
        hass.bus.async_fire.assert_called_once_with("servent.my_event", {"a": 1})

    def test_extra_state_attributes_include_fixed_and_servent_id(self):
        ent = self.make_button(fixed_attributes={"zone": "hall"})
        assert ent.extra_state_attributes == {"zone": "hall", "servent_id": "btn1"}

    def test_name_property(self):
        ent = self.make_button()
        assert ent.name == "Test"


class TestServEntThresholdBinarySensor:
    def make_threshold(self, hass=None, **extra):
        defaults = {"entity_id": "sensor.source", "lower": 1.0, "upper": 10.0, "hysteresis": 0.5}
        config = make_definition("threshold", "th1", **(defaults | extra))
        return ServEntThresholdBinarySensor(hass or MagicMock(), config)

    def test_name_is_overridden_from_config(self):
        ent = self.make_threshold()
        assert ent.name == "Test"

    def test_unique_id_is_overridden(self):
        ent = self.make_threshold()
        assert ent._attr_unique_id == "sensor-th1"

    def test_device_class(self):
        ent = self.make_threshold(device_class="motion")
        assert ent.device_class is BinarySensorDeviceClass.MOTION

    def test_extra_state_attributes_merge_threshold_and_servent_data(self):
        attrs = self.make_threshold().extra_state_attributes
        assert attrs["servent_id"] == "th1"
        assert attrs["source_entity_id"] == "sensor.source"
        assert attrs["entity_id"] == "sensor.source"
        assert attrs["lower"] == 1.0
        assert attrs["upper"] == 10.0
        assert attrs["hysteresis"] == 0.5

    async def test_restore_attributes_is_noop(self):
        # Threshold sensors compute state from the source entity; restore is disabled.
        ent = self.make_threshold()
        assert await ent.restore_attributes() is None


class TestServEntHassIsReady:
    def test_initial_state(self):
        ent = ServEntHassIsReady()
        assert ent._attr_unique_id == "servent-hass-is-up"
        assert ent._attr_is_on is False
        assert ent._attr_extra_state_attributes == {"servent_flag": "servent-hass-is-up"}
        assert ent._attr_device_info["identifiers"] == {("servents", "device-servent_core_device")}

    def test_set_state_updates_entity_and_registrar(self, registrar):
        ent = ServEntHassIsReady()
        ent.hass = MagicMock()
        ent.schedule_update_ha_state = MagicMock()

        ent.set_state(True)
        assert ent._attr_is_on is True
        assert registrar.is_hass_up is True

        ent.set_state(False)
        assert ent._attr_is_on is False
        assert registrar.is_hass_up is False
