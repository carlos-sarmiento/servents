import logging

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from datetime import datetime
import pytz

from .entity import ServEntEntity

from .const import (
    SERVENT_DEVICE,
    SERVENT_DEVICE_CLASS,
    SERVENT_ENTITY,
    SERVENT_ENUM_OPTIONS,
    SERVENT_ID,
    SERVENT_SENSOR,
    SERVENT_STATE_CLASS,
    SERVENT_UNIT_OF_MEASUREMENT,
    SERVENTS_CONFIG_SENSORS,
)
from .utilities import (
    add_entity_to_cache,
    get_ent_config,
    get_live_entities_from_cache,
    save_config_to_file,
    toEnum,
)

SERVENTS_ENTS_NEW_SENSOR = "servents_ents_new_sensor"

_LOGGER = logging.getLogger(__name__)


async def async_handle_create_sensor(hass, data):
    ents = get_ent_config(SERVENTS_CONFIG_SENSORS)

    servent_id = data.get(SERVENT_ENTITY)[SERVENT_ID]

    ent = {
        SERVENT_ENTITY: data.get(SERVENT_ENTITY),
        SERVENT_DEVICE: data.get(SERVENT_DEVICE),
    }
    ents[servent_id] = ent

    save_config_to_file()

    async_dispatcher_send(hass, SERVENTS_ENTS_NEW_SENSOR)


async def _async_setup_entity(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    ents = get_ent_config(SERVENTS_CONFIG_SENSORS)

    for servent_id, ent_config in ents.items():
        if get_live_entities_from_cache(SERVENT_SENSOR, servent_id) is None:
            entity = ServEntSensor(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            add_entity_to_cache(SERVENT_SENSOR, servent_id, entity)
            async_add_entities([entity])

        else:
            live_entity = get_live_entities_from_cache(SERVENT_SENSOR, servent_id)
            live_entity._update_servent_entity_config(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            live_entity.verified_schedule_update_ha_state()


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up sensor platform."""

    async def async_discover():
        await _async_setup_entity(hass, config_entry, async_add_entities)

    async_dispatcher_connect(
        hass,
        SERVENTS_ENTS_NEW_SENSOR,
        async_discover,
    )

    await _async_setup_entity(hass, config_entry, async_add_entities)


class ServEntSensor(ServEntEntity, RestoreSensor):
    def __init__(self, config, device_config):
        self.servent_configure(config, device_config)

    def update_specific_entity_config(self):
        # Sensor Attributes
        self._attr_device_class = toEnum(
            SensorDeviceClass, self.servent_config.get(SERVENT_DEVICE_CLASS, None)
        )

        self._attr_native_unit_of_measurement = self.servent_config.get(
            SERVENT_UNIT_OF_MEASUREMENT, None
        )

        self._attr_state_class = self.servent_config.get(SERVENT_STATE_CLASS, None)
        self._attr_options = self.servent_config.get(SERVENT_ENUM_OPTIONS, None)

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
