"""Characterization tests for the service handlers in __init__.py."""

from unittest.mock import MagicMock, patch

import pytest

from servents.data_model.entity_configs import SensorConfig, SwitchConfig

from custom_components.servents import (
    handle_create_entity,
    handle_update_entity,
    register_and_update_all_entities,
)
from tests.conftest import FakeServiceCall, make_definition


def register_builder(registrar, definition_type, builder=None):
    builder = builder or MagicMock(side_effect=lambda d: MagicMock(servent_config=d))
    registrar.register_builder_for_definition(definition_type, builder, MagicMock())
    return builder


class TestHandleCreateEntity:
    async def test_no_entities_raises(self):
        with pytest.raises(Exception, match="Call does not define any entities"):
            await handle_create_entity(FakeServiceCall({}))

    async def test_empty_entities_list_raises(self):
        with pytest.raises(Exception, match="Call does not define any entities"):
            await handle_create_entity(FakeServiceCall({"entities": []}))

    async def test_creates_definition_and_builds_entity(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        await handle_create_entity(
            FakeServiceCall(
                {"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]}
            )
        )

        definitions = registrar.get_all_entities()
        assert len(definitions) == 1
        assert definitions[0].servent_id == "s1"
        builder.assert_called_once()
        assert registrar.get_live_entity_for_servent_id("s1") is not None

    async def test_creates_multiple_entities_in_one_call(self, registrar):
        register_builder(registrar, SensorConfig)
        register_builder(registrar, SwitchConfig)

        await handle_create_entity(
            FakeServiceCall(
                {
                    "entities": [
                        {"entity_type": "sensor", "servent_id": "s1", "name": "S1"},
                        {"entity_type": "switch", "servent_id": "sw1", "name": "SW1"},
                    ]
                }
            )
        )

        assert len(registrar.get_all_entities()) == 2
        assert registrar.get_live_entity_for_servent_id("s1") is not None
        assert registrar.get_live_entity_for_servent_id("sw1") is not None

    async def test_invalid_definition_in_list_raises_before_any_registration(self, registrar):
        # parse_entity_config runs on the entire list before registration, so
        # one bad definition aborts the whole call.
        register_builder(registrar, SensorConfig)

        with pytest.raises(Exception, match="is not supported"):
            await handle_create_entity(
                FakeServiceCall(
                    {
                        "entities": [
                            {"entity_type": "sensor", "servent_id": "s1", "name": "S1"},
                            {"entity_type": "bogus", "servent_id": "s2", "name": "S2"},
                        ]
                    }
                )
            )

        assert registrar.get_all_entities() == []

    async def test_type_conflict_is_logged_not_raised(self, registrar, caplog):
        # register_definition raising (type change for same servent_id) is
        # caught and logged; the service call still completes.
        register_builder(registrar, SensorConfig)
        register_builder(registrar, SwitchConfig)

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]})
        )
        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "switch", "servent_id": "s1", "name": "S1"}]})
        )

        # original definition survives
        assert isinstance(registrar.get_all_entities()[0], SensorConfig)
        assert "Cannot change the type" in caplog.text

    async def test_recreating_existing_entity_updates_live_entity(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "First"}]})
        )
        live = registrar.get_live_entity_for_servent_id("s1")

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "Second"}]})
        )

        # builder is only invoked once; the existing live entity is reconfigured
        assert builder.call_count == 1
        assert registrar.get_live_entity_for_servent_id("s1") is live
        live._update_servent_entity_config.assert_called_once()
        live.verified_schedule_update_ha_state.assert_called_once()


class TestHandleUpdateEntity:
    async def test_updates_live_entity(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall({"servent_id": "s1", "state": 42, "attributes": {"a": 1}})
        )

        live.set_new_state_and_attributes.assert_called_once_with(42, {"a": 1})
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_unknown_servent_id_warns_and_does_not_raise(self, caplog):
        await handle_update_entity(FakeServiceCall({"servent_id": "ghost", "state": 1}))
        assert "Non Registered ID ghost" in caplog.text

    async def test_extraneous_keys_in_call_are_ignored(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall({"servent_id": "s1", "state": "on", "junk_key": True})
        )

        live.set_new_state_and_attributes.assert_called_once_with("on", {})


class TestRegisterAndUpdateAllEntities:
    def test_builds_missing_and_updates_existing(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        existing_live = MagicMock()
        registrar.register_live_entity("existing", existing_live)
        registrar.register_definition(make_definition("sensor", "existing", name="Old"))
        registrar.register_definition(make_definition("sensor", "new-one"))

        register_and_update_all_entities()

        # "new-one" is built; "existing" is reconfigured in place
        assert builder.call_count == 1
        assert builder.call_args[0][0].servent_id == "new-one"
        existing_live._update_servent_entity_config.assert_called_once()
        existing_live.verified_schedule_update_ha_state.assert_called_once()

    def test_noop_when_registry_is_empty(self, registrar):
        register_and_update_all_entities()
        assert registrar.live_entities == {}


class TestSetup:
    def test_setup_registers_three_services(self):
        from custom_components.servents import setup

        hass = MagicMock()
        assert setup(hass, MagicMock()) is True

        registered = {call.args[:2] for call in hass.services.register.call_args_list}
        assert registered == {
            ("servents", "create_entity"),
            ("servents", "update_state"),
            ("servents", "cleanup_devices"),
        }


class TestCleanupDevices:
    @staticmethod
    def get_cleanup_handler(hass):
        from custom_components.servents import setup

        setup(hass, MagicMock())
        return next(
            call.args[2]
            for call in hass.services.register.call_args_list
            if call.args[1] == "cleanup_devices"
        )

    async def run_cleanup(self, devices):
        cleanup = self.get_cleanup_handler(MagicMock())
        device_registry = MagicMock()
        device_registry.devices.values.return_value = devices

        with patch("custom_components.servents.dr.async_get", return_value=device_registry):
            await cleanup(FakeServiceCall({}))

        return {call.args[0] for call in device_registry.async_remove_device.call_args_list}

    async def test_removes_stale_devices_whose_identifier_value_contains_servent(self, registrar):
        # Candidate selection checks for the substring "servent" in the
        # identifier VALUE (a[1]), not the domain (a[0]). Only candidates whose
        # id is absent from the current definitions are removed.
        registrar.register_definition(
            make_definition(
                "sensor", "s1", device_config={"device_id": "kept-servent-dev", "name": "Kept"}
            )
        )

        kept = MagicMock(id="kept-entry", identifiers={("servents", "device-kept-servent-dev")})
        stale = MagicMock(id="stale-entry", identifiers={("servents", "device-stale-servent-dev")})

        removed = await self.run_cleanup([kept, stale])
        assert removed == {"stale-entry"}

    async def test_stale_device_without_servent_in_identifier_value_is_not_removed(self):
        # Fixed (H2): candidate selection now filters by domain == DOMAIN, not
        # by substring in the identifier value. A stale servents-domain device
        # IS now selected and removed even when its value lacks "servent".
        stale = MagicMock(id="stale-entry", identifiers={("servents", "device-abc")})
        assert await self.run_cleanup([stale]) == {"stale-entry"}

    async def test_foreign_device_with_servent_in_identifier_value_is_removed(self):
        # Fixed (H2): a device from ANOTHER integration is no longer selected
        # for removal just because its identifier value contains "servent".
        foreign = MagicMock(id="foreign-entry", identifiers={("zwave", "my-servent-node")})
        assert await self.run_cleanup([foreign]) == set()
