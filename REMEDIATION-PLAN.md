# ServEnts Remediation Plan — Model Assignments & Orchestration

Companion to `FABLE-AUDIT.md`. Every audit finding is assigned to a work
package (WP), and every work package to the cheapest model tier that can
execute it safely. The packages follow the audit's "Suggested priority
order" and run **strictly sequentially** — they touch the same files and
each later package assumes the earlier ones landed. Each package is
independently shippable (green suite + clean ruff + one commit).

The non-negotiable context for every package is the **"Hard constraint:
fixes must not break Domovoy"** section of `FABLE-AUDIT.md` and its
**"Test-flip map"** — both must be read in full by every agent that touches
code.

---

## Model tiers and rationale

| Model  | Used for                                                                                                                                               | Packages        |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- |
| Fable  | Contract-critical rework where the obvious fix breaks Domovoy, and the parse-layer replacement with deliberate behavioral deltas. Highest blast radius | WP3, WP7        |
| Opus   | Cross-cutting restructures with HA lifecycle subtleties and several interacting findings per package. Also the orchestrator itself                     | WP4, WP5, WP6   |
| Sonnet | Contained multi-file fixes that the audit already specifies precisely, with low design ambiguity                                                       | WP1b, WP2, WP8a |
| Haiku  | Mechanical edits with an exact spec and (where applicable) an existing pinned test to flip                                                             | WP1a, WP8b      |

---

## Per-issue assignments

| ID  | Package      | Model        | Fix (short)                                                    |
| --- | ------------ | ------------ | -------------------------------------------------------------- |
| H1  | WP1a         | Haiku        | Delete the never-set `hass.data[DOMAIN]` pop in unload         |
| H2  | WP1b         | Sonnet       | Filter cleanup candidates by identifier domain, not value      |
| H3  | WP7          | Fable        | Class-level `_unrecorded_attributes` so it actually applies    |
| H4  | WP7          | Fable        | Restore only ServEnts-owned attrs; `fixed_attributes` win      |
| H5  | WP2+WP3      | Sonnet       | Drop `pytz`; declare runtime deps in `manifest.json`           |
| H6  | WP6          | Opus         | Apply new threshold params on re-create                        |
| H7  | WP5          | Opus         | Proper error types; type-conflict path stays non-fatal         |
| H8  | WP1b+WP3     | Sonnet+Fable | Coerce `device_definition` (stopgap), then native `from_dict`  |
| M1  | WP1a         | Haiku        | `is not None` checks for number min/max/step                   |
| M2  | WP6          | Opus         | Button `update_state` applies attributes, not silent no-op     |
| M3  | WP8b         | Haiku        | Document frozen `sensor-` prefix in code (no behavior change)  |
| M4  | WP8a         | Sonnet       | DATE class emits `date`; accept float epochs                   |
| M5  | WP4          | Opus         | Key builders by type object; align with registration check     |
| M6  | WP4          | Opus         | Stop hard-setting `is_hass_up=True` on registrar reset         |
| M7  | WP4          | Opus         | Single "HASS is up" tracking path, with unsubscribe handles    |
| M8  | WP3+WP5      | Fable+Opus   | Parse-time validation via data model + top-level `vol.Schema`  |
| M9  | WP3          | Fable        | No mutation of nested `ServiceCall.data`; fixed by `from_dict` |
| M10 | WP2+WP5+WP8a | Sonnet+Opus  | Modern HA APIs: async setup/register, config-flow, manifest    |
| M11 | WP4          | Opus         | No duplicate hass-up entity on config-entry reload             |
| L1  | WP8b         | Haiku        | Fix copy-paste strings (services.yaml header, docstring)       |
| L2  | WP2          | Sonnet       | Align `manifest.json` / `pyproject.toml` versions              |
| L3  | WP8b         | Haiku        | Remove dead code still remaining after WP3–WP7                 |
| L4  | WP8b         | Haiku        | Relative imports everywhere                                    |
| L5  | WP8a         | Sonnet       | Rename definition-vs-live-entity variables                     |
| L6  | WP3          | Fable        | Eager coercion; no side effects in `device_info` getter        |
| L7  | WP7          | Fable        | Adopt `extra_restore_state_data` end to end                    |
| L8  | WP6          | Opus         | Threshold sensor merges `fixed_attributes`                     |
| L9  | WP4+WP5      | Opus         | Unregister services/listeners/websocket on unload              |
| L10 | WP8b         | Haiku        | Fire `servent.core_reloaded` only on actual reload             |
| L11 | WP3          | Fable        | Disappears with `data_carriers.py`                             |
| S1  | WP4          | Opus         | Registrar state onto `entry.runtime_data`; kill singleton      |
| S2  | WP5          | Opus         | Extract `services.py` per HA convention                        |
| S3  | WP6          | Opus         | Two-step lifecycle: `__init__` + `apply_config`                |
| S4  | WP6          | Opus         | Base class owns attribute merge + restore; one platform hook   |
| S5  | WP4+WP5      | Opus         | Separate definition store from entity factory                  |
| S6  | WP3          | Fable        | Replace `data_carriers.py` with `servents-data-model`          |

