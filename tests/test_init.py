"""Tests for the ServEnts config-entry lifecycle."""

from unittest.mock import AsyncMock, MagicMock, call

from homeassistant.components import websocket_api

from custom_components.servents import PLATFORMS, WEBSOCKET_COMMAND, async_unload_entry
from custom_components.servents.const import DOMAIN
from custom_components.servents.registrar import ServentDefinitionRegistrar
from custom_components.servents.services import (
    SERVICE_CLEANUP_DEVICES,
    SERVICE_CREATE_ENTITY,
    SERVICE_UPDATE_STATE,
)


def _make_unload_hass(unload_ok: bool) -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=unload_ok)
    hass.data = {
        websocket_api.const.DOMAIN: {
            WEBSOCKET_COMMAND: MagicMock(),
            "other/command": MagicMock(),
        }
    }
    return hass


def _make_unload_entry(registrar: ServentDefinitionRegistrar) -> MagicMock:
    entry = MagicMock()
    entry.runtime_data = registrar
    return entry


async def test_async_unload_entry_preserves_teardown_side_effects_when_platform_unload_fails():
    registrar = ServentDefinitionRegistrar()
    unsubscribe = MagicMock()
    registrar.unsub_hass_state_listeners.append(unsubscribe)
    entry = _make_unload_entry(registrar)
    hass = _make_unload_hass(False)

    assert await async_unload_entry(hass, entry) is False

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
    hass.services.async_remove.assert_not_called()
    assert WEBSOCKET_COMMAND in hass.data[websocket_api.const.DOMAIN]
    unsubscribe.assert_not_called()
    assert registrar.unsub_hass_state_listeners == [unsubscribe]


async def test_async_unload_entry_tears_down_services_websocket_and_listeners_after_successful_unload():
    registrar = ServentDefinitionRegistrar()
    unsubscribe = MagicMock()
    registrar.unsub_hass_state_listeners.append(unsubscribe)
    entry = _make_unload_entry(registrar)
    hass = _make_unload_hass(True)

    assert await async_unload_entry(hass, entry) is True

    hass.config_entries.async_unload_platforms.assert_awaited_once_with(entry, PLATFORMS)
    hass.services.async_remove.assert_has_calls(
        [
            call(DOMAIN, SERVICE_CREATE_ENTITY),
            call(DOMAIN, SERVICE_UPDATE_STATE),
            call(DOMAIN, SERVICE_CLEANUP_DEVICES),
        ]
    )
    assert WEBSOCKET_COMMAND not in hass.data[websocket_api.const.DOMAIN]
    assert "other/command" in hass.data[websocket_api.const.DOMAIN]
    unsubscribe.assert_called_once_with()
    assert registrar.unsub_hass_state_listeners == []
