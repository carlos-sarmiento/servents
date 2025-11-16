from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypeVar

from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .deserialization import EntityConfig
from .entity import ServEntEntity

T = TypeVar("T", bound=EntityConfig)


@dataclass
class ServentDefinitionRegistrar:
    entity_definitions: dict[str, EntityConfig] = field(default_factory=dict)
    live_entities: dict[str, ServEntEntity] = field(default_factory=dict)
    entity_builders: dict[str, Callable[[EntityConfig], ServEntEntity]] = field(default_factory=dict)
    is_hass_up: bool = False

    def set_hass_up(self, state: bool):
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
        type_name = str(definition_type)

        def full_implementation(definition: T) -> ServEntEntity:
            entity = builder(definition)
            self.register_live_entity(definition.servent_id, entity)
            async_add_entities([entity])
            return entity

        self.entity_builders[type_name] = full_implementation  # type: ignore

    def build_and_register_entity(self, definition: EntityConfig) -> ServEntEntity:
        type_name = str(type(definition))
        if type_name not in self.entity_builders:
            raise Exception(f"There is no builder registered for type {type_name}")

        return self.entity_builders[type_name](definition)


servent_current_config: ServentDefinitionRegistrar = ServentDefinitionRegistrar()


def get_registrar() -> ServentDefinitionRegistrar:
    return servent_current_config


def reset_registrar() -> None:
    global servent_current_config
    servent_current_config = ServentDefinitionRegistrar()
    servent_current_config.is_hass_up = True
