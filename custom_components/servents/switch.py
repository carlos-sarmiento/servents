from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from servents.data_model.entity_configs import SwitchConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    register_platform_builder(config_entry, SwitchConfig, lambda x: ServEntSwitch(x), async_add_entities)


class ServEntSwitch(ServEntEntity[SwitchConfig], SwitchEntity, RestoreEntity):
    def configure_platform(self):
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

    def _write_native_state(self, state):
        self._attr_is_on = state

    async def _restore_native_state(self) -> None:
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_is_on = last_state.state == "on"
