from .const import (
    DOMAIN,
    SERVENT_SENSOR,
    SERVENT_BINARY_SENSOR,
    SERVENT_BUTTON,
    SERVENT_SWITCH,
    SERVENT_NUMBER,
    SERVENT_SELECT,
    SERVENT_ENTITY,
    SERVENT_ID,
)
from .utilities import (
    get_all_device_ids,
    get_hass_object,
    get_live_entities_from_cache,
    get_platform_for_servent_id,
    load_config_from_file,
    servent_reset_config,
    store_hass_object,
)
from .sensor import async_handle_create_sensor
from .binary_sensor import (
    async_handle_create_binary_sensor,
)
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
    type = data.get("type")

    hass = get_hass_object()

    servent_id = call.data.get(SERVENT_ENTITY)[SERVENT_ID]

    platform = get_platform_for_servent_id(servent_id)

    if platform is not None and platform != type:
        raise Exception(
            f"Can't change the platform '{platform}' for an existing Ent: {servent_id}"
        )

    if type == SERVENT_SENSOR:
        await async_handle_create_sensor(hass, data)
    elif type == SERVENT_BINARY_SENSOR:
        await async_handle_create_binary_sensor(hass, data)
    elif type == SERVENT_SWITCH:
        await async_handle_create_switch(hass, data)
    elif type == SERVENT_NUMBER:
        await async_handle_create_number(hass, data)
    elif type == SERVENT_SELECT:
        await async_handle_create_select(hass, data)
    elif type == SERVENT_BUTTON:
        await async_handle_create_button(hass, data)

    else:
        raise Exception("Invalid Type for Entity")


async def handle_update_entity(call: ServiceCall) -> None:
    """Handle the service call."""
    servent_id = call.data["servent_id"]
    state = call.data["state"]
    attributes = call.data.get("attributes", {})

    platform = get_platform_for_servent_id(servent_id)

    if platform is not None and platform is not SERVENT_BUTTON:
        live_entity = get_live_entities_from_cache(platform, servent_id)
        live_entity.set_new_state_and_attributes(state, attributes)
        try:
            if live_entity.hass is not None:
                live_entity.verified_schedule_update_ha_state()
        except AttributeError:
            pass

    else:
        _LOGGER.warn(
            f"Tried to update a Non Registered ID {servent_id}. This can happen if you are sending an update event immediately after a creation event and the ID hasn't been registered yet"
        )


def setup(hass, config):
    """Set up is called when Home Assistant is loading our component."""
    load_config_from_file()

    async def handle_cleanup_devices(call: ServiceCall) -> None:
        """Handle the service call."""

        device_registry = dr.async_get(hass)

        device_ids = get_all_device_ids()

        devices = [
            d
            for d in device_registry.devices.values()
            if any(["servent" in a[1] for a in d.identifiers])
        ]

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    store_hass_object(hass)

    hass.bus.async_fire("servent.core_reloaded")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    servent_reset_config()

    return unload_ok
