"""Characterization tests for each platform's entity class."""

from datetime import date, datetime, time, timezone
from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.event import EventDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.number.const import DEFAULT_MAX_VALUE, DEFAULT_MIN_VALUE, DEFAULT_STEP, NumberMode
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.components.text import TextMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.servents.binary_sensor import (
    ServEntBinarySensor,
    ServEntHassIsReady,
    ServEntThresholdBinarySensor,
)
from custom_components.servents.button import ServEntButton
from custom_components.servents.date import ServEntDateEntity
from custom_components.servents.datetime import ServEntDatetimeEntity
from custom_components.servents.event import ServEntEventEntity
from custom_components.servents.number import ServEntNumber
from custom_components.servents.select import ServEntSelect
from custom_components.servents.sensor import ServEntSensor
from custom_components.servents.switch import ServEntSwitch
from custom_components.servents.text import ServEntTextEntity
from custom_components.servents.time import ServEntTimeEntity
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
        # Since WP3 the shared model forces device_class "enum" when options
        # are provided.
        sensor = ServEntSensor(make_definition("sensor", "s1", options=["low", "high"]))
        assert sensor._attr_options == ["low", "high"]
        assert sensor._attr_device_class is SensorDeviceClass.ENUM

    def test_invalid_device_class_raises_at_parse_time(self):
        # Flipped (WP3): the bad value is now rejected while parsing the
        # definition (Literal validation), before any entity is built.
        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError):
            make_definition("sensor", "s1", device_class="not-a-class")

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

    def test_timestamp_state_converts_from_integer_epoch(self):
        # Fixed (M4, WP8a): TIMESTAMP emits a timezone-aware datetime.
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="timestamp"))
        sensor.set_new_state_and_attributes(1700000000, {})
        assert sensor._attr_native_value == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_date_state_converts_from_epoch_to_date(self):
        # Fixed (M4, WP8a): DATE must emit a date, not a datetime. HA serializes
        # SensorDeviceClass.DATE with value.isoformat(); a datetime yields a full
        # timestamp string whereas a date yields "2023-11-14" as expected.
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="date"))
        sensor.set_new_state_and_attributes(1700000000, {})
        assert sensor._attr_native_value == date(2023, 11, 14)

    def test_timestamp_state_accepts_stringified_integer_epoch(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="timestamp"))
        sensor.set_new_state_and_attributes("1700000000", {})
        assert sensor._attr_native_value == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_timestamp_state_accepts_float_epoch(self):
        # Fixed (M4, WP8a): float(state) replaces int(state) so sub-second
        # precision is preserved and float-string epochs do not raise ValueError.
        sensor = ServEntSensor(make_definition("sensor", "s1", device_class="timestamp"))
        sensor.set_new_state_and_attributes("1700000000.5", {})
        assert sensor._attr_native_value == datetime.fromtimestamp(1700000000.5, tz=timezone.utc)

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

    def test_mode_is_required(self):
        # Flipped (WP3): mode used to be optional (None → HA default); the
        # shared model requires it.
        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError):
            make_definition("number", "n1")

    def test_falsy_bounds_are_ignored(self):
        # min_value=0, max_value=0, and step=0 are falsy but are legitimate values.
        # They are now correctly applied (0.0 checks use `is not None` instead of truthiness).
        ent = ServEntNumber(make_definition("number", "n1", mode="auto", min_value=0.0, max_value=0.0, step=0.0))
        assert ent.native_min_value == 0.0
        assert ent.native_max_value == 0.0
        assert ent.native_step == 0.0

    def test_reconfigure_clears_omitted_bounds_and_step(self):
        ent = ServEntNumber(
            make_definition("number", "n1", mode="auto", min_value=1.0, max_value=10.0, step=0.5)
        )
        assert ent.native_min_value == 1.0
        assert ent.native_max_value == 10.0
        assert ent.native_step == 0.5

        ent.apply_config(make_definition("number", "n1", mode="auto"))

        assert ent.native_min_value == DEFAULT_MIN_VALUE
        assert ent.native_max_value == DEFAULT_MAX_VALUE
        assert ent.native_step is None
        assert ent.step == DEFAULT_STEP

        ent.apply_config(make_definition("number", "n1", mode="auto", min_value=0.0, max_value=0.0, step=0.0))

        assert ent.native_min_value == 0.0
        assert ent.native_max_value == 0.0
        assert ent.native_step == 0.0

    def test_set_native_value(self):
        ent = ServEntNumber(make_definition("number", "n1", mode="auto"))
        ent.set_native_value(7.5)
        assert ent._attr_native_value == 7.5

    def test_set_state(self):
        ent = ServEntNumber(make_definition("number", "n1", mode="auto"))
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
        # event is required since WP3 (a "" default fired the literal event
        # "servent.").
        return ServEntButton(make_definition("button", "btn1", **({"event": "e"} | extra)), hass or MagicMock())

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


