from collections.abc import Mapping
from typing import Any

from homeassistant.components.valve import ATTR_POSITION, ValveDeviceClass, ValveEntityFeature, ValveState
try:
    from homeassistant.components.valve.entity import ValveEntity
except ModuleNotFoundError:
    from homeassistant.components.valve import ValveEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import ValveConfig

from .command_entity import apply_if_optimistic, fire_entity_command
from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up valve platform."""
    register_platform_builder(config_entry, ValveConfig, lambda x: ServEntValve(x), async_add_entities)


class ServEntValve(ServEntEntity[ValveConfig], ValveEntity):
    def configure_platform(self) -> None:
        self._attr_device_class = (
            ValveDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        )
        self._attr_reports_position = self.servent_config.supports_position
        features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        if self.servent_config.supports_position:
            features |= ValveEntityFeature.SET_POSITION
        if self.servent_config.supports_stop:
            features |= ValveEntityFeature.STOP
        self._attr_supported_features = features

    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_is_closed = None
            self._attr_is_opening = None
            self._attr_is_closing = None
            self._attr_current_valve_position = None
            return

        if isinstance(state, Mapping):
            self._apply_valve_state(state)
            return

        self._apply_valve_state_name(state)

    def _apply_valve_state(self, state: Mapping[str, Any]) -> None:
        if "position" in state:
            self._apply_valve_position(state["position"])
        if "state" in state:
            self._apply_valve_state_name(state["state"], set_position="position" not in state)

    def _apply_valve_state_name(self, state: Any, *, set_position: bool = True) -> None:
        valve_state = ValveState(state)
        self._attr_is_opening = valve_state == ValveState.OPENING
        self._attr_is_closing = valve_state == ValveState.CLOSING
        self._attr_is_closed = valve_state == ValveState.CLOSED
        if set_position and self._attr_reports_position:
            if valve_state == ValveState.CLOSED:
                self._attr_current_valve_position = 0
            elif valve_state == ValveState.OPEN:
                self._attr_current_valve_position = 100

    def _apply_valve_position(self, position: Any) -> None:
        if position is None:
            self._attr_current_valve_position = None
            return

        current_position = int(position)
        self._attr_current_valve_position = current_position
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = current_position <= 0

    def _apply_valve_command(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        if action == "open":
            self._apply_valve_state_name(ValveState.OPENING)
        elif action == "close":
            self._apply_valve_state_name(ValveState.CLOSING)
        elif action == "stop":
            self._attr_is_opening = False
            self._attr_is_closing = False

        if "position" in command:
            self._apply_valve_position(command["position"])

    def _fire_valve_command(self, command: dict[str, Any]) -> None:
        apply_if_optimistic(self, command, self._apply_valve_command)
        fire_entity_command(self, "valve", command)

    async def async_handle_open_valve(self) -> None:
        await self.async_open_valve()

    async def async_handle_close_valve(self) -> None:
        await self.async_close_valve()

    async def async_open_valve(self) -> None:
        self._fire_valve_command({"action": "open"})

    async def async_close_valve(self) -> None:
        self._fire_valve_command({"action": "close"})

    async def async_set_valve_position(self, position: int) -> None:
        self._fire_valve_command({ATTR_POSITION: int(position)})

    async def async_stop_valve(self) -> None:
        self._fire_valve_command({"action": "stop"})
