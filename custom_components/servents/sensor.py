from datetime import datetime, timezone

from homeassistant.components.sensor import RestoreSensor
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import SensorConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    register_platform_builder(config_entry, SensorConfig, lambda x: ServEntSensor(x), async_add_entities)


class ServEntSensor(ServEntEntity[SensorConfig], RestoreSensor):
    def configure_platform(self):
        # Sensor Attributes
        self._attr_device_class = (
            SensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

        self._attr_native_unit_of_measurement = self.servent_config.unit_of_measurement
        self._attr_state_class = self.servent_config.state_class
        self._attr_options = self.servent_config.options

    def _write_native_state(self, state):
        if state is not None and self._attr_device_class in [SensorDeviceClass.DATE, SensorDeviceClass.TIMESTAMP]:
            state = datetime.fromtimestamp(int(state), timezone.utc)

        self._attr_native_value = state

    async def _restore_native_state(self) -> None:
        if (last_sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_sensor_data.native_value