class TestServEntTextEntity:
    def test_config_and_state(self):
        ent = ServEntTextEntity(
            make_definition("text", "txt1", min_length=1, max_length=10, pattern="^[a-z]+$", mode="password")
        )
        ent.set_new_state_and_attributes("hello", {"a": 1})

        assert ent._attr_mode is TextMode.PASSWORD
        assert ent._attr_native_min == 1
        assert ent._attr_native_max == 10
        assert ent._attr_pattern == "^[a-z]+$"
        assert ent.native_value == "hello"
        assert ent._attr_extra_state_attributes == {"a": 1, "servent_id": "txt1"}

    async def test_async_set_value_fires_event_and_updates_state(self):
        ent = ServEntTextEntity(make_definition("text", "txt1"))
        ent.hass = MagicMock()
        ent.verified_schedule_update_ha_state = MagicMock()
        ent.set_new_state_and_attributes("old", {"keep": "yes"})

        await ent.async_set_value("new")

        ent.hass.bus.async_fire.assert_called_once_with(
            "servent.text_changed",
            {"servent_id": "txt1", "value": "new"},
        )
        assert ent.native_value == "new"
        assert ent._attr_extra_state_attributes == {"keep": "yes", "servent_id": "txt1"}
        ent.verified_schedule_update_ha_state.assert_called_once()


class TestServEntDateEntity:
    def test_state_parses_iso_date(self):
        ent = ServEntDateEntity(make_definition("date", "date1"))
        ent.set_new_state_and_attributes("2026-07-05", None)
        assert ent.native_value == date(2026, 7, 5)
        assert ent.state == "2026-07-05"

    async def test_async_set_value_fires_event_and_updates_state(self):
        ent = ServEntDateEntity(make_definition("date", "date1"))
        ent.hass = MagicMock()
        ent.verified_schedule_update_ha_state = MagicMock()

        await ent.async_set_value(date(2026, 7, 5))

        ent.hass.bus.async_fire.assert_called_once_with(
            "servent.date_changed",
            {"servent_id": "date1", "value": "2026-07-05"},
        )
        assert ent.native_value == date(2026, 7, 5)
        ent.verified_schedule_update_ha_state.assert_called_once()


class TestServEntTimeEntity:
    def test_state_parses_iso_time(self):
        ent = ServEntTimeEntity(make_definition("time", "time1"))
        ent.set_new_state_and_attributes("12:30:15", None)
        assert ent.native_value == time(12, 30, 15)
        assert ent.state == "12:30:15"

    async def test_async_set_value_fires_event_and_updates_state(self):
        ent = ServEntTimeEntity(make_definition("time", "time1"))
        ent.hass = MagicMock()
        ent.verified_schedule_update_ha_state = MagicMock()

        await ent.async_set_value(time(12, 30, 15))

        ent.hass.bus.async_fire.assert_called_once_with(
            "servent.time_changed",
            {"servent_id": "time1", "value": "12:30:15"},
        )
        assert ent.native_value == time(12, 30, 15)
        ent.verified_schedule_update_ha_state.assert_called_once()


