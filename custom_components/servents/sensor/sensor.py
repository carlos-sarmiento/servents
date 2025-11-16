from datetime import datetime

import pytz
from homeassistant.components.sensor import RestoreSensor
from homeassistant.components.sensor.const import SensorDeviceClass

from custom_components.servents.entity import ServEntEntity
from servents.data_model.entity_configs import SensorConfig


class ServEntSensor(ServEntEntity[SensorConfig], RestoreSensor):
    def __init__(self, config: SensorConfig):
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # Sensor Attributes
        self._attr_device_class = (
            SensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

        self._attr_native_unit_of_measurement = self.servent_config.unit_of_measurement
        self._attr_state_class = self.servent_config.state_class
        self._attr_options = list(self.servent_config.options) if self.servent_config.options else None

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
