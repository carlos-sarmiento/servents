from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .deserialization import SelectConfig
from .entity import ServEntEntity
from .registrar import get_registrar


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    get_registrar().register_builder_for_definition(SelectConfig, lambda x: ServEntSelect(x), async_add_entities)


class ServEntSelect(ServEntEntity[SelectConfig], SelectEntity, RestoreEntity):
    def __init__(self, config: SelectConfig):
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # Select Attributes
        self._attr_options = list(self.servent_config.options)

    def select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.verified_schedule_update_ha_state()

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_current_option = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_current_option = last_state.state

        await self.restore_attributes()
