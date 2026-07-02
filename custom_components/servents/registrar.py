from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, TypeVar

from homeassistant.helpers.entity_platform import AddEntitiesCallback
from servents.data_model.entity_configs import EntityConfig

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .entity import ServEntEntity

T = TypeVar("T", bound=EntityConfig)


@dataclass
class ServentDefinitionRegistrar:
    """Per-config-entry registry of definitions, live entities, and builders.

    State lives on ``entry.runtime_data`` (see ``async_setup_entry``); there is
    no process-global instance. ``is_hass_up`` tracks the last observed
    ``EVENT_HOMEASSISTANT_STARTED/STOP`` transition and backs the
    ``servent/hass-state`` websocket command.
    """

    entity_definitions: dict[str, EntityConfig] = field(default_factory=dict)
    live_entities: dict[str, ServEntEntity] = field(default_factory=dict)
    entity_builders: dict[type[EntityConfig], Callable[[EntityConfig], ServEntEntity]] = field(default_factory=dict)
    is_hass_up: bool = False
    # Unsubscribe callbacks for the STARTED/STOP listeners, released on unload.
    unsub_hass_state_listeners: list[Callable[[], None]] = field(default_factory=list)

    def release_hass_state_listeners(self) -> None:
        while self.unsub_hass_state_listeners:
            self.unsub_hass_state_listeners.pop()()

    def set_hass_up(self, state: bool) -> None:
        self.is_hass_up = state

    def register_definition(self, entity: EntityConfig) -> None:
        if entity.servent_id in self.entity_definitions:
            new_type = type(entity)
            old_type = type(self.entity_definitions[entity.servent_id])

            if not isinstance(entity, old_type):
                raise Exception(
                    f"Cannot change the type of entity with servent_id {entity.servent_id} from {old_type} to {new_type}"
                )

        self.entity_definitions[entity.servent_id] = entity

    def get_entities_of_type(self, entity_type: type[T]) -> list[T]:
        return [x for x in self.entity_definitions.values() if isinstance(x, entity_type)]

    def get_all_entities(self) -> list[EntityConfig]:
        return [x for x in self.entity_definitions.values()]

    def get_live_entity_for_servent_id(self, servent_id: str) -> ServEntEntity | None:
        return self.live_entities[servent_id] if servent_id in self.live_entities else None

    def register_live_entity(self, servent_id: str, entity: ServEntEntity) -> None:
        self.live_entities[servent_id] = entity

    def register_builder_for_definition(
        self,
        definition_type: type[T],
        builder: Callable[[T], ServEntEntity],
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        def full_implementation(definition: T) -> ServEntEntity:
            entity = builder(definition)
            self.register_live_entity(definition.servent_id, entity)
            async_add_entities([entity])
            return entity

        # Dispatch keys on the exact type object; register_definition accepts a
        # definition only when its exact type already has a builder (see
        # build_and_register_entity), so registration and dispatch agree.
        self.entity_builders[definition_type] = full_implementation  # type: ignore

    def build_and_register_entity(self, definition: EntityConfig) -> ServEntEntity:
        definition_type = type(definition)
        if definition_type not in self.entity_builders:
            raise Exception(f"There is no builder registered for type {definition_type}")

        return self.entity_builders[definition_type](definition)


def get_registrar_from_hass(hass: HomeAssistant) -> ServentDefinitionRegistrar:
    """Resolve the registrar for the (single) ServEnts config entry.

    The domain-global service handlers and the websocket command only receive
    ``hass``; they reach the registrar hung on the config entry's
    ``runtime_data``. ServEnts is a single-entry integration, so the first
    entry's registrar is the one.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        registrar = getattr(entry, "runtime_data", None)
        if isinstance(registrar, ServentDefinitionRegistrar):
            return registrar

    raise Exception("No ServEnts config entry with an initialized registrar was found")


def get_registrar_for_entry(entry: ConfigEntry) -> ServentDefinitionRegistrar:
    """Registrar for a specific config entry (used by platform setup)."""
    registrar = getattr(entry, "runtime_data", None)
    if not isinstance(registrar, ServentDefinitionRegistrar):
        raise Exception(f"Config entry {entry.entry_id} has no initialized registrar")
    return registrar