class TestServEntDatetimeEntity:
    def test_state_parses_timezone_aware_datetime(self):
        ent = ServEntDatetimeEntity(make_definition("date_time", "dt1"))
        ent.set_new_state_and_attributes("2026-07-05T12:30:15+00:00", None)
        assert ent.native_value == datetime(2026, 7, 5, 12, 30, 15, tzinfo=timezone.utc)
        assert ent.state == "2026-07-05T12:30:15+00:00"

    def test_naive_datetime_is_rejected(self):
        ent = ServEntDatetimeEntity(make_definition("date_time", "dt1"))
        with pytest.raises(ValueError, match="timezone"):
            ent.set_new_state_and_attributes("2026-07-05T12:30:15", None)

    async def test_async_set_value_fires_event_and_updates_state(self):
        ent = ServEntDatetimeEntity(make_definition("date_time", "dt1"))
        ent.hass = MagicMock()
        ent.verified_schedule_update_ha_state = MagicMock()
        value = datetime(2026, 7, 5, 12, 30, 15, tzinfo=timezone.utc)

        await ent.async_set_value(value)

        ent.hass.bus.async_fire.assert_called_once_with(
            "servent.datetime_changed",
            {"servent_id": "dt1", "value": "2026-07-05T12:30:15+00:00"},
        )
        assert ent.native_value == value
        ent.verified_schedule_update_ha_state.assert_called_once()


class TestServEntEventEntity:
    def test_config(self):
        ent = ServEntEventEntity(
            make_definition("event", "ev1", event_types=["pressed", "held"], device_class="doorbell")
        )
        assert ent.event_types == ["pressed", "held"]
        assert ent.device_class is EventDeviceClass.DOORBELL

    async def test_async_trigger_event_updates_state_and_attributes(self):
        ent = ServEntEventEntity(make_definition("event", "ev1", event_types=["pressed", "held"]))
        ent.verified_schedule_update_ha_state = MagicMock()

        await ent.async_trigger_event("pressed", {"confidence": 0.93})

        assert ent.state is not None
        assert ent.state_attributes["event_type"] == "pressed"
        assert ent.state_attributes["confidence"] == 0.93
        ent.verified_schedule_update_ha_state.assert_called_once()

    async def test_async_trigger_event_rejects_invalid_type(self):
        ent = ServEntEventEntity(make_definition("event", "ev1", event_types=["pressed"]))

        with pytest.raises(HomeAssistantError, match="Invalid event type"):
            await ent.async_trigger_event("held", {})


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
        # L8 (WP6): fixed_attributes are now included, like every other platform
        # (they fall out of the base owning the merge). servent_id, the
        # threshold internals, and source_entity_id stay.
        attrs = self.make_threshold(fixed_attributes={"zone": "attic"}).extra_state_attributes
        assert attrs["servent_id"] == "th1"
        assert attrs["zone"] == "attic"
        assert attrs["source_entity_id"] == "sensor.source"
        assert attrs["entity_id"] == "sensor.source"
        assert attrs["lower"] == 1.0
        assert attrs["upper"] == 10.0
        assert attrs["hysteresis"] == 0.5

    def test_reconfigure_applies_new_bounds(self):
        # H6 (WP6): re-creating a threshold sensor with new bounds/source used to
        # be silently ignored (params were consumed once by __init__). apply_config
        # now re-applies them to the ThresholdSensor internals.
        ent = self.make_threshold()
        new_config = make_definition(
            "threshold", "th1", entity_id="sensor.other", lower=5.0, upper=20.0, hysteresis=1.5
        )
        ent.apply_config(new_config)

        assert ent._entity_id == "sensor.other"
        assert ent.source_entity_id == "sensor.other"
        assert ent._threshold_lower == 5.0
        assert ent._threshold_upper == 20.0
        assert ent._hysteresis == 1.5
        attrs = ent.extra_state_attributes
        assert attrs["lower"] == 5.0
        assert attrs["upper"] == 20.0
        assert attrs["source_entity_id"] == "sensor.other"

    def test_reconfigure_while_live_re_runs_sensor_setup(self):
        # When already added to hass, a reconfigure re-tracks the (new) source
        # entity: it drops the old on-remove callbacks and re-runs the
        # ThresholdSensor setup so new bounds/source take effect immediately.
        ent = self.make_threshold()
        ent.hass = MagicMock()
        ent._call_on_remove_callbacks = MagicMock()
        ent._async_setup_sensor = MagicMock()

        ent.apply_config(
            make_definition("threshold", "th1", entity_id="sensor.other", lower=5.0, upper=20.0, hysteresis=1.5)
        )

        ent._call_on_remove_callbacks.assert_called_once()
        ent._async_setup_sensor.assert_called_once()
        assert ent._entity_id == "sensor.other"

    def test_reconfigure_clearing_a_bound_drops_it(self):
        # A reconfigure that removes the lower bound must actually drop it
        # (ThresholdSensor reads bounds via getattr(..., None)).
        ent = self.make_threshold()
        assert ent._threshold_lower == 1.0
        ent.apply_config(make_definition("threshold", "th1", entity_id="sensor.source", upper=10.0, hysteresis=0.5))
        assert not hasattr(ent, "_threshold_lower")
        assert ent.extra_state_attributes["lower"] is None

    async def test_restore_attributes_is_noop(self):
        # Threshold sensors compute state from the source entity; restore is disabled.
        ent = self.make_threshold()
        assert await ent.restore_attributes() is None


