"""Tests for the ServEnts config-entry lifecycle."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.components import websocket_api

from custom_components.servents import PLATFORMS, WEBSOCKET_COMMAND, async_setup_entry, async_unload_entry
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


async def test_async_setup_entry_cleans_up_platform_listeners_when_platform_setup_fails():
    hass = MagicMock()
    hass.data = {}
    unsubscribe = MagicMock()

    async def fail_forward_entry_setups(entry, _platforms):
        entry.runtime_data.unsub_hass_state_listeners.append(unsubscribe)
        raise RuntimeError("platform setup failed")

    hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=fail_forward_entry_setups)
    entry = MagicMock(entry_id="entry-1")

    with patch("custom_components.servents.websocket_api.async_register_command") as register_command:
        with pytest.raises(RuntimeError, match="platform setup failed"):
            await async_setup_entry(hass, entry)

    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)
    hass.services.async_register.assert_not_called()
    register_command.assert_not_called()
    unsubscribe.assert_called_once_with()
    assert entry.runtime_data.unsub_hass_state_listeners == []


async def test_async_setup_entry_cleans_up_partial_globals_when_late_registration_fails():
    hass = MagicMock()
    hass.data = {websocket_api.const.DOMAIN: {WEBSOCKET_COMMAND: MagicMock(), "other/command": MagicMock()}}
    unsubscribe = MagicMock()

    async def forward_entry_setups(entry, _platforms):
        entry.runtime_data.unsub_hass_state_listeners.append(unsubscribe)

    hass.config_entries.async_forward_entry_setups = AsyncMock(side_effect=forward_entry_setups)
    entry = MagicMock(entry_id="entry-1")

    with patch(
        "custom_components.servents.websocket_api.async_register_command",
        side_effect=RuntimeError("websocket registration failed"),
    ):
        with pytest.raises(RuntimeError, match="websocket registration failed"):
            await async_setup_entry(hass, entry)

    hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(entry, PLATFORMS)
    assert {call.args[:2] for call in hass.services.async_register.call_args_list} == {
        (DOMAIN, SERVICE_CREATE_ENTITY),
        (DOMAIN, SERVICE_UPDATE_STATE),
        (DOMAIN, SERVICE_CLEANUP_DEVICES),
    }
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
    assert entry.runtime_data.unsub_hass_state_listeners == []


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
