import logging
from typing import Any, Generic, TypeVar

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .data_carriers import BaseServentEntityDefinition, ServentDeviceDefinition

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseServentEntityDefinition)


class ServEntEntityAttributes(Generic[T], Entity):
    servent_config: T
    servent_id: str
    fixed_attributes: dict[str, Any]

    def servent_configure(self, config: T) -> None:
        # entity attributes
        # Fixed Values
        self._attr_should_poll = False
        self._attr_has_entity_name = True

        # sensor fixed values
        # When we create a sensor, we never set an initial value. Value should be set by calling the right service
        self.servent_config = config
        self._attr_unique_id = f"sensor-{self.servent_config.servent_id}"
        self.servent_id = self.servent_config.servent_id
        self._update_servent_entity_config(config)
        self.set_new_state_and_attributes(
            self.servent_config.default_state,
            self.fixed_attributes,
        )
        self._unrecorded_attributes = frozenset(["servent_config", *self.fixed_attributes.keys()])
        self._attr_entity_registry_enabled_default = not self.servent_config.disabled_by_default

    def _update_servent_entity_config(self, config: T) -> None:
        self.servent_config = config

        # Absolutely Required Attributes
        self._attr_name = self.servent_config.name
        self._attr_device_info = None
        self._attr_entity_category = (
            EntityCategory(self.servent_config.entity_category) if self.servent_config.entity_category else None
        )
        self.fixed_attributes = self.servent_config.fixed_attributes | {"servent_id": self.servent_id}

        self.update_specific_entity_config()

    def update_specific_entity_config(self) -> None:
        pass

    def set_new_state_and_attributes(self, state, attributes) -> None:
        pass

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""
        if isinstance(self.servent_config.device_definition, dict):
            self.servent_config.device_definition = ServentDeviceDefinition.from_dict(
                self.servent_config.device_definition
            )

        return (
            self.servent_config.device_definition.get_device_info() if self.servent_config.device_definition else None
        )


class ServentExtraData(ExtraStoredData):
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        super().__init__()

    def as_dict(self) -> dict[str, Any]:
        return self.data


class ServEntEntity(ServEntEntityAttributes[T], RestoreEntity):
    def verified_schedule_update_ha_state(self) -> None:
        if self.hass is not None:
            self.schedule_update_ha_state()

    async def restore_attributes(self) -> None:
        state = await self.async_get_last_state()
        attributes = state.attributes if state else {}
        self._attr_extra_state_attributes = self._attr_extra_state_attributes | self.fixed_attributes | attributes
