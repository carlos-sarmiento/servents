import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.threshold.binary_sensor import ThresholdSensor

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from .entity import ServEntEntity, ServEntEntityAttributes, ServEntHelperMixin

from .const import (
    SERVENT_DEVICE,
    SERVENT_DEVICE_CLASS,
    SERVENT_ENTITY,
    SERVENT_ID,
    SERVENT_THRESHOLD_BINARY_SENSOR,
    SERVENTS_CONFIG_BINARY_SENSORS,
)
from .utilities import (
    add_entity_to_cache,
    get_ent_config,
    get_live_entities_from_cache,
    save_config_to_file,
    toEnum,
)

SERVENTS_ENTS_NEW_BINARY_SENSOR = "servents_ents_new_binary_sensor"

_LOGGER = logging.getLogger(__name__)


async def async_handle_create_binary_sensor(hass, data):
    ents = get_ent_config(SERVENTS_CONFIG_BINARY_SENSORS)

    servent_id = data.get(SERVENT_ENTITY)[SERVENT_ID]

    ent = {
        SERVENT_ENTITY: data.get(SERVENT_ENTITY),
        SERVENT_DEVICE: data.get(SERVENT_DEVICE),
    }
    ents[servent_id] = ent

    save_config_to_file()

    async_dispatcher_send(hass, SERVENTS_ENTS_NEW_BINARY_SENSOR)


async def _async_setup_entity(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    ents = get_ent_config(SERVENTS_CONFIG_BINARY_SENSORS)

    for servent_id, ent_config in ents.items():
        type = ent_config[SERVENT_ENTITY].get("type", None)
        if get_live_entities_from_cache(type, servent_id) is None:
            if type == SERVENT_THRESHOLD_BINARY_SENSOR:
                entity = ServEntThresholdBinarySensor(
                    hass, ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
                )
            else:
                entity = ServEntBinarySensor(
                    ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
                )

            add_entity_to_cache(type, servent_id, entity)
            async_add_entities([entity])

        else:
            live_entity = get_live_entities_from_cache(type, servent_id)
            live_entity._update_servent_entity_config(
                ent_config[SERVENT_ENTITY], ent_config[SERVENT_DEVICE]
            )
            try:
                live_entity.verified_schedule_update_ha_state()
            except AttributeError:
                pass


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up binary_sensor platform."""

    async def async_discover():
        await _async_setup_entity(hass, config_entry, async_add_entities)

    async_dispatcher_connect(
        hass,
        SERVENTS_ENTS_NEW_BINARY_SENSOR,
        async_discover,
    )

    await _async_setup_entity(hass, config_entry, async_add_entities)


class ServEntBinarySensor(ServEntEntity, BinarySensorEntity, RestoreEntity):
    def __init__(self, config, device_config):
        self.servent_configure(config, device_config)

    def update_specific_entity_config(self):
        # BinarySensor Attributes
        self._attr_device_class = toEnum(
            BinarySensorDeviceClass, self.servent_config.get(SERVENT_DEVICE_CLASS, None)
        )

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_is_on = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == "off":
                self._attr_is_on = False
            elif last_state.state == "on":
                self._attr_is_on = True
        await self.restore_attributes()


class ServEntThresholdBinarySensor(ServEntHelperMixin, ThresholdSensor):
    def __init__(self, hass, config, device_config):
        super().__init__(
            hass=hass,
            entity_id=config["entity_id"],
            lower=config.get("lower"),
            upper=config.get("upper"),
            hysteresis=config.get("hysteresis", 0),
            name="WillBeOverriden",
            device_class=None,
            unique_id="WillBeOverriden",
        )
        self.source_entity_id = config["entity_id"]
        self.servent_configure(config, device_config)

    def update_specific_entity_config(self):
        # BinarySensor Attributes
        self._attr_device_class = toEnum(
            BinarySensorDeviceClass, self.servent_config.get(SERVENT_DEVICE_CLASS, None)
        )

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the sensor class of the sensor."""
        return self._attr_device_class

    @property
    def extra_state_attributes(self):
        extra_attributes = super().extra_state_attributes or {}
        return extra_attributes | {
            "servent_id": self.servent_id,
            "source_entity_id": self.source_entity_id,
        }
