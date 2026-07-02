"""Shared fixtures for the ServEnts characterization test suite.

These tests pin down the current behavior of the integration before a
refactor. They intentionally test quirks as well as intended behavior, so a
failing test after the refactor means "behavior changed" — decide consciously
whether that change is desired, then update the test.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.servents.const import DOMAIN
from custom_components.servents.definitions import parse_entity_config
from custom_components.servents.registrar import ServentDefinitionRegistrar


def make_hass_for_registrar(registrar: ServentDefinitionRegistrar) -> MagicMock:
    """A hass whose single ServEnts config entry carries the given registrar.

    Mirrors production access: service handlers and the websocket resolve the
    registrar via ``hass.config_entries.async_entries(DOMAIN)`` →
    ``entry.runtime_data``.
    """
    entry = MagicMock()
    entry.runtime_data = registrar

    hass = MagicMock()
    hass.config_entries.async_entries.side_effect = lambda domain: [entry] if domain == DOMAIN else []
    return hass


@pytest.fixture
def registrar():
    """A fresh per-entry registrar; handlers reach it via FakeServiceCall.hass."""
    return ServentDefinitionRegistrar()


@pytest.fixture
def mock_hass():
    return MagicMock()


class FakeServiceCall:
    """Minimal stand-in for homeassistant.core.ServiceCall.

    Handlers resolve the registrar from ``call.hass``; pass a ``registrar`` so
    the fake wires up a matching hass, or an explicit ``hass``.
    """

    def __init__(self, data: dict, registrar: ServentDefinitionRegistrar | None = None, hass=None):
        self.data = data
        if hass is not None:
            self.hass = hass
        elif registrar is not None:
            self.hass = make_hass_for_registrar(registrar)
        else:
            self.hass = MagicMock()


@pytest.fixture
def make_service_call():
    return FakeServiceCall


def make_definition(entity_type: str = "sensor", servent_id: str = "test-id", name: str = "Test", **extra):
    return parse_entity_config({"entity_type": entity_type, "servent_id": servent_id, "name": name, **extra})


@pytest.fixture
def definition_factory():
    return make_definition