---

## Work packages

Run in this exact order. Common acceptance for every package: full suite
green (`uv run pytest -q`), lint clean
(`uvx ruff check custom_components/ tests/`), pinned tests flipped only as
listed in the audit's test-flip map, no edits under `~/dev/domovoy`, one
commit referencing the audit IDs (e.g. `Fix H2: cleanup_devices domain
filter`), and the corresponding findings in `FABLE-AUDIT.md` annotated as
fixed by this package.

### WP1a — Trivial destructive-bug fixes (Haiku)

- **H1**: delete the `hass.data[DOMAIN]` pop in `__init__.py:146`;
  `async_unload_entry` returns the platform-unload result.
- **M1**: `number.py:43-50` — replace falsy checks on
  `max_value`/`min_value`/`step` with `is not None`.
- Flip: `test_platform_entities.py::test_falsy_bounds_are_ignored`
  (0.0 bounds must now apply).

### WP1b — Cleanup-devices correctness + H8 stopgap (Sonnet)

- **H2**: `__init__.py:96` — select removal candidates with
  `a[0] == DOMAIN` instead of `"servent" in a[1]`.
- **H8 (stopgap)**: in `to_dataclass` (`data_carriers.py`), coerce a dict
  `device_definition` into `ServentDeviceDefinition` exactly as
  `device_config` is coerced. This is deliberately temporary — WP3 deletes
  it — but un-breaks `cleanup_devices` for Domovoy immediately.
- Flip: both `test_services.py::TestCleanupDevices` quirk tests;
  `test_domovoy_wire_format.py::test_cleanup_devices_crashes_on_uncoerced_device_definition`
  (raises → succeeds) and `test_device_definition_dict_is_not_coerced_eagerly`
  (dict → dataclass).

### WP2 — Runtime dependencies and manifest hygiene (Sonnet)

- **H5 (pytz half)**: remove the `pytz` import from `sensor.py`; use
  `datetime.timezone.utc` or `homeassistant.util.dt` instead. Do **not**
  add `pytz` to requirements.
- **M10 (manifest rows)**: add `integration_type` to `manifest.json`; point
  `documentation` at the repo instead of the issues URL.
- **L2**: align `manifest.json` version with `pyproject.toml` (0.6.0).
- Note: the `"requirements": ["servents-data-model==0.6.0"]` line lands in
  WP3, together with the import that needs it.

### WP3 — Replace `data_carriers.py` with `servents-data-model` (Fable)

The parse-layer migration described in the audit's "servents-data-model
adoption" section — read it in full, including the behavioral-deltas table.

- **S6/H8/L6**: delete `data_carriers.py`; parse service payloads with
  `serde.from_dict` on the shared `servents_data_model` classes. Nested
  `device_definition` deserializes to `DeviceConfig` natively; remove the
  side-effecting coercion in the `device_info` getter (and the WP1b
  stopgap).
- **M8 (field half) / M9 / L11**: parse-time required-field and `Literal`
  validation; no more mutation of nested `ServiceCall.data`; no more
  `inspect.signature` per build.
- Add `"requirements": ["servents-data-model==0.6.0"]` to `manifest.json`
  (completes H5).
- Keep the `entity_type` → class dispatch, keyed on the shared `EntityType`
  StrEnum.
- Wrap `SerdeError`/`ValueError` in `ServiceValidationError`.
- `DeviceConfig` has no `get_device_id()` — the `device-{device_id}` prefix
  logic must live on (or wrap) the integration side (constraint 7).
- Migrate the `update_state` path (`ServentUpdateEntity`) in the same sweep.
- Constraints 6 and 8: `device_definition` accepted as-is; `app_name` /
  `is_global` accepted and ignored (pinned by
  `test_app_name_and_is_global_are_silently_ignored`, must keep passing).
- Flip: the `test_data_carriers.py` lenient-default tests exactly per the
  behavioral-deltas table and the test-flip map — each flip is a conscious
  decision, noted in the commit message.

### WP4 — Registrar onto the config entry; kill the singleton (Opus)

- **S1**: move all registrar state to `entry.runtime_data`; remove the
  module-level singleton, `get_registrar()` call sites, and the
  `reset_registrar` hack (**M6** disappears with it).
- **M5**: key builders by the type object with exact-type registration so
  registration and dispatch agree. Flip the two pinned
  `test_registrar.py` quirk tests.
