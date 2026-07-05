from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity, LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import LightConfig

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
    """Set up light platform."""
    register_platform_builder(config_entry, LightConfig, lambda x: ServEntLight(x), async_add_entities)


class ServEntLight(ServEntEntity[LightConfig], LightEntity):
    def configure_platform(self) -> None:
        self._attr_supported_features = LightEntityFeature(0)
        self._attr_supported_color_modes = {
            ColorMode.BRIGHTNESS if self.servent_config.supports_brightness else ColorMode.ONOFF
        }

    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_is_on = None
            self._attr_color_mode = None
            self._attr_brightness = None
            return

        self._apply_light_state(require_state_dict(state, "light"))

    def _apply_light_state(self, state: dict[str, Any]) -> None:
        apply_present_state_fields(
            state,
            {
                "state": self._apply_power_state,
                "brightness": self._apply_brightness,
            },
        )
        self._sync_color_mode()

    def _apply_power_state(self, state: Any) -> None:
        self._attr_is_on = None if state is None else bool(state)

    def _apply_brightness(self, brightness: Any) -> None:
        self._attr_brightness = None if brightness is None else int(brightness)

    def _sync_color_mode(self) -> None:
        if self._attr_is_on:
            self._attr_color_mode = (
                ColorMode.BRIGHTNESS if self.servent_config.supports_brightness else ColorMode.ONOFF
            )
        else:
            self._attr_color_mode = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        command = command_payload(
            state=True,
            brightness=kwargs.get(ATTR_BRIGHTNESS) if self.servent_config.supports_brightness else None,
        )
        apply_if_optimistic(self, command, self._apply_light_state)
        fire_entity_command(self, "light", command)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        command = {"state": False}
        apply_if_optimistic(self, command, self._apply_light_state)
        fire_entity_command(self, "light", command)
