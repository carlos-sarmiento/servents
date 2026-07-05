from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import DatetimeConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up datetime platform."""
    register_platform_builder(config_entry, DatetimeConfig, lambda x: ServEntDatetimeEntity(x), async_add_entities)


class ServEntDatetimeEntity(ServEntEntity[DatetimeConfig], DateTimeEntity):
    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_native_value = None
            return

        value = state if isinstance(state, datetime) else datetime.fromisoformat(str(state))
        if value.tzinfo is None:
            raise ValueError("datetime state must include timezone information")
        self._attr_native_value = value

    async def async_set_value(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("datetime value must include timezone information")
        self.hass.bus.async_fire(
            "servent.datetime_changed",
            {"servent_id": self.servent_id, "value": value.isoformat()},
        )
        self.set_new_state_and_attributes(value, self._current_dynamic_attributes())
        self.verified_schedule_update_ha_state()
