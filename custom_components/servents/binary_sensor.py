from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.threshold.binary_sensor import ThresholdSensor, _threshold_type
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
from .entity import ServEntEntity, register_platform_builder
from .registrar import ServentDefinitionRegistrar, get_registrar_for_entry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    registrar = get_registrar_for_entry(config_entry)

    configure_homeassistant_up_sensor(hass, registrar, async_add_entities)

    register_platform_builder(config_entry, BinarySensorConfig, lambda x: ServEntBinarySensor(x), async_add_entities)
    register_platform_builder(
        config_entry, ThresholdBinarySensorConfig, lambda x: ServEntThresholdBinarySensor(hass, x), async_add_entities
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
    def configure_platform(self):
        # BinarySensor Attributes
        self._attr_device_class = (
            BinarySensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    def _write_native_state(self, state):
        self._attr_is_on = state

    async def _restore_native_state(self) -> None:
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == "off":
                self._attr_is_on = False
            elif last_state.state == "on":
                self._attr_is_on = True


class ServEntThresholdBinarySensor(ServEntEntity[ThresholdBinarySensorConfig], ThresholdSensor):
    def __init__(self, hass: HomeAssistant, config: ThresholdBinarySensorConfig):
        # ThresholdSensor.__init__ is keyword-only and seeds the source entity,
        # bounds, hysteresis and threshold_type. name/unique_id are placeholders
        # here — the ServEnt lifecycle overrides them via __init__/apply_config.
        ThresholdSensor.__init__(
            self,
            hass=hass,
            entity_id=config.entity_id,
            lower=config.lower,
            upper=config.upper,
            hysteresis=config.hysteresis,
            name="WillBeOverriden",
            device_class=None,
            unique_id="WillBeOverriden",
        )
        ServEntEntity.__init__(self, config)

    def configure_platform(self):
        # BinarySensor Attributes
        self._attr_device_class = (
            BinarySensorDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )
        # H6: apply_config runs on every reconfigure, so re-apply the bounds and
        # source entity here (they are otherwise consumed once by __init__ and
        # never refreshed). When already added to hass, re-run the source-entity
        # tracking so the new bounds take effect.
        self._apply_threshold_bounds()

    def _apply_threshold_bounds(self) -> None:
        config = self.servent_config

        self._entity_id = config.entity_id
        self.source_entity_id = config.entity_id
        self._hysteresis = config.hysteresis

        # ThresholdSensor only sets _threshold_lower/_upper when not None and
        # reads them via getattr(..., None); mirror that so clearing a bound on
        # reconfigure actually drops it.
        if config.lower is not None:
            self._threshold_lower = config.lower
        elif hasattr(self, "_threshold_lower"):
            del self._threshold_lower

        if config.upper is not None:
            self._threshold_upper = config.upper
        elif hasattr(self, "_threshold_upper"):
            del self._threshold_upper

        self.threshold_type = _threshold_type(config.lower, config.upper)

        if self.hass is not None:
            # Reconfigure while live: drop the old source-entity tracker (and any
            # other on-remove callbacks) and re-run setup so the new source and
            # bounds are tracked and the state is recomputed.
            self._call_on_remove_callbacks()
            self._async_setup_sensor()

    async def async_added_to_hass(self) -> None:
        # A threshold sensor computes its own state from the source entity, so
        # it uses ThresholdSensor's setup (start tracking the source) rather than
        # the ServEnt restore flow. restore_attributes is a no-op here.
        await ThresholdSensor.async_added_to_hass(self)

    @property
    def extra_state_attributes(self):
        # L8: include fixed_attributes (which already carries servent_id), the
        # ThresholdSensor internals, and source_entity_id — falls out of the base
        # owning fixed_attributes on self._attr_extra_state_attributes.
        threshold_attributes: dict = super().extra_state_attributes or {}  # type: ignore
        return threshold_attributes | self.fixed_attributes | {"source_entity_id": self.source_entity_id}

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return the sensor class of the sensor."""
        return self._attr_device_class

    async def restore_attributes(self):
        ...
