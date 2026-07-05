from collections.abc import Mapping
from typing import Any

from homeassistant.components.siren import SirenEntity, SirenEntityFeature
from homeassistant.components.siren.const import ATTR_DURATION, ATTR_TONE, ATTR_VOLUME_LEVEL
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import SirenConfig

from .command_entity import apply_if_optimistic, apply_present_state_fields, command_payload, fire_entity_command
from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up siren platform."""
    register_platform_builder(config_entry, SirenConfig, lambda x: ServEntSiren(x), async_add_entities)


class ServEntSiren(ServEntEntity[SirenConfig], SirenEntity):
    def configure_platform(self) -> None:
        self._attr_available_tones = self.servent_config.available_tones
        features = SirenEntityFeature.TURN_ON | SirenEntityFeature.TURN_OFF
        if self.servent_config.available_tones:
            features |= SirenEntityFeature.TONES
        if self.servent_config.supports_volume_set:
            features |= SirenEntityFeature.VOLUME_SET
        if self.servent_config.supports_duration:
            features |= SirenEntityFeature.DURATION
        self._attr_supported_features = features

    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_is_on = None
            return

        if isinstance(state, Mapping):
            self._apply_siren_state(state)
            return

        self._apply_power_state(state)

    def _apply_siren_state(self, state: Mapping[str, Any]) -> None:
        apply_present_state_fields(state, {"state": self._apply_power_state})

    def _apply_power_state(self, state: Any) -> None:
        self._attr_is_on = None if state is None else bool(state)

    def _fire_siren_command(self, command: dict[str, Any]) -> None:
        apply_if_optimistic(self, command, self._apply_siren_state)
        fire_entity_command(self, "siren", command)

    async def async_turn_on(self, **kwargs: Any) -> None:
        volume_level = kwargs.get(ATTR_VOLUME_LEVEL)
        self._fire_siren_command(
            command_payload(
                state=True,
                tone=kwargs.get(ATTR_TONE) if self.servent_config.available_tones else None,
                duration=kwargs.get(ATTR_DURATION) if self.servent_config.supports_duration else None,
                volume_level=round(float(volume_level) * 100)
                if volume_level is not None and self.servent_config.supports_volume_set
                else None,
            )
        )

    async def async_turn_off(self, **_kwargs: Any) -> None:
        self._fire_siren_command({"state": False})
