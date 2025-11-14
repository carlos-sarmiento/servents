from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .data_carriers import SwitchConfig
from .entity import ServEntEntity
from .registrar import get_registrar


async def async_setup_entry(
    _hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    get_registrar().register_builder_for_definition(SwitchConfig, lambda x: ServEntSwitch(x), async_add_entities)


class ServEntSwitch(ServEntEntity[SwitchConfig], SwitchEntity, RestoreEntity):
    def __init__(self, config: SwitchConfig):
        self.servent_configure(config)

    def update_specific_entity_config(self):
        # Switch Attributes
        self._attr_device_class = (
            SwitchDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    def turn_on(self, **_kwargs):
        self._attr_is_on = True
        self.verified_schedule_update_ha_state()

    def turn_off(self, **_kwargs):
        self._attr_is_on = False
        self.verified_schedule_update_ha_state()

    def set_new_state_and_attributes(self, state, attributes):
        self._attr_is_on = state
        if attributes is None:
            attributes = {}
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == "on"
        await self.restore_attributes()
