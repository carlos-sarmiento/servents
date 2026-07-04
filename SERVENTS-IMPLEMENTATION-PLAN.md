# ServEnts Work Order Implementation Plan

This document translates the ServEnts work order into staged implementation,
verification, and release work.

## Purpose

Implement the contracts in `SERVENTS-WORK-ORDER.md` across the ServEnts
custom component and the `servents-data-model` package, with compatibility
checked against the local Home Assistant checkout at
`/home/cargsl/dev/github/homeassistant`.

The plan is intentionally staged so each PR has a clear contract boundary,
focused tests, and a realistic chance of review. The live Home Assistant test
harness is part of the work, not an optional afterthought.

## Source Baseline

| Source                 | Location                                | Baseline                 |
| ---------------------- | --------------------------------------- | ------------------------ |
| ServEnts component     | `/home/cargsl/dev/servents`             | `master` at `6123dc5`    |
| ServEnts data model    | `servents-data-model/`                  | `master` at `bff5cb4`    |
| Home Assistant API ref | `/home/cargsl/dev/github/homeassistant` | `dev` at `7dc93c57e4f`   |
| Work order             | `SERVENTS-WORK-ORDER.md`                | Untracked handoff source |

## Compatibility Findings From Home Assistant

These findings must guide implementation, because some work-order names do not
map 1:1 to HA internals.

| Area        | Compatibility requirement                                                                                                                                         |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `date_time` | Domovoy wire type remains `date_time`, but HA platform/domain is `datetime`, exposed as `Platform.DATETIME` and `homeassistant.components.datetime`.              |
| Light       | Brightness support is expressed with `ColorMode.BRIGHTNESS` in `_attr_supported_color_modes`; do not invent a brightness feature flag.                            |
| Light       | When the light is on, HA requires a valid `_attr_color_mode`; use `ColorMode.ONOFF` or `ColorMode.BRIGHTNESS` according to config and state.                      |
| Cover       | State comes from `_attr_is_closed`, `_attr_is_opening`, `_attr_is_closing`, and `_attr_current_cover_position`; feature flags gate HA services.                   |
| Fan         | `FanEntity.is_on` derives from `percentage > 0` or non-`None` `preset_mode`; command handling must keep those fields coherent.                                    |
| Climate     | `TARGET_TEMPERATURE` and `TARGET_TEMPERATURE_RANGE` are mutually exclusive; `hvac_modes`, temp bounds, fan/preset/swing lists are capability attributes.          |
| Lock        | `code_format` is a state attribute and HA validates codes before dispatching service methods.                                                                     |
| Valve       | The base entity class lives in `homeassistant.components.valve.entity`; set `reports_position=True` when `supports_position=True`.                                |
| Siren       | HA service input `volume_level` is a `0.0..1.0` float; Domovoy command payload wants integer percent `0..100`.                                                    |
| Text        | HA uses `_attr_native_min`, `_attr_native_max`, `_attr_pattern`, and `_attr_mode`; service validation happens before `async_set_value`.                           |
| Date/time   | `DateEntity`, `TimeEntity`, and `DateTimeEntity` use `native_value`; datetime state serializes as UTC ISO seconds and must be timezone-aware.                     |
| Event       | `EventEntity._trigger_event` validates allowed event types and updates timestamp plus attributes; wrap invalid types as `HomeAssistantError` in the service path. |
| Registry    | Entity registry migration uses `(ha_domain, platform, unique_id)` where platform is always `servents` and unique ID remains `sensor-{servent_id}`.                |

## Non-Goals

| Item                                 | Reason                                                                  |
| ------------------------------------ | ----------------------------------------------------------------------- |
| Media player, camera/image, update   | Explicitly deferred by FEAT-SRV-13.                                     |
| Changing the frozen unique ID prefix | `sensor-` is existing wire/registry format and must remain unchanged.   |
| Device ID migration on rename        | FEAT-SRV-14 only migrates entity registry unique IDs.                   |
| Docker image digest pinning          | Repository policy prefers floating tags for automatic upstream patches. |

