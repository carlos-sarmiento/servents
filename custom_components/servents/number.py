from homeassistant.components.number import NumberDeviceClass, RestoreNumber
from homeassistant.components.number.const import NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import NumberConfig

from .entity import ServEntEntity, register_platform_builder


def _set_optional_float_attr(entity: object, attr_name: str, value: float | None) -> None:
    if value is None:
        if hasattr(entity, attr_name):
            delattr(entity, attr_name)
        return

    setattr(entity, attr_name, value)


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    register_platform_builder(config_entry, NumberConfig, lambda x: ServEntNumber(x), async_add_entities)


class ServEntNumber(ServEntEntity[NumberConfig], RestoreNumber):
    def set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.verified_schedule_update_ha_state()

    def configure_platform(self):
        # Number Attributes
        self._attr_device_class = (
            NumberDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

        self._attr_native_unit_of_measurement = self.servent_config.unit_of_measurement

        if self.servent_config.mode:
            self._attr_mode = NumberMode(self.servent_config.mode)

        _set_optional_float_attr(self, "_attr_native_max_value", self.servent_config.max_value)
        _set_optional_float_attr(self, "_attr_native_min_value", self.servent_config.min_value)
        self._attr_native_step = self.servent_config.step

    def _write_native_state(self, state):
        self._attr_native_value = state

    async def _restore_native_state(self) -> None:
        if (last_number_data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last_number_data.native_value
