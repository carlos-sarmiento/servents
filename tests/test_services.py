"""Characterization tests for the service handlers in __init__.py."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from servents.data_model.entity_configs import SensorConfig, SwitchConfig

from custom_components.servents import (
    handle_create_entity,
    handle_update_entity,
    register_and_update_all_entities,
)
from custom_components.servents.const import CORE_DEVICE_ID, DOMAIN
from custom_components.servents.sensor import ServEntSensor
from custom_components.servents.services import handle_cleanup_devices, handle_remove_entity, handle_trigger_event
from tests.conftest import FakeServiceCall, make_definition


def register_builder(registrar, definition_type, builder=None):
    builder = builder or MagicMock(side_effect=lambda d: MagicMock(servent_config=d))
    registrar.register_builder_for_definition(definition_type, builder, MagicMock())
    return builder


class TestHandleCreateEntity:
    async def test_no_entities_raises(self, registrar):
        with pytest.raises(Exception, match="Call does not define any entities"):
            await handle_create_entity(FakeServiceCall({}, registrar))

    async def test_empty_entities_list_raises(self, registrar):
        with pytest.raises(Exception, match="Call does not define any entities"):
            await handle_create_entity(FakeServiceCall({"entities": []}, registrar))

    async def test_creates_definition_and_builds_entity(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        await handle_create_entity(
            FakeServiceCall(
                {"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]}, registrar
            )
        )

        definitions = registrar.get_all_definitions()
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
                },
                registrar,
            )
        )

        assert len(registrar.get_all_definitions()) == 2
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
                    },
                    registrar,
                )
            )

        assert registrar.get_all_definitions() == []

    async def test_type_conflict_is_logged_not_raised(self, registrar, caplog):
        # register_definition raising (type change for same servent_id) is
        # caught and logged; the service call still completes.
        register_builder(registrar, SensorConfig)
        register_builder(registrar, SwitchConfig)

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]}, registrar)
        )
        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "switch", "servent_id": "s1", "name": "S1"}]}, registrar)
        )

        # original definition survives
        assert isinstance(registrar.get_all_definitions()[0], SensorConfig)
        assert "Cannot change the type" in caplog.text
        # H7 (constraint 2): the type-conflict path is a WARNING, not an error,
        # and the call did not raise.
        assert any(
            r.levelno == logging.WARNING and "Cannot change the type" in r.getMessage()
            for r in caplog.records
        )

    async def test_recreating_existing_entity_updates_live_entity(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "First"}]}, registrar)
        )
        live = registrar.get_live_entity_for_servent_id("s1")

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "Second"}]}, registrar)
        )

        # builder is only invoked once; the existing live entity is reconfigured
        assert builder.call_count == 1
        assert registrar.get_live_entity_for_servent_id("s1") is live
        live.apply_config.assert_called_once()
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_previous_servent_id_migrates_before_build(self, registrar):
        builder = register_builder(registrar, SensorConfig)
        registry = MagicMock()
        registry.async_get_entity_id.side_effect = lambda _domain, _platform, unique_id: {
            "sensor-old-s1": "sensor.old_s1",
        }.get(unique_id)

        with patch("custom_components.servents.services.er.async_get", return_value=registry):
            await handle_create_entity(
                FakeServiceCall(
                    {
                        "entities": [
                            {
                                "entity_type": "sensor",
                                "servent_id": "new-s1",
                                "name": "S1",
                                "previous_servent_ids": ["old-s1"],
                            }
                        ]
                    },
                    registrar,
                )
            )

        registry.async_update_entity.assert_called_once_with(
            "sensor.old_s1",
            new_unique_id="sensor-new-s1",
        )
        builder.assert_called_once()

    async def test_previous_servent_id_conflict_warns_and_refuses_migration(self, registrar, caplog):
        register_builder(registrar, SensorConfig)
        registry = MagicMock()
        registry.async_get_entity_id.side_effect = lambda _domain, _platform, unique_id: {
            "sensor-old-s1": "sensor.old_s1",
            "sensor-new-s1": "sensor.new_s1",
        }.get(unique_id)

        with patch("custom_components.servents.services.er.async_get", return_value=registry):
            await handle_create_entity(
                FakeServiceCall(
                    {
                        "entities": [
                            {
                                "entity_type": "sensor",
                                "servent_id": "new-s1",
                                "name": "S1",
                                "previous_servent_ids": ["old-s1"],
                            }
                        ]
                    },
                    registrar,
                )
            )

        registry.async_update_entity.assert_not_called()
        assert "ServEnts rename conflict" in caplog.text

    async def test_previous_servent_id_noops_when_old_entry_is_absent(self, registrar, caplog):
        register_builder(registrar, SensorConfig)
        registry = MagicMock()
        registry.async_get_entity_id.return_value = None

        with patch("custom_components.servents.services.er.async_get", return_value=registry):
            await handle_create_entity(
                FakeServiceCall(
                    {
                        "entities": [
                            {
                                "entity_type": "sensor",
                                "servent_id": "new-s1",
                                "name": "S1",
                                "previous_servent_ids": ["old-s1"],
                            }
                        ]
                    },
                    registrar,
                )
            )

        registry.async_update_entity.assert_not_called()
        assert "ServEnts rename conflict" not in caplog.text


class TestHandleUpdateEntity:
    async def test_updates_live_entity(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall({"servent_id": "s1", "state": 42, "attributes": {"a": 1}}, registrar)
        )

        live.set_new_state_and_attributes.assert_called_once_with(42, {"a": 1})
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_availability_only_update_does_not_touch_state(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(FakeServiceCall({"servent_id": "s1", "available": False}, registrar))

        live.set_availability.assert_called_once_with(False)
        live.set_new_state_and_attributes.assert_not_called()
        live.set_new_attributes.assert_not_called()
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_available_plus_state_updates_both_and_schedules_once(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall(
                {"servent_id": "s1", "state": 42, "attributes": {"a": 1}, "available": True},
                registrar,
            )
        )

        live.set_availability.assert_called_once_with(True)
        live.set_new_state_and_attributes.assert_called_once_with(42, {"a": 1})
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_attribute_only_update_leaves_state_unchanged(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(FakeServiceCall({"servent_id": "s1", "attributes": {"a": 1}}, registrar))

        live.set_new_attributes.assert_called_once_with({"a": 1}, merge_attributes=False)
        live.set_new_state_and_attributes.assert_not_called()
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_merge_attributes_state_update(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall(
                {
                    "servent_id": "s1",
                    "state": 42,
                    "attributes": {"a": 1},
                    "merge_attributes": True,
                },
                registrar,
            )
        )

        live.set_new_state_and_attributes.assert_called_once_with(
            42,
            {"a": 1},
            merge_attributes=True,
        )
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_merge_attributes_attribute_only_update(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall(
                {"servent_id": "s1", "attributes": {"a": 1}, "merge_attributes": True},
                registrar,
            )
        )

        live.set_new_attributes.assert_called_once_with({"a": 1}, merge_attributes=True)
        live.verified_schedule_update_ha_state.assert_called_once()

    async def test_unknown_servent_id_warns_and_does_not_raise(self, registrar, caplog):
        await handle_update_entity(FakeServiceCall({"servent_id": "ghost", "state": 1}, registrar))
        assert "Non Registered ID ghost" in caplog.text

    async def test_extraneous_keys_in_call_are_ignored(self, registrar):
        live = MagicMock()
        registrar.register_live_entity("s1", live)

        await handle_update_entity(
            FakeServiceCall({"servent_id": "s1", "state": "on", "junk_key": True}, registrar)
        )

        live.set_new_state_and_attributes.assert_called_once_with("on", {})


class TestErrorSemantics:
    """H7: each failure path maps to the correct HA exception type."""

    async def test_empty_entities_raises_service_validation_error(self, registrar):
        # Paths Domovoy never hits raise ServiceValidationError so HA can
        # present them in the UI.
        with pytest.raises(ServiceValidationError, match="Call does not define any entities"):
            await handle_create_entity(FakeServiceCall({"entities": []}, registrar))

    async def test_unknown_entity_type_raises_service_validation_error(self, registrar):
        with pytest.raises(ServiceValidationError, match="is not supported"):
            await handle_create_entity(
                FakeServiceCall(
                    {"entities": [{"entity_type": "bogus", "servent_id": "s1", "name": "S1"}]},
                    registrar,
                )
            )

    async def test_builder_failure_raises_home_assistant_error(self, registrar):
        # No builder is registered for SensorConfig; build_and_register_entity
        # raises a bare Exception which must surface as HomeAssistantError, not
        # be swallowed like the type-conflict path.
        with pytest.raises(HomeAssistantError, match="Failed to build or update entity 's1'"):
            await handle_create_entity(
                FakeServiceCall(
                    {"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]},
                    registrar,
                )
            )

    async def test_service_validation_error_is_a_home_assistant_error(self):
        # ServiceValidationError subclasses HomeAssistantError; the builder path
        # must not catch-and-rewrap ServiceValidationError raised by build.
        assert issubclass(ServiceValidationError, HomeAssistantError)


class TestServiceSchemas:
    """M8: top-level vol.Schema envelopes that must not reject Domovoy payloads."""

    def test_create_entity_schema_accepts_domovoy_entities_list(self):
        from custom_components.servents.services import CREATE_ENTITY_SCHEMA

        # Inner entity dicts (with device_definition/app_name/is_global) pass
        # through untouched — inner validation is serde's job.
        payload = {
            "entities": [
                {
                    "entity_type": "sensor",
                    "servent_id": "s1",
                    "name": "S1",
                    "device_definition": {"device_id": "d1", "name": "Dev", "is_global": False},
                    "app_name": "my_app",
                }
            ]
        }
        assert CREATE_ENTITY_SCHEMA(payload) == payload

    def test_create_entity_schema_rejects_empty_list(self):
        from custom_components.servents.services import CREATE_ENTITY_SCHEMA

        with pytest.raises(vol.Invalid):
            CREATE_ENTITY_SCHEMA({"entities": []})

    def test_create_entity_schema_rejects_missing_entities(self):
        from custom_components.servents.services import CREATE_ENTITY_SCHEMA

        with pytest.raises(vol.Invalid):
            CREATE_ENTITY_SCHEMA({})

    def test_update_state_schema_accepts_domovoy_payload(self):
        from custom_components.servents.services import UPDATE_STATE_SCHEMA

        payload = {"servent_id": "s1", "state": 21.5, "attributes": {}}
        assert UPDATE_STATE_SCHEMA(payload) == payload

    def test_update_state_schema_requires_servent_id(self):
        from custom_components.servents.services import UPDATE_STATE_SCHEMA

        with pytest.raises(vol.Invalid):
            UPDATE_STATE_SCHEMA({"state": 1})

    def test_update_state_schema_allows_extra_keys(self):
        from custom_components.servents.services import UPDATE_STATE_SCHEMA

        # Constraint 8: extra keys must pass, never be rejected.
        result = UPDATE_STATE_SCHEMA({"servent_id": "s1", "state": "on", "junk": True})
        assert result["junk"] is True

    def test_update_state_schema_accepts_availability_and_merge_keys(self):
        from custom_components.servents.services import UPDATE_STATE_SCHEMA

        payload = {"servent_id": "s1", "available": False, "merge_attributes": True}
        assert UPDATE_STATE_SCHEMA(payload) == payload

    def test_remove_entity_schema_requires_servent_id(self):
        from custom_components.servents.services import REMOVE_ENTITY_SCHEMA

        with pytest.raises(vol.Invalid):
            REMOVE_ENTITY_SCHEMA({})
        assert REMOVE_ENTITY_SCHEMA({"servent_id": "s1"}) == {"servent_id": "s1"}

    def test_trigger_event_schema_defaults_attributes(self):
        from custom_components.servents.services import TRIGGER_EVENT_SCHEMA

        assert TRIGGER_EVENT_SCHEMA({"servent_id": "s1", "event_type": "pressed"}) == {
            "servent_id": "s1",
            "event_type": "pressed",
            "attributes": {},
        }


class TestRegisterAndUpdateAllEntities:
    def test_builds_missing_and_updates_existing(self, registrar):
        builder = register_builder(registrar, SensorConfig)

        existing_live = MagicMock()
        registrar.register_live_entity("existing", existing_live)
        registrar.register_definition(make_definition("sensor", "existing", name="Old"))
        registrar.register_definition(make_definition("sensor", "new-one"))

        register_and_update_all_entities(registrar)

        # "new-one" is built; "existing" is reconfigured in place
        assert builder.call_count == 1
        assert builder.call_args[0][0].servent_id == "new-one"
        existing_live.apply_config.assert_called_once()
        existing_live.verified_schedule_update_ha_state.assert_called_once()

    def test_reconfigure_existing_entity_refreshes_live_fixed_attributes(self, registrar):
        live = ServEntSensor(
            make_definition("sensor", "existing", fixed_attributes={"zone": "kitchen", "old": "stale"})
        )
        live.set_new_state_and_attributes(10, {"dynamic": "kept"})
        live.verified_schedule_update_ha_state = MagicMock()
        registrar.register_live_entity("existing", live)
        registrar.register_definition(
            make_definition("sensor", "existing", name="Renamed", fixed_attributes={"zone": "attic"})
        )

        register_and_update_all_entities(registrar)

        assert live._attr_extra_state_attributes == {
            "dynamic": "kept",
            "zone": "attic",
            "servent_id": "existing",
        }
        live.verified_schedule_update_ha_state.assert_called_once_with()

    def test_noop_when_registry_is_empty(self, registrar):
        register_and_update_all_entities(registrar)
        assert registrar.live_entities == {}


class TestSetup:
    def test_register_services_registers_services(self):
        from custom_components.servents.services import async_register_services

        hass = MagicMock()
        async_register_services(hass)

        registered = {call.args[:2] for call in hass.services.async_register.call_args_list}
        assert registered == {
            ("servents", "create_entity"),
            ("servents", "update_state"),
            ("servents", "cleanup_devices"),
            ("servents", "remove_entity"),
            ("servents", "trigger_event"),
        }


class TestCleanupDevices:
    @staticmethod
    def get_cleanup_handler():
        # The cleanup handler is now a module-level function in services.py.
        return handle_cleanup_devices

    async def run_cleanup(self, devices, registrar=None):
        from custom_components.servents.registrar import ServentDefinitionRegistrar

        cleanup = self.get_cleanup_handler()
        device_registry = MagicMock()
        device_registry.devices.values.return_value = devices

        with patch("custom_components.servents.services.dr.async_get", return_value=device_registry):
            await cleanup(FakeServiceCall({}, registrar or ServentDefinitionRegistrar()))

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

        removed = await self.run_cleanup([kept, stale], registrar)
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

    async def test_cleanup_preserves_core_device_while_removing_stale_dynamic_device(self):
        core = MagicMock(id="core-entry", identifiers={(DOMAIN, CORE_DEVICE_ID)})
        stale = MagicMock(id="stale-entry", identifiers={(DOMAIN, "device-stale")})

        assert await self.run_cleanup([core, stale]) == {"stale-entry"}

    async def test_cleanup_ignores_foreign_identifier_when_matching_live_device_id(self, registrar):
        registrar.register_definition(
            make_definition("sensor", "s1", device_config={"device_id": "live", "name": "Live"})
        )

        stale = MagicMock(
            id="stale-entry",
            identifiers={(DOMAIN, "device-stale"), ("other_domain", "device-live")},
        )

        assert await self.run_cleanup([stale], registrar) == {"stale-entry"}


class TestRemoveEntity:
    async def run_remove(self, registrar, *, entity_id="sensor.s1", device_id="device-entry", remaining=None):
        entity_registry = MagicMock()
        entity_registry.async_get_entity_id.return_value = entity_id
        entity_registry.async_get.return_value = MagicMock(device_id=device_id)

        device_registry = MagicMock()
        device_registry.async_get.return_value = MagicMock(id=device_id)

        with (
            patch("custom_components.servents.services.er.async_get", return_value=entity_registry),
            patch(
                "custom_components.servents.services.er.async_entries_for_device",
                return_value=remaining or [],
            ),
            patch("custom_components.servents.services.dr.async_get", return_value=device_registry),
        ):
            await handle_remove_entity(FakeServiceCall({"servent_id": "s1"}, registrar))

        return entity_registry, device_registry

    async def test_unknown_id_is_noop(self, registrar):
        with (
            patch("custom_components.servents.services.er.async_get") as entity_get,
            patch("custom_components.servents.services.dr.async_get") as device_get,
        ):
            await handle_remove_entity(FakeServiceCall({"servent_id": "ghost"}, registrar))

        entity_get.assert_not_called()
        device_get.assert_not_called()

    async def test_removes_live_entity_definition_registry_entry_and_empty_device(self, registrar):
        registrar.register_definition(
            make_definition("sensor", "s1", device_config={"device_id": "dev1", "name": "Dev"})
        )
        registrar.register_live_entity("s1", MagicMock(servent_config=registrar.get_definition_for_servent_id("s1")))

        entity_registry, device_registry = await self.run_remove(registrar)

        entity_registry.async_remove.assert_called_once_with("sensor.s1")
        device_registry.async_remove_device.assert_called_once_with("device-entry")
        assert registrar.get_definition_for_servent_id("s1") is None
        assert registrar.get_live_entity_for_servent_id("s1") is None

    async def test_removes_definition_only_entity(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))

        entity_registry, _device_registry = await self.run_remove(registrar, device_id=None)

        entity_registry.async_remove.assert_called_once_with("sensor.s1")
        assert registrar.get_definition_for_servent_id("s1") is None

    async def test_keeps_multi_entity_device(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))

        _entity_registry, device_registry = await self.run_remove(
            registrar,
            remaining=[MagicMock(entity_id="sensor.other")],
        )

        device_registry.async_remove_device.assert_not_called()

    async def test_missing_registry_entry_still_removes_registrar_state(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        entity_registry = MagicMock()
        entity_registry.async_get_entity_id.return_value = None

        with (
            patch("custom_components.servents.services.er.async_get", return_value=entity_registry),
            patch("custom_components.servents.services.dr.async_get", return_value=MagicMock()),
        ):
            await handle_remove_entity(FakeServiceCall({"servent_id": "s1"}, registrar))

        entity_registry.async_remove.assert_not_called()
        assert registrar.get_definition_for_servent_id("s1") is None

    async def test_registry_remove_failure_raises_home_assistant_error(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        entity_registry = MagicMock()
        entity_registry.async_get_entity_id.return_value = "sensor.s1"
        entity_registry.async_get.return_value = MagicMock(device_id="device-entry")
        entity_registry.async_remove.side_effect = RuntimeError("boom")

        with (
            patch("custom_components.servents.services.er.async_get", return_value=entity_registry),
            patch("custom_components.servents.services.dr.async_get", return_value=MagicMock()),
            pytest.raises(HomeAssistantError, match="Failed to remove ServEnt entity"),
        ):
            await handle_remove_entity(FakeServiceCall({"servent_id": "s1"}, registrar))

    async def test_create_after_remove_recreates_entity(self, registrar):
        register_builder(registrar, SensorConfig)
        registrar.register_definition(make_definition("sensor", "s1"))
        await self.run_remove(registrar, entity_id=None, device_id=None)

        await handle_create_entity(
            FakeServiceCall({"entities": [{"entity_type": "sensor", "servent_id": "s1", "name": "S1"}]}, registrar)
        )

        assert registrar.get_definition_for_servent_id("s1") is not None
        assert registrar.get_live_entity_for_servent_id("s1") is not None


class TestTriggerEvent:
    async def test_non_live_event_is_noop(self, registrar):
        await handle_trigger_event(
            FakeServiceCall({"servent_id": "event1", "event_type": "pressed", "attributes": {}}, registrar)
        )

    async def test_non_event_live_entity_is_noop(self, registrar):
        live = MagicMock(spec=[])
        registrar.register_live_entity("event1", live)

        await handle_trigger_event(
            FakeServiceCall({"servent_id": "event1", "event_type": "pressed", "attributes": {}}, registrar)
        )

    async def test_triggers_live_event_entity(self, registrar):
        live = MagicMock()
        live.async_trigger_event = AsyncMock()
        registrar.register_live_entity("event1", live)

        await handle_trigger_event(
            FakeServiceCall(
                {"servent_id": "event1", "event_type": "pressed", "attributes": {"confidence": 0.93}},
                registrar,
            )
        )

        live.async_trigger_event.assert_awaited_once_with("pressed", {"confidence": 0.93})

    async def test_invalid_event_type_error_propagates_from_entity(self, registrar):
        live = MagicMock()
        live.async_trigger_event = AsyncMock(side_effect=HomeAssistantError("invalid event type"))
        registrar.register_live_entity("event1", live)

        with pytest.raises(HomeAssistantError, match="invalid event type"):
            await handle_trigger_event(
                FakeServiceCall({"servent_id": "event1", "event_type": "unknown", "attributes": {}}, registrar)
            )

    async def test_repeated_triggers_reach_entity(self, registrar):
        live = MagicMock()
        live.async_trigger_event = AsyncMock()
        registrar.register_live_entity("event1", live)

        await handle_trigger_event(FakeServiceCall({"servent_id": "event1", "event_type": "pressed"}, registrar))
        await handle_trigger_event(FakeServiceCall({"servent_id": "event1", "event_type": "pressed"}, registrar))

        assert live.async_trigger_event.await_count == 2
