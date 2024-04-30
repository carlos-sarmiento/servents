from homeassistant.components.number import NumberDeviceClass, RestoreNumber
from homeassistant.components.number.const import NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.servents.data_carriers import ServentNumberDefinition
from custom_components.servents.registrar import get_registrar

from .entity import ServEntEntity


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    get_registrar().register_builder_for_definition(
        ServentNumberDefinition, lambda x: ServEntNumber(x), async_add_entities
    )


class ServEntNumber(ServEntEntity[ServentNumberDefinition], RestoreNumber):
    def __init__(self, config: ServentNumberDefinition):
        self.servent_configure(config)

    def set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.verified_schedule_update_ha_state()

    def update_specific_entity_config(self):
        # Number Attributes
        self._attr_device_class = (
            NumberDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

        self._attr_native_unit_of_measurement = self.servent_config.unit_of_measurement

        if self.servent_config.mode:
            self._attr_mode = NumberMode(self.servent_config.mode)

        if self.servent_config.max_value:
            self._attr_native_max_value = self.servent_config.max_value

        if self.servent_config.min_value:
            self._attr_native_min_value = self.servent_config.min_value

        if self.servent_config.step:
            self._attr_native_step = self.servent_config.step

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_native_value = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""

        if (last_number_data := await self.async_get_last_number_data()) is not None:
            self._attr_native_value = last_number_data.native_value

        await self.restore_attributes()