## Phase 0: Live Home Assistant Harness Bootstrap

Goal: make the required live Docker validation available before any feature
phase is considered complete. The original plan placed the live harness in
Phase 9, but the execution goal requires a dedicated disposable Home Assistant
container after every phase. This prerequisite phase moves the minimum harness
needed for Phase 1 ahead of data-model work while keeping the broader Phase 9
test-case expansion intact.

1. Create `scripts/live_ha_e2e.py` and keep all runtime files under
   `.tmp/live-ha/` so cleanup is deterministic.
2. Build and preinstall a local `servents-data-model` wheel into a dedicated
   Home Assistant container before HA starts.
3. Copy `custom_components/servents` into the container config directory and
   write a minimal `configuration.yaml`.
4. Start `homeassistant/home-assistant:stable` or a configured floating tag on
   a random host port, wait for `/api/` and `/manifest.json`, then create an
   access token through HA auth.
5. Create the ServEnts config entry through HA's config-flow API.
6. Implement the minimum live smoke that Phase 1 can exercise without new
   component platforms: HA starts cleanly, the ServEnts config entry loads, and
   the existing sensor path can create and update a live entity.
7. Always stop and remove the container unless `--keep-container` is passed for
   debugging, and print HA logs plus the HA version on failure.

Validation:

- `uv run python scripts/live_ha_e2e.py --image homeassistant/home-assistant:stable`
- The harness must not depend on a developer's real HA instance, real HA
  config, or a fixed port.

## Phase 1: Data Model Expansion

Goal: make `servents-data-model` parse every new Domovoy payload natively.

1. Add `EntityType` values:
   `LIGHT`, `COVER`, `FAN`, `CLIMATE`, `LOCK`, `VALVE`, `SIREN`, `TEXT`,
   `DATE`, `TIME`, `DATETIME`, and `EVENT`.
2. Add config dataclasses:
   `LightConfig`, `CoverConfig`, `FanConfig`, `ClimateConfig`, `LockConfig`,
   `ValveConfig`, `SirenConfig`, `TextConfig`, `DateConfig`, `TimeConfig`,
   `DatetimeConfig`, and `EventConfig`.
3. Extend base models:
   `DeviceConfig` gains rich device fields; `EntityConfig` gains
   `restore_state: bool = True` and
   `previous_servent_ids: list[str] | None = None`; `ServentUpdateEntity`
   gains `available: bool | None = None`,
   `merge_attributes: bool | None = None`, and optional `state`.
4. Add model validation:
   climate mode lists and target-temperature exclusivity, climate temp bounds,
   event non-empty `event_types`, text bounds, date/time wire type names, and
   enum/literal constraints for device classes and modes.
5. Version and packaging:
   publish a single version that covers the whole work order instead of
   releasing `0.7.0`, `0.8.0`, `0.9.0`, and `0.10.0` independently unless the
   package registry workflow requires intermediate versions.

Validation:

- `uv run pytest -q` inside `servents-data-model`.
- Add serde round-trip tests for each work-order payload.
- Add negative tests for every component-side rejection that should happen at
  parse time.

## Phase 2: Component Shared Semantics

Goal: update the existing platforms before adding new ones, so every platform
inherits the same availability, attribute, restore, and rename behavior.

1. Add availability support in `ServEntEntity`:
   `_servent_available = True`, `available`, `set_availability`, and reset to
   available in `apply_config`.
2. Gate restore reads with `restore_state`; keep writing `extra_restore_state_data`
   so flipping the flag back to `True` can restore again later.
3. Update `handle_update_entity`:
   detect presence of the raw `state` key, support availability-only updates,
   support attribute-only updates, support `merge_attributes`, and schedule one
   HA state update after all changes.
4. Add entity/domain helpers:
   map each `EntityType` to the HA platform domain, with
   `THRESHOLD_BINARY_SENSOR -> binary_sensor` and `DATETIME -> datetime`.