- **M7/L9 (listener half)**: one place registers the
  `EVENT_HOMEASSISTANT_STARTED/STOP` listeners, holding unsubscribe handles
  released on unload.
- **M11**: the hass-up sensor is added once per entry lifecycle; reload must
  not log a duplicate-unique_id error, and the live instance must be the one
  the listeners drive.
- **S5 (partial)**: separate the definition store from the entity factory so
  builders stop smuggling `async_add_entities` by closure.
- Constraint 4: `servent/hass-state` keeps its name and
  `{"is_hass_up": bool}` shape.

### WP5 — `services.py`, schemas, and error semantics (Opus)

- **S2**: move the three service handlers (including the
  `handle_cleanup_devices` closure) into a `services.py` module;
  `ServiceCall.hass` replaces the closure-captured `hass`.
- **M10 (setup rows)**: `async_setup` + `hass.services.async_register`; fix
  the wrong `ConfigEntry` annotation.
- **M8 (schema half)**: top-level `vol.Schema` per service (`entities` is a
  non-empty list of dicts; `update_state` requires `servent_id`), with
  selectors in `services.yaml`.
- **H7**: malformed payloads and unknown `entity_type` raise
  `ServiceValidationError`; builder failures raise `HomeAssistantError`.
  **The servent_id type-conflict path stays non-fatal** — structured
  warning log, call succeeds (constraint 2;
  `test_services.py::test_type_conflict_is_logged_not_raised` must keep
  passing).
- **L9 (service half)**: unregister services and the websocket command on
  unload.

### WP6 — Entity lifecycle collapse and platform de-duplication (Opus)

- **S3**: merge `ServEntEntityAttributes`/`ServEntEntity`; replace
  `servent_configure` / `_update_servent_entity_config` /
  `update_specific_entity_config` with `__init__` + one `apply_config`
  hook.
- **S4**: the base class owns the
  `fixed_attributes | attributes | {"servent_id": ...}` merge, the restore
  flow, and the builder-registration boilerplate; platforms implement a
  single "write the native state attr" hook. **Constraint 1: `servent_id`
  must remain in every entity's live attributes, buttons included.**
- **M2**: button `update_state` applies the attributes (preferred) — never
  a service error (constraint 3).
- **H6**: re-creating a threshold sensor applies the new `entity_id` /
  `lower` / `upper` / `hysteresis` (HA 2025.11 `ThresholdSensor.__init__`
  is keyword-only — see audit "Verified facts").
- **L8**: threshold sensor's `extra_state_attributes` includes
  `fixed_attributes` (falls out of S4 if the base owns the merge).

### WP7 — Attribute persistence done right (Fable)

The audit calls this one of the three places where the obvious fix breaks
Domovoy. Constraint 1 is absolute: `servent_id` must be present in the live
state's attributes at all times, for every entity type.

- **H3**: `_unrecorded_attributes` must be a **class** attribute (or use
  `MATCH_ALL`) — instance assignment is provably ignored by
  `Entity.__init_subclass__`. Decide the recording policy deliberately:
  per-config keys cannot be expressed with a static set.
- **H4/L7**: persist ServEnts-owned attributes via `ServentExtraData` +
  `extra_restore_state_data` (write side finally implemented); on restore,
  take only ServEnts-owned keys — never the full historical
  `state.attributes` — and merge current `fixed_attributes` **last** so
  updated fixed attributes are not reverted by stale restores.

### WP8a — Non-trivial hygiene (Sonnet)

- **M4**: `sensor.py` DATE branch produces a `date` (`.date()`); parse
  epochs with `float(...)` so `"1700000000.5"` works for TIMESTAMP.
- **L5**: rename definition-holding variables/functions
  (`get_all_entities`, `live_entity`, `servent_current_config`) to say
  "definition"; the definition/live-entity distinction is the core design.
- **M10 (config-flow row)**: `class ServentsConfigFlow(ConfigFlow,
  domain=DOMAIN)` instead of the legacy `HANDLERS.register` decorator.

### WP8b — Mechanical hygiene (Haiku)

- **L1**: fix the "Irrigation Unlimited" line in `services.yaml` and the
  "Handle search." docstring.
- **L3**: remove dead code that is *still* dead after WP3–WP7 (check first:
  `ServentExtraData` becomes live in WP7 — do not remove it; the redundant
  `options`/`name` property overrides and any leftover unused loggers go).
- **L4**: convert the remaining absolute `custom_components.servents.`
  imports to relative.
