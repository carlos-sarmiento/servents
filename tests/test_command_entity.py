from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from custom_components.servents.command_entity import (
    SERVENT_ENTITY_COMMAND_EVENT,
    apply_if_optimistic,
    apply_present_state_fields,
    command_payload,
    fire_entity_command,
    require_state_dict,
)


@dataclass
class FakeConfig:
    optimistic: bool


class FakeCommandEntity:
    def __init__(self, *, optimistic: bool) -> None:
        self.hass = MagicMock()
        self.servent_id = "light-1"
        self.servent_config = FakeConfig(optimistic=optimistic)
        self.schedule_count = 0

    def verified_schedule_update_ha_state(self) -> None:
        self.schedule_count += 1


def test_command_payload_keeps_falsy_values_and_omits_none():
    assert command_payload(state=False, brightness=0, preset_mode="", missing=None) == {
        "state": False,
        "brightness": 0,
        "preset_mode": "",
    }


def test_fire_entity_command_uses_shared_event_contract():
    entity = FakeCommandEntity(optimistic=False)
    command = {"state": True, "brightness": 128}

    fire_entity_command(entity, "light", command)

    entity.hass.bus.async_fire.assert_called_once_with(
        SERVENT_ENTITY_COMMAND_EVENT,
        {
            "servent_id": "light-1",
            "entity_type": "light",
            "command": {"state": True, "brightness": 128},
        },
    )


def test_fire_entity_command_copies_command_payload():
    entity = FakeCommandEntity(optimistic=False)
    command = {"state": True}

    fire_entity_command(entity, "light", command)
    command["state"] = False

    fired_payload = entity.hass.bus.async_fire.call_args.args[1]
    assert fired_payload["command"] == {"state": True}


def test_apply_if_optimistic_skips_non_optimistic_entity():
    entity = FakeCommandEntity(optimistic=False)
    applied: list[dict] = []

    did_apply = apply_if_optimistic(entity, {"state": True}, applied.append)

    assert did_apply is False
    assert applied == []
    assert entity.schedule_count == 0


def test_apply_if_optimistic_applies_and_schedules_update():
    entity = FakeCommandEntity(optimistic=True)
    applied: list[dict] = []

    did_apply = apply_if_optimistic(entity, {"state": True}, applied.append)

    assert did_apply is True
    assert applied == [{"state": True}]
    assert entity.schedule_count == 1


def test_apply_if_optimistic_can_skip_update_scheduling():
    entity = FakeCommandEntity(optimistic=True)

    did_apply = apply_if_optimistic(entity, {"state": True}, lambda _command: None, schedule_update=False)

    assert did_apply is True
    assert entity.schedule_count == 0


def test_apply_if_optimistic_copies_command_payload():
    entity = FakeCommandEntity(optimistic=True)
    command = {"state": True}
    applied: list[dict] = []

    apply_if_optimistic(entity, command, applied.append)
    command["state"] = False

    assert applied == [{"state": True}]


def test_require_state_dict_accepts_mapping_payload():
    assert require_state_dict({"state": True}, "light") == {"state": True}


@pytest.mark.parametrize("state", [None, True, "open", ["state", "open"]])
def test_require_state_dict_rejects_non_mapping_payloads(state):
    with pytest.raises(ValueError, match="light state must be a dict"):
        require_state_dict(state, "light")


def test_apply_present_state_fields_only_calls_handlers_for_present_keys():
    applied: dict[str, object] = {}

    did_apply = apply_present_state_fields(
        {"state": None, "brightness": 0, "ignored": "value"},
        {
            "state": lambda value: applied.__setitem__("state", value),
            "brightness": lambda value: applied.__setitem__("brightness", value),
            "preset_mode": lambda value: applied.__setitem__("preset_mode", value),
        },
    )

    assert did_apply is True
    assert applied == {"state": None, "brightness": 0}


def test_apply_present_state_fields_reports_when_nothing_matched():
    did_apply = apply_present_state_fields({"ignored": "value"}, {"state": lambda _value: None})

    assert did_apply is False
