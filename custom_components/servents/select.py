import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    SERVENT_DEVICE,
    SERVENT_ENTITY,
    SERVENT_ENTITY_CATEGORY,
    SERVENT_ENTITY_DEFAULT_STATE,
    SERVENT_ENUM_OPTIONS,
    SERVENT_ID,
    SERVENT_NAME,
    SERVENT_SELECT,
    SERVENTS_CONFIG_SELECTS,
)
from .utilities import (
    add_entity_to_cache,
    create_device_info,
    get_ent_config,
    get_live_entities_from_cache,
    save_config_to_file,
    toEnum,
)

SERVENTS_ENTS_NEW_SELECT = "servents_ents_new_select"

_LOGGER = logging.getLogger(__name__)


async def async_handle_create_select(hass, data):
    ents = get_ent_config(SERVENTS_CONFIG_SELECTS)

    servent_id = data.get(SERVENT_ENTITY)[SERVENT_ID]

    ent = {
        SERVENT_ENTITY: data.get(SERVENT_ENTITY),
        SERVENT_DEVICE: data.get(SERVENT_DEVICE),
    }
    ents[servent_id] = ent

    save_config_to_file()

    async_dispatcher_send(hass, SERVENTS_ENTS_NEW_SELECT)


async def _async_setup_entity(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    ents = get_ent_config(SERVENTS_CONFIG_SELECTS)

    for servent_id, ent_config in ents.items():
        if get_live_entities_from_cache(SERVENT_SELECT, servent_id) is None:
            entity = ServEntSelect(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            add_entity_to_cache(SERVENT_SELECT, servent_id, entity)
            async_add_entities([entity])

        else:
            live_entity = get_live_entities_from_cache(SERVENT_SELECT, servent_id)
            live_entity._update_servent_entity_config(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            live_entity.schedule_update_ha_state()


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up select platform."""

    async def async_discover():
        await _async_setup_entity(hass, config_entry, async_add_entities)

    async_dispatcher_connect(
        hass,
        SERVENTS_ENTS_NEW_SELECT,
        async_discover,
    )

    await _async_setup_entity(hass, config_entry, async_add_entities)


class ServEntSelect(SelectEntity, RestoreEntity):
    def __init__(self, config, device_config):
        # entity attributes
        # Fixed Values
        self._attr_should_poll = False
        self._attr_has_entity_name = True

        # select fixed values
        # When we create a select, we never set an initial value. Value should be set by calling the right service
        self._update_servent_entity_config(config, device_config)
        self._attr_unique_id = f"select-{self.servent_config[SERVENT_ID]}"
        self._attr_current_option = self.servent_config.get(
            SERVENT_ENTITY_DEFAULT_STATE, None
        )
        self.servent_id = self.servent_config[SERVENT_ID]
        self._attr_extra_state_attributes = {"servent_id": self.servent_id}

    def _update_servent_entity_config(self, config, device_config):
        self.servent_config = config
        self.servent_device_config = device_config

        # Absolutely Required Attributes
        self._attr_name = self.servent_config[SERVENT_NAME]

        self._attr_device_info = create_device_info(self.servent_device_config)

        self._attr_entity_category = toEnum(
            EntityCategory, self.servent_config.get(SERVENT_ENTITY_CATEGORY, None)
        )

        # Select Attributes
        self._attr_options = self.servent_config.get(SERVENT_ENUM_OPTIONS, [])

    def select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.schedule_update_ha_state()

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_current_option = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state

        if (
            last_extra_attributes := await self.async_get_last_extra_data()
        ) is not None:
            self._attr_extra_state_attributes = last_extra_attributes.as_dict() | {
                "servent_id": self.servent_id
            }
