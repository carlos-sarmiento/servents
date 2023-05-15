import logging

from homeassistant.const import EntityCategory

from .const import (
    SERVENT_ENTITY_CATEGORY,
    SERVENT_ENTITY_DEFAULT_STATE,
    SERVENT_ID,
    SERVENT_NAME,
    SERVENT_ENTITY_DISABLED_BY_DEFAULT,
)
from .utilities import (
    create_device_info,
    toEnum,
)

_LOGGER = logging.getLogger(__name__)


class ServEntEntityAttributes:
    def servent_configure(self, config, device_config):
        # entity attributes
        # Fixed Values
        self._attr_should_poll = False
        self._attr_has_entity_name = True

        # sensor fixed values
        # When we create a sensor, we never set an initial value. Value should be set by calling the right service
        self._update_servent_entity_config(config, device_config)
        self._attr_unique_id = f"sensor-{self.servent_config[SERVENT_ID]}"
        self.servent_id = self.servent_config[SERVENT_ID]
        self.set_new_state_and_attributes(
            self.servent_config.get(SERVENT_ENTITY_DEFAULT_STATE, None),
            {"servent_id": self.servent_id},
        )
        self._attr_entity_registry_enabled_default = (
            not self.servent_config.get(SERVENT_ENTITY_DISABLED_BY_DEFAULT, False),
        )

    def _update_servent_entity_config(self, config, device_config):
        self.servent_config = config
        self.servent_device_config = device_config

        # Absolutely Required Attributes
        self._attr_name = self.servent_config[SERVENT_NAME]
        self._attr_device_info = create_device_info(self.servent_device_config)
        self._attr_entity_category = toEnum(
            EntityCategory, self.servent_config.get(SERVENT_ENTITY_CATEGORY, None)
        )

        self.update_specific_entity_config()

    def update_specific_entity_config(self):
        pass

    def set_new_state_and_attributes(self, state, attributes):
        pass


class ServEntEntity(ServEntEntityAttributes):
    def verified_schedule_update_ha_state(self):
        if self.hass is not None:
            self.schedule_update_ha_state()

    async def restore_attributes(self):
        if (
            last_extra_attributes := await self.async_get_last_extra_data()
        ) is not None:
            self._attr_extra_state_attributes = last_extra_attributes.as_dict() | {
                "servent_id": self.servent_id
            }


class ServEntHelperMixin(ServEntEntityAttributes):
    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def extra_state_attributes(self):
        extra_attributes = super().extra_state_attributes or {}
        return extra_attributes | {"servent_id": self.servent_id}
