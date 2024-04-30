from datetime import datetime

import pytz
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .data_carriers import ServentSensorDefinition
from .entity import ServEntEntity
from .registrar import get_registrar


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    get_registrar().register_builder_for_definition(
        ServentSensorDefinition, lambda x: ServEntSensor(x), async_add_entities
    )


class ServEntSensor(ServEntEntity[ServentSensorDefinition], RestoreSensor):
    def __init__(self, config: ServentSensorDefinition):
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # Sensor Attributes
        self._attr_device_class = (
            SensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

        self._attr_native_unit_of_measurement = self.servent_config.unit_of_measurement
        self._attr_state_class = self.servent_config.state_class
        self._attr_options = self.servent_config.enum_options

    def set_new_state_and_attributes(self, state, attributes):
        if state is not None and self._attr_device_class in [SensorDeviceClass.DATE, SensorDeviceClass.TIMESTAMP]:
            state = datetime.fromtimestamp(int(state), pytz.utc)

        self._attr_native_value = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_sensor_data.native_value

        await self.restore_attributes()
