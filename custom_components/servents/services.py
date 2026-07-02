"""Service handlers for the ServEnts integration (HA `services.py` convention).

The three services (`create_entity`, `update_state`, `cleanup_devices`) and the
create-or-update reconciliation loop live here. Handlers reach the per-entry
registrar through ``ServiceCall.hass`` (``get_registrar_from_hass``), so none of
them needs a closure over ``hass``.

Registration and teardown are driven from ``__init__`` via ``async_register_services``
/ ``async_unregister_services`` so they pair with the config-entry lifecycle.

Error semantics (H7):
- Empty ``entities`` and any malformed / unknown-``entity_type`` payload raise
  ``ServiceValidationError`` (paths Domovoy never triggers).
- A ``servent_id`` type conflict on ``register_definition`` stays NON-FATAL: it
  is caught and logged as a structured warning; the call still succeeds
  (constraint 2 — Domovoy does not guard its ``create_entity`` calls).
- A builder failure during reconciliation raises ``HomeAssistantError``.
"""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .definitions import get_device_id, parse_entity_config, parse_update_entity
from .registrar import ServentDefinitionRegistrar, get_registrar_from_hass

_LOGGER = logging.getLogger(__name__)

SERVICE_CREATE_ENTITY = "create_entity"
SERVICE_UPDATE_STATE = "update_state"
SERVICE_CLEANUP_DEVICES = "cleanup_devices"

# Top-level schemas (M8). They only validate the outer envelope; the inner
# entity/device dicts are validated by serde.from_dict at parse time (WP3), so
# nothing Domovoy sends is rejected here:
#   - create_entity carries `entities`, a non-empty list of dicts (each entity
#     dict is passed through untouched to parse_entity_config).
#   - update_state carries `servent_id`; `state`/`attributes` stay optional and
#     `extra=ALLOW_EXTRA` lets Domovoy's extra keys through (parse_update_entity
#     ignores unknown keys, matching the pre-schema behavior).
CREATE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required("entities"): vol.All([dict], vol.Length(min=1)),
    },
    extra=vol.ALLOW_EXTRA,
)

UPDATE_STATE_SCHEMA = vol.Schema(
    {
        vol.Required("servent_id"): cv.string,
        vol.Optional("state"): object,
        vol.Optional("attributes"): dict,
    },
    extra=vol.ALLOW_EXTRA,
)

CLEANUP_DEVICES_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)


async def handle_create_entity(call: ServiceCall) -> None:
    """Create (or reconfigure) one or more ServEnt entities."""
    registrar = get_registrar_from_hass(call.hass)

    entities_list = call.data.get("entities", [])

    if not entities_list:
        raise ServiceValidationError("Call does not define any entities")

    # parse_entity_config raises ServiceValidationError for missing/unknown
    # entity_type and wraps serde errors; a malformed definition aborts the
    # whole call before anything registers.
    entities = [parse_entity_config(x) for x in entities_list]

    for definition in entities:
        try:
            registrar.register_definition(definition)
        except HomeAssistantError:
            # Any HA error is a real problem; don't mask it as a type conflict.
            raise
        except Exception as err:  # noqa: BLE001 - only the type-conflict path
            # Constraint 2: re-registering a servent_id with a new entity type
            # must stay non-fatal. Domovoy does not guard its create_entity
            # calls, so promoting this to an error would crash running apps.
            # register_definition raises a bare Exception ("Cannot change the
            # type ...") only for this case; log it as a structured warning and
            # keep the original definition.
            _LOGGER.warning(
                "Ignoring type conflict for servent_id %r; keeping the existing definition: %s",
                definition.servent_id,
                err,
            )

    register_and_update_all_entities(registrar)


async def handle_update_entity(call: ServiceCall) -> None:
    """Apply a new state and attributes to an existing entity."""
    registrar = get_registrar_from_hass(call.hass)

    data = parse_update_entity(call.data)

    live_entity = registrar.get_live_entity_for_servent_id(data.servent_id)

    if live_entity:
        live_entity.set_new_state_and_attributes(data.state, data.attributes)
        live_entity.verified_schedule_update_ha_state()

    else:
        _LOGGER.warn(
            f"Tried to update a Non Registered ID {data.servent_id}. This can happen if you are sending an update event immediately after a creation event and the ID hasn't been registered yet"
        )


async def handle_cleanup_devices(call: ServiceCall) -> None:
    """Remove ServEnts devices not present in the current run's definitions."""
    hass = call.hass
    registrar = get_registrar_from_hass(hass)

    device_registry = dr.async_get(hass)

    definitions = registrar.get_all_entities()

    device_ids = set([get_device_id(x.device_definition) for x in definitions if x.device_definition])

    devices = [d for d in device_registry.devices.values() if any([a[0] == DOMAIN for a in d.identifiers])]

    for device_entry in devices:
        for identifier in device_entry.identifiers:
            if identifier[1] in device_ids:
                break
        else:
            device_registry.async_remove_device(device_entry.id)


def register_and_update_all_entities(registrar: ServentDefinitionRegistrar) -> None:
    """Build entities for new definitions and reconfigure existing live ones."""
    ents = registrar.get_all_entities()

    for ent_config in ents:
        servent_id = ent_config.servent_id

        live_entity = registrar.get_live_entity_for_servent_id(servent_id)

        try:
            if live_entity is None:
                registrar.build_and_register_entity(ent_config)
            else:
                live_entity._update_servent_entity_config(ent_config)
                live_entity.verified_schedule_update_ha_state()
        except HomeAssistantError:
            raise
        except Exception as err:
            # A builder failure (e.g. the platform has not registered a builder
            # yet) leaves partially applied state; surface it as a proper HA
            # error rather than a bare propagating Exception.
            raise HomeAssistantError(
                f"Failed to build or update entity {servent_id!r}: {err}"
            ) from err


def async_register_services(hass: HomeAssistant) -> None:
    """Register the three ServEnts services with their top-level schemas."""
    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_ENTITY, handle_create_entity, schema=CREATE_ENTITY_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE_STATE, handle_update_entity, schema=UPDATE_STATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEANUP_DEVICES, handle_cleanup_devices, schema=CLEANUP_DEVICES_SCHEMA
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove the three ServEnts services (pairs with async_register_services)."""
    for service in (SERVICE_CREATE_ENTITY, SERVICE_UPDATE_STATE, SERVICE_CLEANUP_DEVICES):
        hass.services.async_remove(DOMAIN, service)