5. Add rename migration before entity build:
   migrate the first resolvable previous unique ID, no-op when already migrated,
   and warn/refuse when both old and new registry entries exist.
6. Update device info:
   pass through rich device fields, with `sw_version or version` precedence and
   no clearing when rich fields are absent.

Validation:

- Existing unit tests remain green.
- Add tests for availability-only, available-plus-state, attribute-only,
  merge-attributes, restore opt-out, restore re-enable, rich device info, and
  rename migration conflicts.

## Phase 3: Registrar And Services

Goal: provide the service surface Domovoy now expects.

1. Add registrar helpers:
   `get_definition_for_servent_id`, `remove_definition`, and
   `remove_live_entity`.
2. Add `servents.remove_entity`:
   idempotent for unknown IDs, removes the HA registry entry when present,
   removes the registrar definition, removes the live reference, and removes the
   device only when no remaining registry entries point at it.
3. Add `servents.trigger_event`:
   find live event entity, validate event type through the entity, trigger it,
   and silently no-op if the entity is not live yet.
4. Update service registration and teardown:
   include `remove_entity` and `trigger_event` in registration,
   unregistration, `services.yaml`, and tests.

Validation:

- Removal tests for unknown ID, live entity, definition-only entity, multi-entity
  device retention, last-entity device cleanup, and recreate-after-remove.
- Trigger tests for valid event, invalid event, attributes, repeated trigger
  timestamp changes, and non-live no-op.

## Phase 4: Simple New Platforms

Goal: add low-command-complexity platforms and verify platform/domain plumbing.

| Platform    | HA base class    | Key implementation notes                                                                                            |
| ----------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| `text`      | `TextEntity`     | Set `_attr_native_value`, `_attr_native_min`, `_attr_native_max`, `_attr_pattern`, `_attr_mode`; fire change event. |
| `date`      | `DateEntity`     | Parse ISO date strings to `datetime.date`; HA service emits date objects.                                           |
| `time`      | `TimeEntity`     | Parse ISO time strings to `datetime.time`; no timezone.                                                             |
| `date_time` | `DateTimeEntity` | HA module/domain is `datetime`; require timezone-aware values and preserve HA's UTC state serialization.            |
| `event`     | `EventEntity`    | Set event types and optional device class; trigger through `_trigger_event` then write HA state.                    |

Each file follows the existing `register_platform_builder` pattern and registers
its config type in `definitions.ENTITY_TYPE_TO_CONFIG_CLASS`.

Validation:

- Unit tests for config application, state writes, service calls, and
  availability.
- Wire-format tests using the exact JSON payloads from the work order.
- Initial live Docker smoke should cover this phase before moving to
  command-heavy entities.

## Phase 5: Controllable Foundation

Goal: avoid copy-pasting command and optimistic-state logic across seven
platforms.

1. Add a small shared helper module, likely `command_entity.py`, with:
   `fire_entity_command`, `apply_if_optimistic`, and dict-state utilities.
2. Define per-platform state appliers that update only keys present in a dict.
3. Keep native HA service methods async where possible; avoid executor round
   trips for pure in-memory command/event emission.
4. Add tests for helper behavior before platform-specific tests.

## Phase 6: Light, Cover, Fan

Goal: implement FEAT-SRV-10.

| Platform | HA base class | Feature mapping                                                                                                       |
| -------- | ------------- | --------------------------------------------------------------------------------------------------------------------- |
| Light    | `LightEntity` | `supports_brightness=True` means `_attr_supported_color_modes={ColorMode.BRIGHTNESS}`; otherwise `{ColorMode.ONOFF}`. |
| Cover    | `CoverEntity` | Always advertise `OPEN|CLOSE`; add `SET_POSITION` and `STOP` only from config.                                        |
| Fan      | `FanEntity`   | Always advertise `TURN_ON|TURN_OFF`; add `SET_SPEED` for percentage and `PRESET_MODE` when preset modes are present.  |

