from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.threshold.binary_sensor import ThresholdSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .data_carriers import (
    ServentBinarySensorDefinition,
    ServentDeviceDefinition,
    ServentThresholdBinarySensorDefinition,
)
from .entity import ServEntEntity
from .registrar import get_registrar


async def async_setup_entry(
    hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    configure_homeassistant_up_sensor(hass, async_add_entities)

    get_registrar().register_builder_for_definition(
        ServentBinarySensorDefinition, lambda x: ServEntBinarySensor(x), async_add_entities
    )
    get_registrar().register_builder_for_definition(
        ServentThresholdBinarySensorDefinition, lambda x: ServEntThresholdBinarySensor(x, hass), async_add_entities
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

        self._attr_device_info = ServentDeviceDefinition(
            device_id="servent_core_device",
            name="Servents Core",
            manufacturer="Servents",
        ).get_device_info()
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def set_state(self, state: bool):
        self._attr_is_on = state
        get_registrar().set_hass_up(state)
        self.schedule_update_ha_state()


class ServEntBinarySensor(ServEntEntity[ServentBinarySensorDefinition], BinarySensorEntity, RestoreEntity):
    def __init__(self, config: ServentBinarySensorDefinition):
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


class ServEntThresholdBinarySensor(ServEntEntity[ServentThresholdBinarySensorDefinition], ThresholdSensor):
    def __init__(self, config: ServentThresholdBinarySensorDefinition, hass: HomeAssistant):
        super().__init__(
            hass=hass,
            entity_id=config.entity_id,
            lower=config.lower,
            upper=config.upper,
            hysteresis=config.hysteresis,
            name="WillBeOverriden",
            device_class=None,
            unique_id="WillBeOverriden",
        )
        self.source_entity_id = config.entity_id
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # BinarySensor Attributes
        self._attr_device_class = (
            BinarySensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._attr_name  # type: ignore

    @property
    def extra_state_attributes(self):
        extra_attributes: dict = super().extra_state_attributes or {}  # type: ignore
        return extra_attributes | {
            "servent_id": self.servent_id,
            "source_entity_id": self.source_entity_id,
        }

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the sensor class of the sensor."""
        return self._attr_device_class

    async def restore_attributes(self):
        ...