class TestRestoreFlowAcrossPlatforms:
    """WP7 (H4/L7): the full async_added_to_hass restore flow, per platform.

    Invariant 3: servent_id is present in the live attributes after restore on
    every stateful platform, button included (Domovoy discovery, constraint 1).
    Invariant 4: the native value still restores on sensor/number even though
    the ServEnts-owned attributes now share their extra-data dict.
    """

    @staticmethod
    def fake_extra(entity, data: dict):
        from custom_components.servents.entity import ServentExtraData

        async def _get():
            return ServentExtraData(data)

        entity.async_get_last_extra_data = _get

    @staticmethod
    def fake_last_state(entity, state: str):
        last = MagicMock()
        last.state = state

        async def _get():
            return last

        entity.async_get_last_state = _get

    async def test_sensor_restores_native_value_and_owned_attributes(self):
        sensor = ServEntSensor(make_definition("sensor", "s1", fixed_attributes={"zone": "attic"}))
        self.fake_extra(
            sensor,
            {
                "native_value": 21.5,
                "native_unit_of_measurement": "°C",
                "servents_attributes": {"zone": "kitchen", "note": "hi", "servent_id": "s1"},
            },
        )
        await sensor.async_added_to_hass()

        assert sensor._attr_native_value == 21.5
        assert sensor._attr_extra_state_attributes["servent_id"] == "s1"
        assert sensor._attr_extra_state_attributes["note"] == "hi"
        # current fixed_attributes win over the stale stored value
        assert sensor._attr_extra_state_attributes["zone"] == "attic"
        # HA-generated keys from the native-value store do not leak in
        assert "native_unit_of_measurement" not in sensor._attr_extra_state_attributes

    async def test_number_restores_native_value_and_servent_id(self):
        ent = ServEntNumber(make_definition("number", "n1", mode="auto"))
        self.fake_extra(
            ent,
            {
                "native_max_value": None,
                "native_min_value": None,
                "native_step": None,
                "native_unit_of_measurement": None,
                "native_value": 7.5,
                "servents_attributes": {"note": "hi", "servent_id": "n1"},
            },
        )
        await ent.async_added_to_hass()

        assert ent._attr_native_value == 7.5
        assert ent._attr_extra_state_attributes == {"note": "hi", "servent_id": "n1"}

    async def test_switch_restores_state_and_servent_id(self):
        ent = ServEntSwitch(make_definition("switch", "sw1"))
        self.fake_last_state(ent, "on")
        self.fake_extra(ent, {"servents_attributes": {"note": "hi", "servent_id": "sw1"}})
        await ent.async_added_to_hass()

        assert ent._attr_is_on is True
        assert ent._attr_extra_state_attributes == {"note": "hi", "servent_id": "sw1"}

    async def test_select_restores_option_and_servent_id(self):
        ent = ServEntSelect(make_definition("select", "sel1", options=["a", "b"]))
        self.fake_last_state(ent, "b")
        self.fake_extra(ent, {"servents_attributes": {"servent_id": "sel1"}})
        await ent.async_added_to_hass()

        assert ent._attr_current_option == "b"
        assert ent._attr_extra_state_attributes["servent_id"] == "sel1"

    async def test_binary_sensor_restores_state_and_servent_id(self):
        ent = ServEntBinarySensor(make_definition("binary_sensor", "b1"))
        self.fake_last_state(ent, "on")
        self.fake_extra(ent, {"servents_attributes": {"servent_id": "b1"}})
        await ent.async_added_to_hass()

        assert ent._attr_is_on is True
        assert ent._attr_extra_state_attributes["servent_id"] == "b1"

    async def test_button_restore_keeps_servent_id_and_owned_attributes(self):
        # Constraint 1's sharpest edge: Domovoy discovers buttons by the
        # servent_id attribute too. The button now uses the base restore flow
        # (its own async_get_last_extra_data override is gone — L7).
        ent = ServEntButton(make_definition("button", "btn1", event="e"), MagicMock())
        self.fake_extra(ent, {"servents_attributes": {"note": "hi", "servent_id": "btn1"}})
        await ent.async_added_to_hass()

        assert ent._attr_extra_state_attributes == {"note": "hi", "servent_id": "btn1"}

    async def test_button_restore_with_foreign_extra_data_keeps_servent_id(self):
        # Pre-WP7 nothing was ever written, so on first restart after upgrade
        # the stored extra data (if any) is a foreign leftover without our
        # store key. Nothing leaks in; servent_id stays.
        ent = ServEntButton(make_definition("button", "btn1", event="e"), MagicMock())
        self.fake_extra(ent, {"someone_elses": "data"})
        await ent.async_added_to_hass()

        assert ent._attr_extra_state_attributes == {"servent_id": "btn1"}


