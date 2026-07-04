# Agent Instructions

These notes capture repo-specific constraints and Home Assistant live-test
setup details that future agents should follow.

## Repository Rules

- Verify Markdown formatting with the shared markdown formatter after editing
  Markdown files.
- Never change, rewrite, or temporarily repoint the repository `origin` remote.
- Do not pin Docker base images by digest or SHA.

## Live Home Assistant Validation

Use Home Assistant's normal custom integration loading path. Do not modify the
ServEnts `manifest.json` in the source tree or in a temporary copy to point at
local wheels or test-only requirements.

For a disposable Docker Home Assistant run:

1. Create a temporary HA config directory under `.tmp/live-ha/config`.
2. Copy this repository's `custom_components/servents` directory to
   `.tmp/live-ha/config/custom_components/servents`.
3. Leave `custom_components/servents/manifest.json` unchanged. The manifest is
   the integration contract HA reads for custom component metadata and
   requirements.
4. Build the local `servents-data-model` wheel from `servents-data-model/`.
5. Install that wheel into the HA config deps user-site before HA starts. In a
   container, compute the same target HA uses with:

   ```bash
   docker run --rm -v "$PWD/.tmp/live-ha/config:/config" \
     homeassistant/home-assistant:stable \
     sh -c 'PYTHONUSERBASE=/config/deps python -m site --user-site'
   ```

   Then install the wheel into that path with `python -m uv pip install
   --target <computed-user-site> /config/wheels/<wheel-file>.whl`.
6. Start the dedicated Home Assistant container with the temp config mounted at
   `/config` and a random host port for `8123`.
7. Create the ServEnts config entry through Home Assistant's config-flow API,
   then drive real HA service calls and state reads through the REST or
   WebSocket APIs.
8. Stop and remove the container after the test unless a debug flag explicitly
   keeps it.

Why this is the correct mechanism:

- HA mounts the config directory to import `custom_components` during loader
  setup.
- HA discovers custom integrations by importing the `custom_components`
  namespace and resolving each integration from
  `custom_components/<domain>/manifest.json`.
- HA processes manifest `requirements` through its requirements manager. For
  live tests of unpublished package code, preinstall the local wheel into the
  config deps user-site so the manifest requirement is already satisfied.

If the data-model version changes, update the real source manifest and package
metadata as part of the normal versioning work. Do not patch a copied manifest
only for live validation.
