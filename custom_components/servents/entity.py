import logging
from typing import Any, Generic, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from servents.data_model.entity_configs import EntityConfig

from .definitions import get_device_info
from .registrar import get_registrar_for_entry

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=EntityConfig)


def register_platform_builder(
    config_entry: ConfigEntry,
    definition_type: type[T],
    factory,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register a platform's entity builder with the entry's registrar.

    Every platform's ``async_setup_entry`` is a single call to this helper. The
    ``factory`` builds an entity from a definition; the registrar wraps it with
    the "register live entity + async_add_entities" step (S4/S5).
    """
    get_registrar_for_entry(config_entry).register_builder_for_definition(
        definition_type, factory, async_add_entities
    )


class ServentExtraData(ExtraStoredData):
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        super().__init__()

    def as_dict(self) -> dict[str, Any]:
        return self.data


class ServEntEntity(Generic[T], RestoreEntity):
    """Base class for every ServEnt entity.

    Lifecycle is two steps:

    - ``__init__(config)`` runs once. Subclasses call ``super().__init__(config)``
      from their own ``__init__``. It sets the frozen entity flags and IDs, then
      delegates the mutable, re-appliable configuration to ``apply_config``.
    - ``apply_config(config)`` runs on initial setup AND on every reconfigure
      (``services.register_and_update_all_entities`` calls it when Domovoy
      re-creates an existing ``servent_id``). It replaces the definition, name,
      entity category, and ``fixed_attributes``, then calls the per-platform
      ``configure_platform`` hook.

    The base owns the attribute merge (``set_new_state_and_attributes``) and the
    attribute-restore flow (``restore_attributes``); each platform implements a
    single ``_write_native_state`` hook to write its native value, and (if it
    restores one) a ``_restore_native_state`` hook.
    """

    servent_config: T
    servent_id: str
    fixed_attributes: dict[str, Any]

    def __init__(self, config: T) -> None:
        # Fixed entity flags — a ServEnt never polls and always uses entity name.
        self._attr_should_poll = False
        self._attr_has_entity_name = True

        # The unique_id prefix is literally "sensor-" for every platform (M3).
        # It is frozen wire format: changing it orphans every existing registry
        # entry. Do NOT change this.
        self.servent_id = config.servent_id
        self._attr_unique_id = f"sensor-{self.servent_id}"

        self.apply_config(config)

        # Initial state: no native value is written by an app until it calls
        # update_state, but the fixed attributes (incl. servent_id) are always
        # published from creation.
        self.set_new_state_and_attributes(config.default_state, self.fixed_attributes)

        self._unrecorded_attributes = frozenset(["servent_config", *self.fixed_attributes.keys()])
        self._attr_entity_registry_enabled_default = not config.disabled_by_default

    def apply_config(self, config: T) -> None:
        """(Re)apply the mutable configuration. Runs on setup and reconfigure."""
        self.servent_config = config

        self._attr_name = config.name
        self._attr_entity_category = EntityCategory(config.entity_category) if config.entity_category else None
        self.fixed_attributes = config.fixed_attributes | {"servent_id": self.servent_id}

        self.configure_platform()

    def configure_platform(self) -> None:
        """Per-platform config hook (device_class, units, bounds, ...)."""

    def set_new_state_and_attributes(self, state, attributes) -> None:
        """Write native state + republish the merged extra attributes.

        The base owns the ``fixed_attributes | attributes | {"servent_id": ...}``
        merge so ``servent_id`` is always present and can never be overridden
        (constraint 1). Platforms only implement ``_write_native_state``.
        """
        if attributes is None:
            attributes = {}
        self._write_native_state(state)
        self._attr_extra_state_attributes = self.fixed_attributes | attributes | {"servent_id": self.servent_id}

    def _write_native_state(self, state) -> None:
        """Write the platform's native value (``_attr_native_value`` etc.).

        Base no-op: a button has no native value. Platforms with a native value
        override this.
        """

    async def _restore_native_state(self) -> None:
        """Restore the platform's native value from the last state. Optional."""

    async def async_added_to_hass(self) -> None:
        """Restore native value (platform-specific) then attributes (shared)."""
        await self._restore_native_state()
        await self.restore_attributes()

    async def restore_attributes(self) -> None:
        state = await self.async_get_last_state()
        attributes = state.attributes if state else {}
        self._attr_extra_state_attributes = self._attr_extra_state_attributes | self.fixed_attributes | attributes

    def verified_schedule_update_ha_state(self) -> None:
        if self.hass is not None:
            self.schedule_update_ha_state()

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device info."""
        if self.servent_config.device_definition is None:
            return None

        return get_device_info(self.servent_config.device_definition)
