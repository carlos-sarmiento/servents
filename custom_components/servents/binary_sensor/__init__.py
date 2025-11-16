from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.servents.binary_sensor.threshold_binary_sensor import ServEntThresholdBinarySensor
from custom_components.servents.deserialization import get_hass_device_info
from custom_components.servents.entity import ServEntEntity
from custom_components.servents.registrar import get_registrar
from servents.data_model.entity_configs import BinarySensorConfig, DeviceConfig, ThresholdBinarySensorConfig


async def async_setup_entry(
    hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    configure_homeassistant_up_sensor(hass, async_add_entities)

    get_registrar().register_builder_for_definition(
        BinarySensorConfig, lambda x: ServEntBinarySensor(x), async_add_entities
    )
    get_registrar().register_builder_for_definition(
        ThresholdBinarySensorConfig, lambda x: ServEntThresholdBinarySensor(hass, x), async_add_entities
    )


def configure_homeassistant_up_sensor(
    hass: HomeAssistant,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # Create Binary Sensor for HASS IS UP
    uptime_entity = ServEntHassIsReady()
    async_add_entities([uptime_entity], True)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _x: uptime_entity.set_state(True))
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _x: uptime_entity.set_state(False))


class ServEntHassIsReady(BinarySensorEntity):
    def __init__(self):
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        self._attr_unique_id = "servent-hass-is-up"
        self._attr_name = "Home Assistant is Ready"
        self._attr_is_on = False
        self._attr_extra_state_attributes = {"servent_flag": "servent-hass-is-up"}

        self._attr_device_info = get_hass_device_info(
            DeviceConfig(
                device_id="servent_core_device",
                name="Servents Core",
                manufacturer="Servents",
            )
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def set_state(self, state: bool):
        self._attr_is_on = state
        get_registrar().set_hass_up(state)
        self.schedule_update_ha_state()


class ServEntBinarySensor(ServEntEntity[BinarySensorConfig], BinarySensorEntity, RestoreEntity):
    def __init__(self, config: BinarySensorConfig):
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # BinarySensor Attributes
        self._attr_device_class = (
            BinarySensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_is_on = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == "off":
                self._attr_is_on = False
            elif last_state.state == "on":
                self._attr_is_on = True
        await self.restore_attributes()
