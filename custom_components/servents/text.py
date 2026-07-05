from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import TextConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text platform."""
    register_platform_builder(config_entry, TextConfig, lambda x: ServEntTextEntity(x), async_add_entities)


class ServEntTextEntity(ServEntEntity[TextConfig], TextEntity):
    def configure_platform(self) -> None:
        self._attr_mode = TextMode(self.servent_config.mode)
        self._attr_pattern = self.servent_config.pattern

        if self.servent_config.min_length is None:
            if hasattr(self, "_attr_native_min"):
                del self._attr_native_min
        else:
            self._attr_native_min = self.servent_config.min_length

        if self.servent_config.max_length is None:
            if hasattr(self, "_attr_native_max"):
                del self._attr_native_max
        else:
            self._attr_native_max = self.servent_config.max_length

    def _write_native_state(self, state) -> None:
        self._attr_native_value = None if state is None else str(state)

    async def async_set_value(self, value: str) -> None:
        self.hass.bus.async_fire(
            "servent.text_changed",
            {"servent_id": self.servent_id, "value": value},
        )
        self.set_new_state_and_attributes(value, self._current_dynamic_attributes())
        self.verified_schedule_update_ha_state()
