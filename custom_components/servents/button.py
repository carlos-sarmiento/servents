import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from .entity import ServEntEntity

from .const import (
    SERVENT_BUTTON,
    SERVENT_BUTTON_EVENT,
    SERVENT_BUTTON_EVENT_DATA,
    SERVENT_DEVICE,
    SERVENT_DEVICE_CLASS,
    SERVENT_ENTITY,
    SERVENT_ID,
    SERVENTS_CONFIG_BUTTONS,
)
from .utilities import (
    add_entity_to_cache,
    get_ent_config,
    get_live_entities_from_cache,
    save_config_to_file,
    toEnum,
)

SERVENTS_ENTS_NEW_BUTTON = "servents_ents_new_button"

_LOGGER = logging.getLogger(__name__)


async def async_handle_create_button(hass, data):
    ents = get_ent_config(SERVENTS_CONFIG_BUTTONS)

    servent_id = data.get(SERVENT_ENTITY)[SERVENT_ID]

    ent = {
        SERVENT_ENTITY: data.get(SERVENT_ENTITY),
        SERVENT_DEVICE: data.get(SERVENT_DEVICE),
    }
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
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE], hass
            )
            add_entity_to_cache(SERVENT_BUTTON, servent_id, entity)
            async_add_entities([entity])

        else:
            live_entity = get_live_entities_from_cache(SERVENT_BUTTON, servent_id)
            live_entity._update_servent_entity_config(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            live_entity.verified_schedule_update_ha_state()


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


class ServEntButton(ServEntEntity, ButtonEntity, RestoreEntity):
    def __init__(self, config, device_config, hass):
        self.servent_configure(config, device_config)
        self._hass = hass

    def update_specific_entity_config(self):
        # Button Attributes
        self.servent_event = self.servent_config[SERVENT_BUTTON_EVENT]
        self.event_data = self.servent_config.get(SERVENT_BUTTON_EVENT_DATA, {})
        self._attr_device_class = toEnum(
            ButtonDeviceClass, self.servent_config.get(SERVENT_DEVICE_CLASS, None)
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        self._hass.bus.async_fire(f"servent.{self.servent_event}", self.event_data)

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await self.restore_attributes()

    async def restore_attributes(self):
        if (
            last_extra_attributes := await self.async_get_last_extra_data()
        ) is not None:
            self._attr_extra_state_attributes = last_extra_attributes.as_dict() | {
                "servent_id": self.servent_id
            }

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def extra_state_attributes(self):
        extra_attributes = super().extra_state_attributes or {}
        return extra_attributes | {"servent_id": self.servent_id}