class TestServEntHassIsReady:
    def test_initial_state(self):
        ent = ServEntHassIsReady()
        assert ent._attr_unique_id == "servent-hass-is-up"
        assert ent._attr_is_on is False
        assert ent._attr_extra_state_attributes == {"servent_flag": "servent-hass-is-up"}
        assert ent._attr_device_info["identifiers"] == {("servents", "device-servent_core_device")}

    def test_set_is_on_updates_only_the_entity(self):
        # M7: the entity no longer reaches the registrar itself. It exposes a
        # plain state setter; the single STARTED/STOP handler (registered by
        # configure_homeassistant_up_sensor) drives both the entity and the
        # registrar's is_hass_up flag together.
        ent = ServEntHassIsReady()
        ent.set_is_on(True)
        assert ent._attr_is_on is True
        ent.set_is_on(False)
        assert ent._attr_is_on is False

    def test_configure_registers_single_listener_pair_and_syncs_both(self, registrar):
        # M7/M11: one place registers the STARTED/STOP listeners, seeds state
        # from hass.is_running (M6), stores the sensor + unsub handles, and
        # keeps the visible sensor and registrar.is_hass_up in sync.
        from custom_components.servents.binary_sensor import configure_homeassistant_up_sensor

        hass = MagicMock()
        hass.is_running = False
        added = []
        hass.bus.async_listen_once.side_effect = lambda event, cb: (event, cb)

        def async_add_entities(entities, _update=False):
            added.extend(entities)

        configure_homeassistant_up_sensor(hass, registrar, async_add_entities)

        # One sensor added; two listeners (STARTED, STOP); two unsub handles held.
        assert len(added) == 1
        sensor = added[0]
        assert hass.bus.async_listen_once.call_count == 2
        assert len(registrar.unsub_hass_state_listeners) == 2

        # initial value derived from hass.is_running
        assert sensor._attr_is_on is False
        assert registrar.is_hass_up is False

        sensor.schedule_update_ha_state = MagicMock()
        started_cb = hass.bus.async_listen_once.call_args_list[0].args[1]
        stop_cb = hass.bus.async_listen_once.call_args_list[1].args[1]

        started_cb(MagicMock())
        assert sensor._attr_is_on is True
        assert registrar.is_hass_up is True

        stop_cb(MagicMock())
        assert sensor._attr_is_on is False
        assert registrar.is_hass_up is False
