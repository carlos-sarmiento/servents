import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

from custom_components.servents.registrar import get_registrar, reset_registrar

from .const import (
    DOMAIN,
)
from .data_carriers import ServentUpdateEntityDefinition, clean_params_and_build, to_dataclass

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def handle_create_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    data = call.data.copy()
    entities_list = data.get("entities", [])

    if not entities_list:
        raise Exception("Call does not define any entities")

    entities = [to_dataclass(x) for x in entities_list]

    for definition in entities:
        try:
            get_registrar().register_definition(definition)
        except Exception as e:
            _LOGGER.error(e)

    register_and_update_all_entities()


async def handle_update_entity(call: ServiceCall) -> None:
    """Handle the service call."""

    data = clean_params_and_build(ServentUpdateEntityDefinition, call.data)

    live_entity = get_registrar().get_live_entity_for_servent_id(data.servent_id)

    if live_entity:
        live_entity.set_new_state_and_attributes(data.state, data.attributes)
        live_entity.verified_schedule_update_ha_state()

    else:
        _LOGGER.warn(
            f"Tried to update a Non Registered ID {data.servent_id}. This can happen if you are sending an update event immediately after a creation event and the ID hasn't been registered yet"
        )


def setup(hass: HomeAssistant, _entry: ConfigEntry):
    """Set up is called when Home Assistant is loading our component."""

    async def handle_cleanup_devices(_call: ServiceCall) -> None:
        """Handle the service call."""

        device_registry = dr.async_get(hass)

        live_entity = get_registrar().get_all_entities()

        device_ids = set([x.device_definition.get_device_id() for x in live_entity if x.device_definition])

        devices = [d for d in device_registry.devices.values() if any(["servent" in a[1] for a in d.identifiers])]

        for device_entry in devices:
            for identifier in device_entry.identifiers:
                if identifier[1] in device_ids:
                    break
            else:
                device_registry.async_remove_device(device_entry.id)

    hass.services.register(DOMAIN, "create_entity", handle_create_entity)
    hass.services.register(DOMAIN, "update_state", handle_update_entity)
    hass.services.register(DOMAIN, "cleanup_devices", handle_cleanup_devices)

    # Return boolean to indicate that initialization was successful.
    return True


def register_and_update_all_entities() -> None:
    registrar = get_registrar()
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.bus.async_fire("servent.core_reloaded")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    reset_registrar()

    return unload_ok
