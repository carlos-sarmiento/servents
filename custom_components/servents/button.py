from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from servents.data_model.entity_configs import ButtonConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    register_platform_builder(config_entry, ButtonConfig, lambda x: ServEntButton(x, hass), async_add_entities)


class ServEntButton(ServEntEntity[ButtonConfig], ButtonEntity, RestoreEntity):
    def __init__(self, config: ButtonConfig, hass: HomeAssistant):
        super().__init__(config)
        self._hass = hass

    def configure_platform(self):
        # Button Attributes
        self.servent_event = self.servent_config.event
        self.event_data = self.servent_config.event_data
        self._attr_device_class = (
            ButtonDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        self._hass.bus.async_fire(f"servent.{self.servent_event}", self.event_data)

    # A button has no native value, so _write_native_state stays the base no-op.
    # update_state on a button therefore applies the merged attributes (incl.
    # servent_id) via the base set_new_state_and_attributes and never raises
    # (M2 / constraint 3).

    async def restore_attributes(self):
        if (last_extra_attributes := await self.async_get_last_extra_data()) is not None:
            self._attr_extra_state_attributes = (
                last_extra_attributes.as_dict() | self.fixed_attributes | {"servent_id": self.servent_id}
            )