Validation:

- HA service calls fire `servent.entity_command` with exact partial-intent
  payloads.
- Non-optimistic entities do not move on commands.
- Optimistic entities update local state immediately.
- Dict-shaped `update_state` partially updates fields.

## Phase 7: Climate

Goal: implement FEAT-SRV-11 as a focused PR because it has the highest state
surface.

1. Add `climate.py` using `ClimateEntity`.
2. Validate config both in data model and component construction.
3. Advertise only configured `ClimateEntityFeature` flags.
4. Implement HA service methods:
   `async_set_hvac_mode`, `async_set_temperature`, `async_set_fan_mode`,
   `async_set_preset_mode`, `async_set_swing_mode`, `async_turn_on`, and
   `async_turn_off`.
5. Apply dict-shaped acknowledgements field-by-field.
6. Treat `temperature_unit` as `UnitOfTemperature.CELSIUS` or
   `UnitOfTemperature.FAHRENHEIT`.

Validation:

- Unit tests for mutually exclusive target flags, feature flags, command payloads,
  partial update acknowledgements, and optimistic behavior.
- Live Docker test for at least one single-setpoint climate and one range
  climate.

## Phase 8: Lock, Valve, Siren

Goal: implement FEAT-SRV-13 after shared controllable helpers are proven.

| Platform | HA base class | Implementation notes                                                                                                               |
| -------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Lock     | `LockEntity`  | Map states to `_attr_is_locked`, `_attr_is_locking`, `_attr_is_unlocking`, `_attr_is_opening`, `_attr_is_open`, `_attr_is_jammed`. |
| Valve    | `ValveEntity` | Set `reports_position=True` when configured; position updates go to `_attr_current_valve_position`.                                |
| Siren    | `SirenEntity` | Convert HA `volume_level` float to Domovoy integer percent; advertise tone, duration, and volume flags from config.                |

Validation:

- Service-call command payload tests for every supported action.
- Partial update tests.
- Optimistic and non-optimistic tests.
- Live Docker test for one lock, one valve, and one siren command path.

## Phase 9: Live Home Assistant Docker Harness

Goal: prove the integration works against an actual running Home Assistant, not
only mocked unit tests.

Expand `scripts/live_ha_e2e.py` from Phase 0 while continuing to keep all
runtime files under `.tmp/live-ha/` so cleanup is deterministic.

### Container Strategy

| Step | Action                                                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Build a local wheel for `servents-data-model` and store it in `.tmp/live-ha/wheels/`.                                                                        |
| 2    | Copy `custom_components/servents` into `.tmp/live-ha/config/custom_components/servents`.                                                                     |
| 3    | Write a minimal `configuration.yaml` with `default_config`, HTTP enabled, and debug logging for `custom_components.servents`.                                |
| 4    | Run a one-shot container command to install the local data-model wheel and create an HA auth user with `python -m homeassistant --script auth add ...`.      |
| 5    | Start a dedicated container from `homeassistant/home-assistant:stable` or a configured tag, with no digest pinning and a random host port.                   |
| 6    | Wait until `/api/` and `/manifest.json` respond, then get an access token using `/auth/token`.                                                               |
| 7    | Create the ServEnts config entry through `/api/config/config_entries/flow` and `/api/config/config_entries/flow/{flow_id}` instead of seeding storage files. |
| 8    | Drive real HA service calls and WebSocket event subscriptions.                                                                                               |
| 9    | Always stop and remove the container unless `--keep-container` is passed for debugging.                                                                      |

The harness must not depend on a developer's real HA instance, real HA config,
or a fixed port.

### Live Test Cases

