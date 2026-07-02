"""Characterization tests for registrar.py: the definition/live-entity registry."""

from unittest.mock import MagicMock

import pytest

from servents.data_model.entity_configs import BinarySensorConfig, SensorConfig

from custom_components.servents import registrar as registrar_module
from custom_components.servents.registrar import (
    ServentDefinitionRegistrar,
    get_registrar,
    reset_registrar,
)
from tests.conftest import make_definition


class TestRegisterDefinition:
    def test_register_and_retrieve(self, registrar):
        definition = make_definition("sensor", "s1")
        registrar.register_definition(definition)
        assert registrar.get_all_entities() == [definition]

    def test_reregister_same_id_same_type_replaces(self, registrar):
        first = make_definition("sensor", "s1", name="First")
        second = make_definition("sensor", "s1", name="Second")
        registrar.register_definition(first)
        registrar.register_definition(second)

        all_entities = registrar.get_all_entities()
        assert len(all_entities) == 1
        assert all_entities[0].name == "Second"

    def test_reregister_same_id_different_type_raises(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        with pytest.raises(Exception, match="Cannot change the type of entity with servent_id s1"):
            registrar.register_definition(make_definition("switch", "s1"))

    def test_reregister_with_subclass_of_old_type_is_allowed(self, registrar):
        # The check is isinstance(new, type(old)), not type equality:
        # replacing a definition with a subclass instance is currently permitted.
        class Sub(SensorConfig):
            pass

        registrar.register_definition(make_definition("sensor", "s1"))
        registrar.register_definition(Sub(servent_id="s1", name="Sub"))
        assert type(registrar.get_all_entities()[0]) is Sub

    def test_multiple_ids_coexist(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        registrar.register_definition(make_definition("switch", "s2"))
        assert len(registrar.get_all_entities()) == 2


class TestGetEntitiesOfType:
    def test_filters_by_type(self, registrar):
        sensor = make_definition("sensor", "s1")
        binary = make_definition("binary_sensor", "b1")
        registrar.register_definition(sensor)
        registrar.register_definition(binary)

        assert registrar.get_entities_of_type(SensorConfig) == [sensor]
        assert registrar.get_entities_of_type(BinarySensorConfig) == [binary]

    def test_empty_when_no_match(self, registrar):
        registrar.register_definition(make_definition("sensor", "s1"))
        assert registrar.get_entities_of_type(BinarySensorConfig) == []


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
        # Builders are keyed by str(type(definition)) — a definition whose exact
        # type has no builder raises even if a parent type has one.
        registrar.register_builder_for_definition(SensorConfig, MagicMock(), MagicMock())

        class Sub(SensorConfig):
            pass

        with pytest.raises(Exception, match="There is no builder registered for type"):
            registrar.build_and_register_entity(Sub(servent_id="s1", name="X"))


class TestModuleSingleton:
    def test_get_registrar_returns_singleton(self):
        assert get_registrar() is get_registrar()

    def test_reset_registrar_swaps_instance_and_marks_hass_up(self):
        before = get_registrar()
        before.set_hass_up(False)
        reset_registrar()
        after = get_registrar()
        assert after is not before
        assert after.is_hass_up is True

    def test_default_state_of_fresh_instance(self):
        fresh = ServentDefinitionRegistrar()
        assert fresh.entity_definitions == {}
        assert fresh.live_entities == {}
        assert fresh.entity_builders == {}
        assert fresh.is_hass_up is False

    def test_set_hass_up(self):
        registrar = registrar_module.get_registrar()
        registrar.set_hass_up(False)
        assert registrar.is_hass_up is False
        registrar.set_hass_up(True)
        assert registrar.is_hass_up is True
