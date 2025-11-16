from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.components.threshold.binary_sensor import ThresholdSensor
from homeassistant.core import HomeAssistant

from custom_components.servents.entity import ServEntEntity
from servents.data_model.entity_configs import ThresholdBinarySensorConfig


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

    async def restore_attributes(self): ...
