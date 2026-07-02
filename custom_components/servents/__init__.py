import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    callback,
)
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
)
from .definitions import get_device_id, parse_entity_config, parse_update_entity
from .registrar import (
    ServentDefinitionRegistrar,
    get_registrar_from_hass,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@websocket_api.websocket_command(  # type: ignore
    {
        vol.Required("type"): "servent/hass-state",
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


async def handle_create_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    registrar = get_registrar_from_hass(call.hass)

    entities_list = call.data.get("entities", [])

    if not entities_list:
        raise Exception("Call does not define any entities")

    entities = [parse_entity_config(x) for x in entities_list]

    for definition in entities:
        try:
            registrar.register_definition(definition)
        except Exception as e:
            _LOGGER.error(e)

    register_and_update_all_entities(registrar)


async def handle_update_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    registrar = get_registrar_from_hass(call.hass)

    data = parse_update_entity(call.data)

    live_entity = registrar.get_live_entity_for_servent_id(data.servent_id)

    if live_entity:
        live_entity.set_new_state_and_attributes(data.state, data.attributes)
        live_entity.verified_schedule_update_ha_state()

    else:
        _LOGGER.warn(
            f"Tried to update a Non Registered ID {data.servent_id}. This can happen if you are sending an update event immediately after a creation event and the ID hasn't been registered yet"
        )


async def handle_cleanup_devices(call: ServiceCall) -> None:
    """Handle the service call."""
    hass = call.hass
    registrar = get_registrar_from_hass(hass)

    device_registry = dr.async_get(hass)

    definitions = registrar.get_all_entities()

    device_ids = set([get_device_id(x.device_definition) for x in definitions if x.device_definition])

    devices = [d for d in device_registry.devices.values() if any([a[0] == DOMAIN for a in d.identifiers])]

    for device_entry in devices:
        for identifier in device_entry.identifiers:
            if identifier[1] in device_ids:
                break
        else:
            device_registry.async_remove_device(device_entry.id)


def setup(hass: HomeAssistant, _config: ConfigEntry):
    """Set up is called when Home Assistant is loading our component."""

    hass.services.register(DOMAIN, "create_entity", handle_create_entity)
    hass.services.register(DOMAIN, "update_state", handle_update_entity)
    hass.services.register(DOMAIN, "cleanup_devices", handle_cleanup_devices)

    # Return boolean to indicate that initialization was successful.
    return True


def register_and_update_all_entities(registrar: ServentDefinitionRegistrar) -> None:
    ents = registrar.get_all_entities()

    for ent_config in ents:
        servent_id = ent_config.servent_id

        live_entity = registrar.get_live_entity_for_servent_id(servent_id)

        if live_entity is None:
            registrar.build_and_register_entity(ent_config)

        else:
            live_entity._update_servent_entity_config(ent_config)
            live_entity.verified_schedule_update_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    entry.runtime_data = ServentDefinitionRegistrar()

    websocket_api.async_register_command(hass, websocket_hass_is_up)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.bus.async_fire("servent.core_reloaded")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    registrar = getattr(entry, "runtime_data", None)
    if isinstance(registrar, ServentDefinitionRegistrar):
        registrar.release_hass_state_listeners()

    return unload_ok
