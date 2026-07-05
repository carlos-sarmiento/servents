"""Shared helpers for command-driven ServEnt entities."""

from collections.abc import Callable, Mapping
from typing import Any, Protocol


SERVENT_ENTITY_COMMAND_EVENT = "servent.entity_command"


class CommandEntity(Protocol):
    """Protocol for the ServEnt entity surface command helpers need."""

    hass: Any
    servent_id: str
    servent_config: Any

    def verified_schedule_update_ha_state(self) -> None: ...


CommandApplier = Callable[[dict[str, Any]], None]
FieldApplier = Callable[[Any], None]


def command_payload(**fields: Any) -> dict[str, Any]:
    """Build a command payload, keeping falsy values and omitting only None."""
    return {key: value for key, value in fields.items() if value is not None}


def fire_entity_command(
    entity: CommandEntity,
    entity_type: str,
    command: Mapping[str, Any],
) -> None:
    """Fire the shared Domovoy command event for a native HA service call."""
    entity.hass.bus.async_fire(
        SERVENT_ENTITY_COMMAND_EVENT,
        {
            "servent_id": entity.servent_id,
            "entity_type": entity_type,
            "command": dict(command),
        },
    )


def apply_if_optimistic(
    entity: CommandEntity,
    command: Mapping[str, Any],
    apply_command: CommandApplier,
    *,
    schedule_update: bool = True,
) -> bool:
    """Apply command-derived state when the entity config is optimistic."""
    if not bool(getattr(entity.servent_config, "optimistic", False)):
        return False

    apply_command(dict(command))
    if schedule_update:
        entity.verified_schedule_update_ha_state()
    return True


def require_state_dict(state: Any, entity_type: str) -> dict[str, Any]:
    """Return a dict state payload or reject invalid controllable state."""
    if not isinstance(state, Mapping):
        raise ValueError(f"{entity_type} state must be a dict")
    return dict(state)


def apply_present_state_fields(
    state: Mapping[str, Any],
    field_appliers: Mapping[str, FieldApplier],
) -> bool:
    """Apply handlers only for keys present in a partial state dict."""
    did_apply = False
    for key, apply_field in field_appliers.items():
        if key in state:
            apply_field(state[key])
            did_apply = True
    return did_apply
