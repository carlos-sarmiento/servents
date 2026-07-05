import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    callback,
)

from .registrar import (
    ServentDefinitionRegistrar,
    get_registrar_from_hass,
)
from .services import (
    async_register_services,
    async_unregister_services,
    handle_create_entity,
    handle_update_entity,
    register_and_update_all_entities,
)

__all__ = [
    "async_setup_entry",
    "async_unload_entry",
    "handle_create_entity",
    "handle_update_entity",
    "register_and_update_all_entities",
    "websocket_hass_is_up",
]

WEBSOCKET_COMMAND = "servent/hass-state"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATE,
    Platform.DATETIME,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.TIME,
]


@websocket_api.websocket_command(  # type: ignore
    {
        vol.Required("type"): WEBSOCKET_COMMAND,
    }
)
@callback
def websocket_hass_is_up(
    hass: HomeAssistant,
    connection: websocket_api.connection.ActiveConnection,
    msg: dict,
) -> None:
    """Report whether Home Assistant has finished starting."""
    connection.send_result(msg["id"], {"is_hass_up": get_registrar_from_hass(hass).is_hass_up})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    entry.runtime_data = ServentDefinitionRegistrar()

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Services and the websocket command are registered only after platform
        # setup succeeds. If setup fails, the exception handler below removes
        # any platform listeners and any partially registered global handlers.
        async_register_services(hass)
        websocket_api.async_register_command(hass, websocket_hass_is_up)

        # L10: Fire the core_reloaded event only on actual reload, not first install.
        # Track entries that have been set up to distinguish reload from first setup.
        setup_entries = hass.data.setdefault("servents_setup_entries", set())
        if entry.entry_id in setup_entries:
            # This entry has been set up before, so this is a reload.
            hass.bus.async_fire("servent.core_reloaded")
        else:
            # First time setting up this entry.
            setup_entries.add(entry.entry_id)
    except Exception:
        _async_teardown_entry(hass, entry)
        raise

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    _async_teardown_entry(hass, entry)

    return unload_ok


def _async_teardown_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove global handlers and per-entry listeners after successful teardown."""
    async_unregister_services(hass)
    _async_unregister_websocket_command(hass)

    registrar = getattr(entry, "runtime_data", None)
    if isinstance(registrar, ServentDefinitionRegistrar):
        registrar.release_hass_state_listeners()


def _async_unregister_websocket_command(hass: HomeAssistant) -> None:
    """Remove the servent/hass-state websocket command on unload.

    websocket_api has no public unregister API; commands live in
    ``hass.data[websocket_api.DOMAIN]`` keyed by command string (see
    ``async_register_command``). Pop our entry directly so a reload does not
    leave a handler pointing at a torn-down registrar. The command name and its
    ``{"is_hass_up": bool}`` response shape are unchanged (constraint 4).
    """
    handlers = hass.data.get(websocket_api.const.DOMAIN)
    if handlers is not None:
        handlers.pop(WEBSOCKET_COMMAND, None)
