"""Shared fixtures for the ServEnts characterization test suite.

These tests pin down the current behavior of the integration before a
refactor. They intentionally test quirks as well as intended behavior, so a
failing test after the refactor means "behavior changed" — decide consciously
whether that change is desired, then update the test.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.servents import registrar as registrar_module
from custom_components.servents.definitions import parse_entity_config


@pytest.fixture(autouse=True)
def fresh_registrar():
    """The registrar is a module-level singleton; isolate each test."""
    registrar_module.reset_registrar()
    yield registrar_module.get_registrar()
    registrar_module.reset_registrar()


@pytest.fixture
def registrar(fresh_registrar):
    return fresh_registrar


@pytest.fixture
def mock_hass():
    return MagicMock()


class FakeServiceCall:
    """Minimal stand-in for homeassistant.core.ServiceCall."""

    def __init__(self, data: dict):
        self.data = data


@pytest.fixture
def make_service_call():
    return FakeServiceCall


def make_definition(entity_type: str = "sensor", servent_id: str = "test-id", name: str = "Test", **extra):
    return parse_entity_config({"entity_type": entity_type, "servent_id": servent_id, "name": name, **extra})


@pytest.fixture
def definition_factory():
    return make_definition
