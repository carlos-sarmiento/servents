"""Characterization tests for registrar.py: the definition/live-entity registry."""

from unittest.mock import MagicMock

import pytest

from servents.data_model.entity_configs import BinarySensorConfig, SensorConfig

from custom_components.servents.registrar import (
    ServentDefinitionRegistrar,
    get_registrar_for_entry,
    get_registrar_from_hass,
)
from tests.conftest import make_definition, make_hass_for_registrar


class TestRegisterDefinition:
    def test_register_and_retrieve(self, registrar):
        definition = make_definition("sensor", "s1")
        registrar.register_definition(definition)
        assert registrar.get_all_definitions() == [definition]

    def test_reregister_same_id_same_type_replaces(self, registrar):
        first = make_definition("sensor", "s1", name="First")
        second = make_definition("sensor", "s1", name="Second")
        registrar.register_definition(first)
        registrar.register_definition(second)

        all_definitions = registrar.get_all_definitions()
        assert len(all_definitions) == 1
        assert all_definitions[0].name == "Second"

    def test_reregister_same_id_different_type_raises(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        with pytest.raises(Exception, match="Cannot change the type of entity with servent_id s1"):
            registrar.register_definition(make_definition("switch", "s1"))

    def test_reregister_with_subclass_of_old_type_is_allowed(self, registrar):
        # register_definition uses isinstance(new, type(old)), so replacing a
        # definition with a subclass instance is accepted. This still holds
        # after M5, but note the counterpart in TestBuilders: build dispatch is
        # now exact-type, so a subclass replacement will not find the parent's
        # builder — registration acceptance and build dispatch are separate
        # checks and both are intentional.
        class Sub(SensorConfig):
            pass

        registrar.register_definition(make_definition("sensor", "s1"))
        registrar.register_definition(Sub(servent_id="s1", name="Sub"))
        assert type(registrar.get_all_definitions()[0]) is Sub

    def test_multiple_ids_coexist(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        registrar.register_definition(make_definition("switch", "s2"))
        assert len(registrar.get_all_definitions()) == 2


class TestGetDefinitionsOfType:
    def test_filters_by_type(self, registrar):
        sensor = make_definition("sensor", "s1")
        binary = make_definition("binary_sensor", "b1")
        registrar.register_definition(sensor)
        registrar.register_definition(binary)

        assert registrar.get_definitions_of_type(SensorConfig) == [sensor]
        assert registrar.get_definitions_of_type(BinarySensorConfig) == [binary]

    def test_empty_when_no_match(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        assert registrar.get_definitions_of_type(BinarySensorConfig) == []


class TestLiveEntities:
    def test_get_live_entity_returns_none_when_unknown(self, registrar):
        assert registrar.get_live_entity_for_servent_id("nope") is None

    def test_register_and_get_live_entity(self, registrar):
        entity = MagicMock()
        registrar.register_live_entity("s1", entity)
        assert registrar.get_live_entity_for_servent_id("s1") is entity


class TestBuilders:
    def test_build_without_registered_builder_raises(self, registrar):
        definition = make_definition("sensor", "s1")
        with pytest.raises(Exception, match="There is no builder registered for type"):
            registrar.build_and_register_entity(definition)

    def test_registered_builder_builds_registers_and_adds(self, registrar):
        built_entity = MagicMock()
        builder = MagicMock(return_value=built_entity)
        async_add_entities = MagicMock()

        registrar.register_builder_for_definition(SensorConfig, builder, async_add_entities)

        definition = make_definition("sensor", "s1")
        result = registrar.build_and_register_entity(definition)

        assert result is built_entity
        builder.assert_called_once_with(definition)
        async_add_entities.assert_called_once_with([built_entity])
        assert registrar.get_live_entity_for_servent_id("s1") is built_entity

    def test_builder_dispatch_is_by_exact_type(self, registrar):
        # M5: builders are keyed by the type OBJECT (was str(type(...))), with
        # exact-type dispatch. A definition whose exact type has no builder
        # raises even if a parent type has one. Registration and dispatch now
        # use the same key (the type object) rather than a stringified type.
        registrar.register_builder_for_definition(SensorConfig, MagicMock(), MagicMock())

        class Sub(SensorConfig):
            pass

        with pytest.raises(Exception, match="There is no builder registered for type"):
            registrar.build_and_register_entity(Sub(servent_id="s1", name="X"))

    def test_builder_keys_are_type_objects_not_strings(self, registrar):
        # M5: entity_builders is keyed by the type object, not str(type(...)).
        registrar.register_builder_for_definition(SensorConfig, MagicMock(), MagicMock())
        assert SensorConfig in registrar.entity_builders
        assert str(SensorConfig) not in registrar.entity_builders


class TestEntryAccess:
    # S1: the registrar is per-config-entry state on entry.runtime_data, no
    # module-level singleton. Domain-global callers resolve it from hass via
    # the single DOMAIN config entry.
    def test_get_registrar_for_entry_returns_runtime_data(self):
        entry = MagicMock()
        entry.runtime_data = ServentDefinitionRegistrar()
        assert get_registrar_for_entry(entry) is entry.runtime_data

    def test_get_registrar_for_entry_raises_when_uninitialized(self):
        entry = MagicMock()
        entry.runtime_data = None
        with pytest.raises(Exception, match="no initialized registrar"):
            get_registrar_for_entry(entry)

    def test_get_registrar_from_hass_resolves_single_entry(self):
        registrar = ServentDefinitionRegistrar()
        hass = make_hass_for_registrar(registrar)
        assert get_registrar_from_hass(hass) is registrar

    def test_get_registrar_from_hass_raises_when_no_entry(self):
        hass = MagicMock()
        hass.config_entries.async_entries.side_effect = lambda _domain: []
        with pytest.raises(Exception, match="No ServEnts config entry"):
            get_registrar_from_hass(hass)

    def test_default_state_of_fresh_instance(self):
        fresh = ServentDefinitionRegistrar()
        assert fresh.entity_definitions == {}
        assert fresh.live_entities == {}
        assert fresh.entity_builders == {}
        assert fresh.is_hass_up is False

    def test_set_hass_up(self):
        registrar = ServentDefinitionRegistrar()
        registrar.set_hass_up(False)
        assert registrar.is_hass_up is False
        registrar.set_hass_up(True)
        assert registrar.is_hass_up is True

    def test_release_hass_state_listeners_calls_and_clears(self):
        registrar = ServentDefinitionRegistrar()
        unsub_a = MagicMock()
        unsub_b = MagicMock()
        registrar.unsub_hass_state_listeners.extend([unsub_a, unsub_b])
        registrar.release_hass_state_listeners()
        unsub_a.assert_called_once_with()
        unsub_b.assert_called_once_with()
        assert registrar.unsub_hass_state_listeners == []
