from .const import DOMAIN, SERVENT_SENSOR, SERVENT_BINARY_SENSOR, SERVENT_BUTTON, SERVENT_SWITCH, SERVENT_NUMBER, SERVENT_SELECT, SERVENT_ENTITY, SERVENT_ID
from .utilities import get_all_device_ids, get_hass_object, get_platform_for_servent_id, load_config_from_file, store_hass_object
from .sensor import async_handle_create_sensor, handle_update_sensor_state
from .binary_sensor import async_handle_create_binary_sensor, handle_update_binary_sensor_state
from .switch import async_handle_create_switch
from .number import async_handle_create_number
from .select import async_handle_create_select
from .button import async_handle_create_button

import logging

from homeassistant.config_entries import ConfigEntry

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR,
                             Platform.BINARY_SENSOR,
                             Platform.NUMBER,
                             Platform.SELECT,
                             Platform.SWITCH]


async def handle_create_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    type = call.data.get('type')

    hass = get_hass_object()

    servent_id = call.data.get(SERVENT_ENTITY)[SERVENT_ID]

    platform = get_platform_for_servent_id(servent_id)

    if platform is not None and platform != type:
        raise Exception(
            f"Can't change the platform '{platform}' for an existing Ent: {servent_id}")

    if type == SERVENT_SENSOR:
        await async_handle_create_sensor(hass, call)
    elif type == SERVENT_BINARY_SENSOR:
        await async_handle_create_binary_sensor(hass, call)
    elif type == SERVENT_SWITCH:
        await async_handle_create_switch(hass, call)
    elif type == SERVENT_NUMBER:
        await async_handle_create_number(hass, call)
    elif type == SERVENT_SELECT:
        await async_handle_create_select(hass, call)
    elif type == SERVENT_BUTTON:
        await async_handle_create_button(hass, call)

    else:
        raise Exception("Invalid Type for Entity")


async def handle_update_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    servent_id = call.data['servent_id']
    state = call.data['state']
    attributes = call.data.get('attributes', {})

    platform = get_platform_for_servent_id(servent_id)

    if platform == SERVENT_SENSOR:
        handle_update_sensor_state(servent_id, state, attributes)
    elif platform == SERVENT_BINARY_SENSOR:
        handle_update_binary_sensor_state(servent_id, state, attributes)
    else:
        raise Exception("Non Registered ID")


def setup(hass, config):
    """Set up is called when Home Assistant is loading our component."""
    load_config_from_file()

    hass.services.register(DOMAIN, "create_entity", handle_create_entity)
    hass.services.register(DOMAIN, "update_state", handle_update_entity)

    # Return boolean to indicate that initialization was successful.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    store_hass_object(hass)

    device_registry = dr.async_get(hass)

    device_ids = get_all_device_ids()

    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        for identifier in device_entry.identifiers:
            if identifier[1] in device_ids:
                break
        else:
            device_registry.async_remove_device(device_entry.id)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
