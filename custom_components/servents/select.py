from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from servents.data_model.entity_configs import SelectConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    register_platform_builder(config_entry, SelectConfig, lambda x: ServEntSelect(x), async_add_entities)


class ServEntSelect(ServEntEntity[SelectConfig], SelectEntity, RestoreEntity):
    def configure_platform(self) -> None:
        # Select Attributes
        self._attr_options = self.servent_config.options

    @property
    def options(self) -> list[str]:
        return self._attr_options

    def select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.verified_schedule_update_ha_state()

    def _write_native_state(self, state) -> None:
        self._attr_current_option = state

    async def _restore_native_state(self) -> None:
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_current_option = last_state.state
