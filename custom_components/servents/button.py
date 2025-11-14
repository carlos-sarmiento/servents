from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from servents.data_model.entity_configs import (
    ButtonConfig,
)

from .entity import ServEntEntity
from .registrar import get_registrar


async def async_setup_entry(
    hass: HomeAssistant,
    _config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    get_registrar().register_builder_for_definition(ButtonConfig, lambda x: ServEntButton(x, hass), async_add_entities)


class ServEntButton(ServEntEntity[ButtonConfig], ButtonEntity, RestoreEntity):
    def __init__(self, config: ButtonConfig, hass: HomeAssistant):
        self.servent_configure(config)
        self._hass = hass

    def update_specific_entity_config(self):
        # Button Attributes
        self.servent_event = self.servent_config.event
        self.event_data = self.servent_config.event_data
        self._attr_device_class = (
            ButtonDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        self._hass.bus.async_fire(f"servent.{self.servent_event}", self.event_data)

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await self.restore_attributes()

    async def restore_attributes(self):
        if (last_extra_attributes := await self.async_get_last_extra_data()) is not None:
            self._attr_extra_state_attributes = (
                last_extra_attributes.as_dict() | self.fixed_attributes | {"servent_id": self.servent_id}
            )

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._attr_name  # type: ignore

    @property
    def extra_state_attributes(self):
        extra_attributes = super().extra_state_attributes or {}
        return (
            self.fixed_attributes | extra_attributes | {"servent_id": self.servent_id}  # type: ignore
        )
