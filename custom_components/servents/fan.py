from typing import Any

from homeassistant.components.fan import ATTR_PERCENTAGE, ATTR_PRESET_MODE, FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import FanConfig

from .command_entity import (
    apply_if_optimistic,
    apply_present_state_fields,
    command_payload,
    fire_entity_command,
    require_state_dict,
)
from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up fan platform."""
    register_platform_builder(config_entry, FanConfig, lambda x: ServEntFan(x), async_add_entities)


class ServEntFan(ServEntEntity[FanConfig], FanEntity):
    def configure_platform(self) -> None:
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self.servent_config.supports_percentage:
            features |= FanEntityFeature.SET_SPEED
        if self.servent_config.preset_modes:
            features |= FanEntityFeature.PRESET_MODE
        self._attr_supported_features = features
        self._attr_preset_modes = self.servent_config.preset_modes

    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_percentage = None
            self._attr_preset_mode = None
            return

        self._apply_fan_state(require_state_dict(state, "fan"))

    def _apply_fan_state(self, state: dict[str, Any]) -> None:
        apply_present_state_fields(
            state,
            {
                "state": self._apply_power_state,
                "percentage": self._apply_percentage,
                "preset_mode": self._apply_preset_mode,
            },
        )

    def _apply_power_state(self, state: Any) -> None:
        if state:
            if (self._attr_percentage is None or self._attr_percentage <= 0) and self._attr_preset_mode is None:
                self._attr_percentage = 100
        else:
            self._attr_percentage = 0
            self._attr_preset_mode = None

    def _apply_percentage(self, percentage: Any) -> None:
        self._attr_percentage = None if percentage is None else int(percentage)

    def _apply_preset_mode(self, preset_mode: Any) -> None:
        self._attr_preset_mode = None if preset_mode is None else str(preset_mode)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **_kwargs: Any,
    ) -> None:
        command = command_payload(state=True, percentage=percentage, preset_mode=preset_mode)
        apply_if_optimistic(self, command, self._apply_fan_state)
        fire_entity_command(self, "fan", command)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        command = {"state": False}
        apply_if_optimistic(self, command, self._apply_fan_state)
        fire_entity_command(self, "fan", command)

    async def async_set_percentage(self, percentage: int) -> None:
        command = {ATTR_PERCENTAGE: percentage}
        apply_if_optimistic(self, command, self._apply_fan_state)
        fire_entity_command(self, "fan", command)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        command = {ATTR_PRESET_MODE: preset_mode}
        apply_if_optimistic(self, command, self._apply_fan_state)
        fire_entity_command(self, "fan", command)
