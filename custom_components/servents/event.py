from typing import Any

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from servents.data_model.entity_configs import EventConfig

from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up event platform."""
    register_platform_builder(config_entry, EventConfig, lambda x: ServEntEventEntity(x), async_add_entities)


class ServEntEventEntity(ServEntEntity[EventConfig], EventEntity):
    def configure_platform(self) -> None:
        self._attr_event_types = self.servent_config.event_types
        self._attr_device_class = (
            EventDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )

    def _write_native_state(self, _state) -> None:
        """Event entities are updated through trigger_event, not update_state."""

    async def async_internal_added_to_hass(self) -> None:
        if self._servent_restore_state:
            await EventEntity.async_internal_added_to_hass(self)
        else:
            await RestoreEntity.async_internal_added_to_hass(self)

    async def async_trigger_event(self, event_type: str, attributes: dict[str, Any] | None = None) -> None:
        if attributes is None:
            attributes = {}

        try:
            self._trigger_event(event_type, attributes | {"event_type": event_type})
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        self.verified_schedule_update_ha_state()
