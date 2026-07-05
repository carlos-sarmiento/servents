from collections.abc import Mapping
from typing import Any

from homeassistant.components.lock import ATTR_CODE, LockEntity, LockEntityFeature
from homeassistant.components.lock.const import LockState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from servents.data_model.entity_configs import LockConfig

from .command_entity import apply_if_optimistic, apply_present_state_fields, command_payload, fire_entity_command
from .entity import ServEntEntity, register_platform_builder


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up lock platform."""
    register_platform_builder(config_entry, LockConfig, lambda x: ServEntLock(x), async_add_entities)


class ServEntLock(ServEntEntity[LockConfig], LockEntity):
    def configure_platform(self) -> None:
        self._attr_code_format = self.servent_config.code_format
        self._attr_supported_features = (
            LockEntityFeature.OPEN if self.servent_config.supports_open else LockEntityFeature(0)
        )

    def _write_native_state(self, state) -> None:
        if state is None:
            self._clear_lock_state()
            return

        if isinstance(state, Mapping):
            self._apply_lock_state(state)
            return

        self._apply_lock_state_name(state)

    def _clear_lock_state(self) -> None:
        self._attr_is_jammed = None
        self._attr_is_locked = None
        self._attr_is_locking = None
        self._attr_is_open = None
        self._attr_is_opening = None
        self._attr_is_unlocking = None

    def _reset_lock_flags(self) -> None:
        self._attr_is_jammed = False
        self._attr_is_locked = False
        self._attr_is_locking = False
        self._attr_is_open = False
        self._attr_is_opening = False
        self._attr_is_unlocking = False

    def _apply_lock_state(self, state: Mapping[str, Any]) -> None:
        apply_present_state_fields(state, {"state": self._apply_lock_state_name})

    def _apply_lock_state_name(self, state: Any) -> None:
        lock_state = LockState(state)
        self._reset_lock_flags()
        if lock_state == LockState.LOCKED:
            self._attr_is_locked = True
        elif lock_state == LockState.LOCKING:
            self._attr_is_locking = True
        elif lock_state == LockState.UNLOCKING:
            self._attr_is_unlocking = True
        elif lock_state == LockState.UNLOCKED:
            self._attr_is_locked = False
        elif lock_state == LockState.JAMMED:
            self._attr_is_jammed = True
        elif lock_state == LockState.OPENING:
            self._attr_is_opening = True
        elif lock_state == LockState.OPEN:
            self._attr_is_open = True

    def _apply_lock_command(self, command: dict[str, Any]) -> None:
        action = command.get("action")
        if action == "lock":
            self._apply_lock_state_name(LockState.LOCKING)
        elif action == "unlock":
            self._apply_lock_state_name(LockState.UNLOCKING)
        elif action == "open":
            self._apply_lock_state_name(LockState.OPENING)

    def _fire_lock_command(self, command: dict[str, Any]) -> None:
        apply_if_optimistic(self, command, self._apply_lock_command)
        fire_entity_command(self, "lock", command)

    async def async_lock(self, **kwargs: Any) -> None:
        self._fire_lock_command(command_payload(action="lock", code=kwargs.get(ATTR_CODE)))

    async def async_unlock(self, **kwargs: Any) -> None:
        self._fire_lock_command(command_payload(action="unlock", code=kwargs.get(ATTR_CODE)))

    async def async_open(self, **kwargs: Any) -> None:
        self._fire_lock_command(command_payload(action="open", code=kwargs.get(ATTR_CODE)))