| Case               | Real HA assertion                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Config entry setup | ServEnts config entry is created through HA's config flow API and platforms load without setup errors.                   |
| Existing platform  | Create sensor, call `update_state`, then read `/api/states/sensor.*` and verify state plus ServEnts attributes.          |
| Availability       | `available:false` changes HA state to `unavailable`; `available:true` restores availability without losing native value. |
| Attribute-only     | Attributes update with no native state clobber.                                                                          |
| Text/date/time     | Create each entity and verify state serialization through `/api/states`.                                                 |
| Event              | Call `servents.trigger_event`; verify timestamp state and event attributes.                                              |
| Entity command     | Subscribe to `servent.entity_command` over WebSocket, call a native HA service, and assert the event payload.            |
| Removal            | Call `servents.remove_entity`; verify entity registry/state removal and recreate cleanly.                                |
| Rename migration   | Create old entity, restart/reload with `previous_servent_ids`, and verify one registry entry with preserved entity ID.   |

Run the live harness after normal unit tests:

```bash
uv run python scripts/live_ha_e2e.py --image homeassistant/home-assistant:stable
```

The harness should print container logs on failure and include the HA version it
tested.

## Phase 10: Final Verification And Release

Run the full local suite:

```bash
uv run pytest -q
uv run --with ruff ruff check .
git ls-files -z '*.md' | xargs -0 /home/cargsl/.agents/skills/markdown-fmt/scripts/rumdl_markdown.sh check
git diff --check
```

Run data-model checks:

```bash
cd servents-data-model
uv run pytest -q
git diff --check
```

Run live HA:

```bash
uv run python scripts/live_ha_e2e.py --image homeassistant/home-assistant:stable
```

Before release:

1. Confirm `manifest.json`, root `pyproject.toml`, data-model `pyproject.toml`,
   and `uv.lock` agree on versions.
2. Confirm `services.yaml` documents `remove_entity` and `trigger_event`.
3. Confirm no Dockerfile or workflow pins Home Assistant or base images by
   digest.
4. Confirm the untracked handoff file is either intentionally kept untracked or
   superseded by tracked docs.

## Suggested PR Order

| PR  | Scope                                           | Reason                                                                |
| --- | ----------------------------------------------- | --------------------------------------------------------------------- |
| 1   | Data model expansion and tests                  | Unblocks parsing and removes component-side staging hacks.            |
| 2   | Shared component semantics                      | Availability, attributes, restore, device info, and rename migration. |
| 3   | Service additions                               | `remove_entity`, `trigger_event`, registrar helpers, and docs.        |
| 4   | Live HA Docker harness                          | Gives every later platform PR a real integration check.               |
| 5   | Text/date/time/datetime/event platforms         | Low-command surface; proves new platform plumbing.                    |
| 6   | Controllable helper foundation                  | Reduces duplicated optimistic command handling.                       |
| 7   | Light/cover/fan                                 | First command-based feature set.                                      |
| 8   | Climate                                         | Largest state surface; easier to review separately.                   |
| 9   | Lock/valve/siren                                | Long-tail controllables using the proven helper.                      |
| 10  | Final live-test expansion, docs, version polish | Closes gaps, runs the full Docker matrix, and prepares release.       |

## Main Risks

| Risk                                     | Impact                                | Mitigation                                                                   |
| ---------------------------------------- | ------------------------------------- | ---------------------------------------------------------------------------- |
| HA cached properties hold stale attrs    | Reconfigure may expose old values     | Use `_attr_` assignment/deletion paths and tests that read before reconfig.  |
| Unpublished data-model version in Docker | Live HA cannot install requirements   | Build and preinstall local wheel in the test container before HA starts.     |
| Auth/onboarding blocks live tests        | Harness cannot create config entry    | Use HA auth script plus `/auth/token`; fallback to onboarding API if needed. |
| Registry migration collision             | Could orphan or overwrite user entity | Explicit both-present check, log warning, never delete on conflict.          |
| Command event race in WebSocket tests    | Flaky live assertions                 | Subscribe before service call and use bounded retries with log dump.         |
| Too much surface in one PR               | Review becomes ineffective            | Keep PR order above and require green unit plus live smoke per PR.           |
