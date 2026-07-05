from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import DateConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up date platform."""
    register_platform_builder(config_entry, DateConfig, lambda x: ServEntDateEntity(x), async_add_entities)


class ServEntDateEntity(ServEntEntity[DateConfig], DateEntity):
    def _write_native_state(self, state) -> None:
        if state is None or isinstance(state, date):
            self._attr_native_value = state
            return

        self._attr_native_value = date.fromisoformat(str(state))

    async def async_set_value(self, value: date) -> None:
        self.hass.bus.async_fire(
            "servent.date_changed",
            {"servent_id": self.servent_id, "value": value.isoformat()},
        )
        self.set_new_state_and_attributes(value, self._current_dynamic_attributes())
        self.verified_schedule_update_ha_state()
