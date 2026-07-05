from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import TimeConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up time platform."""
    register_platform_builder(config_entry, TimeConfig, lambda x: ServEntTimeEntity(x), async_add_entities)


class ServEntTimeEntity(ServEntEntity[TimeConfig], TimeEntity):
    def _write_native_state(self, state) -> None:
        if state is None or isinstance(state, time):
            self._attr_native_value = state
            return

        self._attr_native_value = time.fromisoformat(str(state))

    async def async_set_value(self, value: time) -> None:
        self.hass.bus.async_fire(
            "servent.time_changed",
            {"servent_id": self.servent_id, "value": value.isoformat()},
        )
        self.set_new_state_and_attributes(value, self._current_dynamic_attributes())
        self.verified_schedule_update_ha_state()