- **L10**: fire `servent.core_reloaded` only on an actual reload, not first
  setup (Domovoy verifiably does not listen for it — audit "Verified
  facts").
- **M3**: add a comment at the unique_id construction pinning the frozen
  `sensor-` prefix (constraint 7). Do **not** change the value; do **not**
  flip `test_unique_id_uses_sensor_prefix_for_all_types`.
- **M10 (logger row)**: any surviving `_LOGGER.warn` → `warning`.

---

## Orchestrator prompt (for an Opus agent)

Hand the block below verbatim to an Opus agent with access to the Agent
tool. It dispatches each work package to a subagent running the assigned
model.

```text
You are the remediation orchestrator for the ServEnts Home Assistant
integration at /home/cargsl/dev/servents. Your job is to land every fix in
REMEDIATION-PLAN.md by dispatching one subagent per work package, each on
the model tier the plan assigns. You coordinate, verify, and commit; the
subagents write the code.

Setup — do this yourself before dispatching anything:
1. Read /home/cargsl/dev/servents/FABLE-AUDIT.md in full. The "Hard
   constraint" section (8 numbered Domovoy contract points), the
   "Test-flip map", and "Remediation working notes" govern everything.
2. Read /home/cargsl/dev/servents/REMEDIATION-PLAN.md in full — it defines
   the work packages, their order, and their model assignments.
3. Confirm the baseline: `uv run pytest -q` (expect ~123 passing; ignore
   the VIRTUAL_ENV mismatch warning) and
   `uvx ruff check custom_components/ tests/` (clean).

Dispatch loop — for each work package, strictly in this order, one at a
time, never in parallel (they edit the same files):
  WP1a (haiku) → WP1b (sonnet) → WP2 (sonnet) → WP3 (fable) →
  WP4 (opus) → WP5 (opus) → WP6 (opus) → WP7 (fable) →
  WP8a (sonnet) → WP8b (haiku)

Use the Agent tool with subagent_type "general-purpose" and the model
parameter set to the package's tier ("haiku", "sonnet", "opus", "fable").

Every subagent prompt must contain:
- The repo path (/home/cargsl/dev/servents) and the instruction to first
  read FABLE-AUDIT.md in full — especially the "Hard constraint" section,
  the "Test-flip map", and "Remediation working notes" — and then its own
  work-package section in REMEDIATION-PLAN.md.
- The package's full scope copied from REMEDIATION-PLAN.md, including
  which pinned characterization tests to flip and which must NOT flip.
- The commands: `uv run pytest -q` and
  `uvx ruff check custom_components/ tests/`, both of which must be clean
  before it reports back.
- Hard rules: fix ONLY the findings in its package (report anything else
  it notices, don't fix it); never modify anything under ~/dev/domovoy;
  never change wire identifiers (unique_id `sensor-{servent_id}`, device
  identifier `device-{device_id}`, event prefix `servent.`, websocket
  command `servent/hass-state`); flip a pinned test only when its fix is
  in scope, per the test-flip map. When a fix touches HA internals, read
  the installed source at .venv/lib/python3.14/site-packages/homeassistant/
  rather than assuming. Markdown tables it edits must stay aligned.
- Required report format: files changed, tests flipped (with names),
  final pytest/ruff output summary, and any in-scope decision it made
  that the plan left open.
- The instruction to update the fixed findings in FABLE-AUDIT.md in place
  (append "**Fixed** in WPn." to each finding it resolved).

Verification gate — after each subagent returns, before moving on:
1. Run `uv run pytest -q` and `uvx ruff check custom_components/ tests/`
   yourself. Both must be clean.
2. Review the diff (`git diff`) against the package scope and the 8
   Domovoy constraints. Pay particular attention on WP5 (type-conflict
   path must stay non-fatal — test_type_conflict_is_logged_not_raised
   still passing), WP6 (button update_state must not reject; servent_id
   in attributes), and WP7 (servent_id in live attributes at all times).
3. Check that only the test flips allowed by the test-flip map happened.
4. If anything fails, send the failure back to the SAME subagent via
   SendMessage with the exact error output and let it fix its own work.
   Do not silently fix it yourself; do not proceed to the next package
   until green.
5. Commit with one commit per package, message referencing the audit IDs
   (e.g. "Fix H1, M1: unload crash and falsy number bounds (WP1a)"),
   ending with the standard Claude co-author line. Do not push.

Special notes:
- WP3 is the riskiest package (parse-layer replacement with deliberate
  behavioral changes). Its commit message must list each lenient-default
  test flipped and the behavioral delta it corresponds to.
- WP1b's H8 stopgap is intentionally deleted again by WP3 — that is
  expected, not churn.
- The manifest `requirements` line for servents-data-model belongs to
  WP3, not WP2.

Done criteria: all 10 packages committed; full suite green; ruff clean;
every finding in FABLE-AUDIT.md annotated fixed (M3 and the frozen-ID
constraints are documented, not changed). Finish with a summary of all
commits and any findings the plan left open plus how they were resolved.
The final acceptance test described in the audit — a running Domovoy
instance pointed at the fixed integration with zero Domovoy-side edits —
is a manual step for the user; call it out explicitly at the end.
```
