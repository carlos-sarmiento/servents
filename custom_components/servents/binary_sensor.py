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

from servents.data_model.entity_configs import (
    BinarySensorConfig,
    DeviceConfig,
    ThresholdBinarySensorConfig,
)

from .definitions import get_device_info
from .entity import ServEntEntity
from .registrar import ServentDefinitionRegistrar, get_registrar_for_entry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    registrar = get_registrar_for_entry(config_entry)

    configure_homeassistant_up_sensor(hass, registrar, async_add_entities)

    registrar.register_builder_for_definition(
        BinarySensorConfig, lambda x: ServEntBinarySensor(x), async_add_entities
    )
    registrar.register_builder_for_definition(
        ThresholdBinarySensorConfig, lambda x: ServEntThresholdBinarySensor(hass, x), async_add_entities
    )


def configure_homeassistant_up_sensor(
    hass: HomeAssistant,
    registrar: ServentDefinitionRegistrar,
    async_add_entities: AddEntitiesCallback,
) -> None:
    # The hass-up sensor and the STARTED/STOP listeners are created once per
    # config-entry lifecycle. The single sensor instance is stored on the
    # registrar so the listeners drive the same object HA tracks (M11), and the
    # one handler keeps the visible sensor and the registrar's is_hass_up flag
    # (read by the servent/hass-state websocket) in sync (M7).
    uptime_entity = ServEntHassIsReady()

    # Seed both effects from the real core state: on a reload after HA is
    # already running, EVENT_HOMEASSISTANT_STARTED will not fire again, so the
    # value must be derived rather than defaulted (M6).
    uptime_entity.set_is_on(hass.is_running)
    registrar.set_hass_up(hass.is_running)

    async_add_entities([uptime_entity], True)

    def set_state(state: bool) -> None:
        uptime_entity.set_is_on(state)
        registrar.set_hass_up(state)
        uptime_entity.schedule_update_ha_state()

    # STARTED and STOP each fire at most once per HA lifetime, so listen_once is
    # correct. Unsubscribe handles are held on the registrar and released on
    # unload so a reload does not leak the previous setup's listeners (M7/L9).
    registrar.unsub_hass_state_listeners.append(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _x: set_state(True))
    )
    registrar.unsub_hass_state_listeners.append(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _x: set_state(False))
    )


class ServEntHassIsReady(BinarySensorEntity):
    def __init__(self):
        self._attr_should_poll = False
        self._attr_has_entity_name = True
        self._attr_unique_id = "servent-hass-is-up"
        self._attr_name = "Home Assistant is Ready"
        self._attr_is_on = False
        self._attr_extra_state_attributes = {"servent_flag": "servent-hass-is-up"}

        self._attr_device_info = get_device_info(
            DeviceConfig(
                device_id="servent_core_device",
                name="Servents Core",
                manufacturer="Servents",
            )
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def set_is_on(self, state: bool) -> None:
        self._attr_is_on = state


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


class ServEntThresholdBinarySensor(ServEntEntity[ThresholdBinarySensorConfig], ThresholdSensor):
    def __init__(self, hass: HomeAssistant, config: ThresholdBinarySensorConfig):
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
