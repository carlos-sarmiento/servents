
from .const import (
    SERVENT_DEVICE_CLASS,
    SERVENT_ENTITY_CATEGORY,
    SERVENT_ID,
    SERVENT_NAME,
    SERVENTS_CONFIG_BUTTONS,
    SERVENT_ENTITY,
    SERVENT_DEVICE,
    SERVENT_BUTTON,
    SERVENT_BUTTON_EVENT,
    SERVENT_BUTTON_EVENT_DATA
)
import logging

from .utilities import create_device_info, get_ent_config, get_live_entities_from_cache, add_entity_to_cache, save_config_to_file, toEnum

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.const import EntityCategory

SERVENTS_ENTS_NEW_BUTTON = 'servents_ents_new_button'

_LOGGER = logging.getLogger(__name__)


async def async_handle_create_button(hass, call):
    data = call.data
    ents = get_ent_config(SERVENTS_CONFIG_BUTTONS)

    servent_id = data.get(SERVENT_ENTITY)[SERVENT_ID]

    ent = {SERVENT_ENTITY: data.get(
        SERVENT_ENTITY), SERVENT_DEVICE: data.get(SERVENT_DEVICE)}
    ents[servent_id] = ent

    save_config_to_file()

    async_dispatcher_send(hass, SERVENTS_ENTS_NEW_BUTTON)


async def _async_setup_entity(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    ents = get_ent_config(SERVENTS_CONFIG_BUTTONS)

    for servent_id, ent_config in ents.items():
        if get_live_entities_from_cache(SERVENT_BUTTON, servent_id) is None:
            entity = ServEntButton(
                hass,
                ent_config[SERVENT_ENTITY],
                ent_config[SERVENT_DEVICE])
            add_entity_to_cache(SERVENT_BUTTON, servent_id, entity)
            async_add_entities(
                [entity]
            )

        else:
            live_entity = get_live_entities_from_cache(
                SERVENT_BUTTON, servent_id)
            live_entity._update_servent_entity_config(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE])
            live_entity.schedule_update_ha_state()


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up button platform."""

    async def async_discover():
        await _async_setup_entity(hass, config_entry, async_add_entities)

    async_dispatcher_connect(
        hass,
        SERVENTS_ENTS_NEW_BUTTON,
        async_discover,
    )

    await _async_setup_entity(hass, config_entry, async_add_entities)


class ServEntButton(ButtonEntity, RestoreEntity):

    def __init__(self, hass, config, device_config):
        # entity attributes
        # Fixed Values
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        self._hass = hass

        # button fixed values
        # When we create a button, we never set an initial value. Value should be set by calling the right service
        self._update_servent_entity_config(config, device_config)
        self._attr_unique_id = f"button-{self.servent_config[SERVENT_ID]}"

    def _update_servent_entity_config(self, config, device_config):
        self.servent_config = config
        self.servent_device_config = device_config

        # Absolutely Required Attributes
        self._attr_name = self.servent_config[SERVENT_NAME]

        self._attr_device_info = create_device_info(self.servent_device_config)

        self._attr_entity_category = toEnum(EntityCategory, self.servent_config.get(
            SERVENT_ENTITY_CATEGORY, None))

        # Button Attributes
        self.servent_event = self.servent_config[SERVENT_BUTTON_EVENT]
        self.event_data = self.servent_config[SERVENT_BUTTON_EVENT_DATA]

        self._attr_device_class = toEnum(ButtonDeviceClass, self.servent_config.get(
            SERVENT_DEVICE_CLASS, None))

    async def async_press(self) -> None:
        """Handle the button press."""
        await self._hass.bus.async_fire(f"servent.{self.servent_event}", self.event_data)
