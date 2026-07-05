from typing import Any

from homeassistant.components.cover import ATTR_POSITION, CoverDeviceClass, CoverEntity, CoverEntityFeature, CoverState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import CoverConfig

from .command_entity import apply_if_optimistic, apply_present_state_fields, fire_entity_command, require_state_dict
from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover platform."""
    register_platform_builder(config_entry, CoverConfig, lambda x: ServEntCover(x), async_add_entities)


class ServEntCover(ServEntEntity[CoverConfig], CoverEntity):
    def configure_platform(self) -> None:
        self._attr_device_class = CoverDeviceClass(self.servent_config.device_class) if self.servent_config.device_class else None
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if self.servent_config.supports_position:
            features |= CoverEntityFeature.SET_POSITION
        if self.servent_config.supports_stop:
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    def _write_native_state(self, state) -> None:
        if state is None:
            self._attr_is_closed = None
            self._attr_is_opening = None
            self._attr_is_closing = None
            self._attr_current_cover_position = None
            return

        self._apply_cover_state(require_state_dict(state, "cover"))

    def _apply_cover_state(self, state: dict[str, Any]) -> None:
        apply_present_state_fields(
            state,
            {
                "position": self._apply_cover_position,
                "state": self._apply_cover_state_name,
            },
        )

    def _apply_cover_state_name(self, state: Any) -> None:
        cover_state = CoverState(state)
        self._attr_is_opening = cover_state == CoverState.OPENING
        self._attr_is_closing = cover_state == CoverState.CLOSING
        self._attr_is_closed = cover_state == CoverState.CLOSED

    def _apply_cover_position(self, position: Any) -> None:
        if position is None:
            self._attr_current_cover_position = None
            return

        current_position = int(position)
        self._attr_current_cover_position = current_position
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = current_position <= 0

    def _apply_cover_command(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        if action == "open":
            self._apply_cover_state({"state": CoverState.OPENING})
        elif action == "close":
            self._apply_cover_state({"state": CoverState.CLOSING})
        elif action == "stop":
            self._attr_is_opening = False
            self._attr_is_closing = False

        if "position" in command:
            self._apply_cover_position(command["position"])

    async def async_open_cover(self, **_kwargs: Any) -> None:
        command = {"action": "open"}
        apply_if_optimistic(self, command, self._apply_cover_command)
        fire_entity_command(self, "cover", command)

    async def async_close_cover(self, **_kwargs: Any) -> None:
        command = {"action": "close"}
        apply_if_optimistic(self, command, self._apply_cover_command)
        fire_entity_command(self, "cover", command)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        command = {"position": int(kwargs[ATTR_POSITION])}
        apply_if_optimistic(self, command, self._apply_cover_command)
        fire_entity_command(self, "cover", command)

    async def async_stop_cover(self, **_kwargs: Any) -> None:
        command = {"action": "stop"}
        apply_if_optimistic(self, command, self._apply_cover_command)
        fire_entity_command(self, "cover", command)
