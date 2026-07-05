from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_SWING_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import ClimateConfig

from .command_entity import (
    apply_if_optimistic,
    apply_present_state_fields,
    command_payload,
    fire_entity_command,
)
from .entity import ServEntEntity, register_platform_builder


DEFAULT_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT]


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate platform."""
    register_platform_builder(config_entry, ClimateConfig, lambda x: ServEntClimate(x), async_add_entities)


class ServEntClimate(ServEntEntity[ClimateConfig], ClimateEntity):
    def configure_platform(self) -> None:
        self._attr_hvac_modes = [
            HVACMode(mode) for mode in (self.servent_config.hvac_modes or DEFAULT_HVAC_MODES)
        ]
        self._attr_temperature_unit = (
            UnitOfTemperature.FAHRENHEIT
            if self.servent_config.temperature_unit == "F"
            else UnitOfTemperature.CELSIUS
        )
        self._attr_fan_modes = self.servent_config.fan_modes
        self._attr_preset_modes = self.servent_config.preset_modes
        self._attr_swing_modes = self.servent_config.swing_modes
        self._attr_target_temperature_step = (
            None if self.servent_config.temp_step is None else float(self.servent_config.temp_step)
        )

        self._set_optional_attr("_attr_min_temp", self.servent_config.min_temp)
        self._set_optional_attr("_attr_max_temp", self.servent_config.max_temp)
        self._ensure_state_attrs()

        features = ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if self.servent_config.supports_target_temperature:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self.servent_config.supports_target_temperature_range:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.servent_config.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if self.servent_config.preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        if self.servent_config.swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = features

    def _set_optional_attr(self, attr_name: str, value: float | int | None) -> None:
        if value is None:
            if hasattr(self, attr_name):
                delattr(self, attr_name)
            return
        setattr(self, attr_name, float(value))

    def _ensure_state_attrs(self) -> None:
        for attr_name in (
            "_attr_current_humidity",
            "_attr_current_temperature",
            "_attr_fan_mode",
            "_attr_hvac_action",
            "_attr_hvac_mode",
            "_attr_preset_mode",
            "_attr_swing_mode",
            "_attr_target_temperature",
            "_attr_target_temperature_high",
            "_attr_target_temperature_low",
        ):
            if not hasattr(self, attr_name):
                setattr(self, attr_name, None)

    def _write_native_state(self, state) -> None:
        if state is None:
            self._apply_climate_state(
                {
                    "hvac_mode": None,
                    "target_temperature": None,
                    "target_temp_low": None,
                    "target_temp_high": None,
                    "current_temperature": None,
                    "current_humidity": None,
                    "fan_mode": None,
                    "preset_mode": None,
                    "swing_mode": None,
                    "hvac_action": None,
                }
            )
            return

        if isinstance(state, Mapping):
            self._apply_climate_state(state)
            return

        self._apply_hvac_mode(state)

    def _apply_climate_state(self, state: Mapping[str, Any]) -> None:
        apply_present_state_fields(
            state,
            {
                "hvac_mode": self._apply_hvac_mode,
                "target_temperature": self._apply_target_temperature,
                "target_temp_low": self._apply_target_temp_low,
                "target_temp_high": self._apply_target_temp_high,
                "current_temperature": self._apply_current_temperature,
                "current_humidity": self._apply_current_humidity,
                "fan_mode": self._apply_fan_mode,
                "preset_mode": self._apply_preset_mode,
                "swing_mode": self._apply_swing_mode,
                "hvac_action": self._apply_hvac_action,
            },
        )

    def _apply_hvac_mode(self, hvac_mode: Any) -> None:
        self._attr_hvac_mode = None if hvac_mode is None else HVACMode(hvac_mode)

    def _apply_target_temperature(self, temperature: Any) -> None:
        self._attr_target_temperature = None if temperature is None else float(temperature)

    def _apply_target_temp_low(self, temperature: Any) -> None:
        self._attr_target_temperature_low = None if temperature is None else float(temperature)

    def _apply_target_temp_high(self, temperature: Any) -> None:
        self._attr_target_temperature_high = None if temperature is None else float(temperature)

    def _apply_current_temperature(self, temperature: Any) -> None:
        self._attr_current_temperature = None if temperature is None else float(temperature)

    def _apply_current_humidity(self, humidity: Any) -> None:
        self._attr_current_humidity = None if humidity is None else float(humidity)

    def _apply_fan_mode(self, fan_mode: Any) -> None:
        self._attr_fan_mode = None if fan_mode is None else str(fan_mode)

    def _apply_preset_mode(self, preset_mode: Any) -> None:
        self._attr_preset_mode = None if preset_mode is None else str(preset_mode)

    def _apply_swing_mode(self, swing_mode: Any) -> None:
        self._attr_swing_mode = None if swing_mode is None else str(swing_mode)

    def _apply_hvac_action(self, hvac_action: Any) -> None:
        self._attr_hvac_action = None if hvac_action is None else HVACAction(hvac_action)

    def _fire_climate_command(self, command: Mapping[str, Any]) -> None:
        apply_if_optimistic(self, command, self._apply_climate_state)
        fire_entity_command(self, "climate", command)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._fire_climate_command({"hvac_mode": hvac_mode.value})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        command = command_payload(
            target_temperature=kwargs.get(ATTR_TEMPERATURE),
            target_temp_low=kwargs.get(ATTR_TARGET_TEMP_LOW),
            target_temp_high=kwargs.get(ATTR_TARGET_TEMP_HIGH),
            hvac_mode=kwargs.get(ATTR_HVAC_MODE),
        )
        if isinstance(command.get("hvac_mode"), HVACMode):
            command["hvac_mode"] = command["hvac_mode"].value
        self._fire_climate_command(command)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._fire_climate_command({ATTR_FAN_MODE: fan_mode})

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._fire_climate_command({ATTR_PRESET_MODE: preset_mode})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        self._fire_climate_command({ATTR_SWING_MODE: swing_mode})

    async def async_turn_on(self) -> None:
        self._fire_climate_command({"hvac_mode": self._turn_on_hvac_mode().value})

    async def async_turn_off(self) -> None:
        self._fire_climate_command({"hvac_mode": HVACMode.OFF.value})

    def _turn_on_hvac_mode(self) -> HVACMode:
        if len(self._attr_hvac_modes) == 2 and HVACMode.OFF in self._attr_hvac_modes:
            return next(mode for mode in self._attr_hvac_modes if mode != HVACMode.OFF)

        for mode in (HVACMode.HEAT_COOL, HVACMode.HEAT, HVACMode.COOL):
            if mode in self._attr_hvac_modes:
                return mode

        return next(mode for mode in self._attr_hvac_modes if mode != HVACMode.OFF)
