from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.servents.registrar import get_registrar
from custom_components.servents.sensor.grouped_sensor import ServEntSensorGroup
from custom_components.servents.sensor.sensor import ServEntSensor
from servents.data_model.entity_configs import SensorConfig


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""

    def builder(config: SensorConfig) -> ServEntSensor | ServEntSensorGroup:
        if config.entity_ids is not None and len(config.entity_ids) > 1:
            return ServEntSensorGroup(config)
        return ServEntSensor(config)

    get_registrar().register_builder_for_definition(SensorConfig, builder, async_add_entities)
