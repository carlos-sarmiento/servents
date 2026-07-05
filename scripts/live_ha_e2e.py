"""Live Home Assistant validation for the ServEnts custom integration.

This script intentionally uses Home Assistant's normal custom integration
loading path:

- copy custom_components/servents into a disposable /config/custom_components
- preinstall the local servents-data-model wheel into a mounted Python user-site
- leave the integration manifest unchanged
- create the config entry and exercise services through HA's public APIs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import tomllib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aiohttp import ClientSession, WSMsgType


ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = ROOT / ".tmp" / "live-ha"
CONFIG_DIR = LIVE_ROOT / "config"
WHEELS_DIR = LIVE_ROOT / "wheels"
USER_SITE_DIR = LIVE_ROOT / "user-site"
COMPONENT_SRC = ROOT / "custom_components" / "servents"
COMPONENT_DST = CONFIG_DIR / "custom_components" / "servents"
DATA_MODEL_DIR = ROOT / "servents-data-model"
SERVENT_ID = "live-ha-temperature"
TEXT_SERVENT_ID = "live-ha-text"
DATE_SERVENT_ID = "live-ha-date"
TIME_SERVENT_ID = "live-ha-time"
DATETIME_SERVENT_ID = "live-ha-datetime"
EVENT_SERVENT_ID = "live-ha-event"
LIGHT_SERVENT_ID = "live-ha-light"
COVER_SERVENT_ID = "live-ha-cover"
FAN_SERVENT_ID = "live-ha-fan"
CLIMATE_SERVENT_ID = "live-ha-climate"
CLIMATE_RANGE_SERVENT_ID = "live-ha-climate-range"
AUTH_USER = "servents-live"
AUTH_PASSWORD = "servents-live-password"
CLIENT_ID = "http://localhost/"


class LiveHAError(RuntimeError):
    """Raised when live Home Assistant validation fails."""


def run_command(
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command with useful failure output."""
    result = subprocess.run(  # noqa: S603 - command is assembled from trusted script inputs
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise LiveHAError(f"Command failed ({result.returncode}): {' '.join(cmd)}\n{output}")
    return result


def docker_volume(host_path: Path, container_path: str, suffix: str) -> str:
    """Return a Docker bind-mount argument."""
    volume = f"{host_path.resolve()}:{container_path}"
    if suffix:
        volume = f"{volume}:{suffix}"
    return volume


def docker_run_base(args: argparse.Namespace) -> list[str]:
    """Base Docker command."""
    return [args.docker_bin]


def docker_run_rm(args: argparse.Namespace, *extra: str) -> subprocess.CompletedProcess[str]:
    """Run a one-shot Home Assistant container."""
    return run_command([*docker_run_base(args), "run", "--rm", *extra])


def remove_runtime_tree(args: argparse.Namespace) -> None:
    """Remove the disposable runtime tree, including root-owned container files."""
    if not LIVE_ROOT.exists():
        return

    try:
        shutil.rmtree(LIVE_ROOT)
        return
    except PermissionError:
        pass

    LIVE_ROOT.parent.mkdir(exist_ok=True)
    result = run_command(
        [
            *docker_run_base(args),
            "run",
            "--rm",
            "-v",
            docker_volume(LIVE_ROOT.parent, "/work", args.volume_suffix),
            args.image,
            "sh",
            "-c",
            "rm -rf /work/live-ha",
        ],
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise LiveHAError(f"Failed to remove {LIVE_ROOT}: {output}")


def prepare_runtime(args: argparse.Namespace) -> None:
    """Create a clean disposable HA config tree."""
    remove_runtime_tree(args)

    (CONFIG_DIR / "custom_components").mkdir(parents=True)
    WHEELS_DIR.mkdir(parents=True)
    USER_SITE_DIR.mkdir(parents=True)

    shutil.copytree(
        COMPONENT_SRC,
        COMPONENT_DST,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
    )

    source_manifest = COMPONENT_SRC / "manifest.json"
    copied_manifest = COMPONENT_DST / "manifest.json"
    if source_manifest.read_bytes() != copied_manifest.read_bytes():
        raise LiveHAError("Copied custom component manifest differs from the source manifest")

    (CONFIG_DIR / "configuration.yaml").write_text(
        "\n".join(
            [
                "default_config:",
                "",
                "logger:",
                "  default: info",
                "  logs:",
                "    custom_components.servents: debug",
                "",
            ]
        ),
        encoding="utf-8",
    )


def read_pyproject_version(path: Path) -> str:
    """Read a pyproject project version."""
    data = tomllib.loads((path / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def manifest_data_model_requirement() -> str | None:
    """Return the ServEnts data-model manifest requirement, if present."""
    manifest = json.loads((COMPONENT_SRC / "manifest.json").read_text(encoding="utf-8"))
    for requirement in manifest.get("requirements", []):
        if requirement.startswith("servents-data-model"):
            return requirement
    return None


def ensure_local_wheel_matches_manifest() -> None:
    """Avoid accidentally validating against the published data-model package."""
    requirement = manifest_data_model_requirement()
    if requirement is None:
        raise LiveHAError("ServEnts manifest has no servents-data-model requirement")

    version = read_pyproject_version(DATA_MODEL_DIR)
    expected = f"servents-data-model=={version}"
    if requirement != expected:
        raise LiveHAError(
            "Local data-model version does not match the real manifest requirement. "
            f"Expected {expected!r}, found {requirement!r}. Update source metadata instead of "
            "patching the copied manifest."
        )


def build_data_model_wheel() -> Path:
    """Build the local servents-data-model wheel."""
    ensure_local_wheel_matches_manifest()
    run_command(["uv", "build", "--wheel", "--out-dir", str(WHEELS_DIR), str(DATA_MODEL_DIR)])
    wheels = sorted(WHEELS_DIR.glob("servents_data_model-*.whl"))
    if not wheels:
        raise LiveHAError("No servents-data-model wheel was built")
    if len(wheels) > 1:
        raise LiveHAError(f"Expected one servents-data-model wheel, found {wheels}")
    return wheels[0]


def compute_container_user_site(args: argparse.Namespace) -> str:
    """Compute the Python user-site path Home Assistant checks in the container."""
    result = docker_run_rm(
        args,
        args.image,
        "sh",
        "-c",
        "python -m site --user-site",
    )
    user_site = result.stdout.strip()
    if not user_site.startswith("/"):
        raise LiveHAError(f"Unexpected Home Assistant user-site: {user_site}")
    return user_site


def preinstall_data_model(args: argparse.Namespace, wheel: Path) -> None:
    """Install the local data-model wheel into HA's mounted user-site."""
    user_site = compute_container_user_site(args)
    docker_run_rm(
        args,
        "-v",
        docker_volume(USER_SITE_DIR, user_site, args.volume_suffix),
        "-v",
        docker_volume(WHEELS_DIR, "/wheels", args.volume_suffix),
        args.image,
        "python",
        "-m",
        "uv",
        "pip",
        "install",
        "--quiet",
        "--target",
        user_site,
        f"/wheels/{wheel.name}",
    )


def create_auth_user(args: argparse.Namespace) -> None:
    """Create a Home Assistant auth provider user in the disposable config."""
    docker_run_rm(
        args,
        "-v",
        docker_volume(CONFIG_DIR, "/config", args.volume_suffix),
        args.image,
        "python",
        "-m",
        "homeassistant",
        "--script",
        "auth",
        "-c",
        "/config",
        "add",
        AUTH_USER,
        AUTH_PASSWORD,
    )


def start_home_assistant(args: argparse.Namespace, container_name: str) -> None:
    """Start the dedicated Home Assistant container."""
    run_command(
        [
            *docker_run_base(args),
            "run",
            "-d",
            "--name",
            container_name,
            "-v",
            docker_volume(CONFIG_DIR, "/config", args.volume_suffix),
            "-v",
            docker_volume(USER_SITE_DIR, compute_container_user_site(args), args.volume_suffix),
            "-p",
            "127.0.0.1::8123",
            args.image,
            "python",
            "-m",
            "homeassistant",
            "--config",
            "/config",
            "--log-no-color",
        ]
    )


def container_port(args: argparse.Namespace, container_name: str) -> int:
    """Return the random host port Docker assigned for HA."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = run_command(
            [*docker_run_base(args), "port", container_name, "8123/tcp"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            endpoint = result.stdout.strip().splitlines()[0]
            return int(endpoint.rsplit(":", 1)[1])
        time.sleep(0.25)
    raise LiveHAError("Home Assistant container did not publish port 8123")


def http_request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: float = 10,
) -> Any:
    """Send an HTTP request and return decoded JSON when present."""
    headers = {"Accept": "application/json"}
    body: bytes | None = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form_body is not None:
        body = urlencode(form_body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local disposable HA URL
            payload = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as err:
        payload = err.read()
        status = err.code
        content_type = err.headers.get("Content-Type", "")
    except (OSError, URLError) as err:
        raise LiveHAError(f"HTTP request failed for {method} {path}: {err}") from err

    if status not in expected:
        text = payload.decode(errors="replace")
        raise LiveHAError(f"Unexpected HTTP {status} for {method} {path}: {text}")
    if not payload:
        return None
    if "application/json" in content_type:
        return json.loads(payload)
    return payload.decode(errors="replace")


def wait_for_home_assistant(base_url: str, timeout_seconds: int) -> None:
    """Wait until Home Assistant's unauthenticated endpoints respond."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            http_request(base_url, "GET", "/manifest.json", expected=(200, 404))
            http_request(base_url, "GET", "/api/", expected=(200, 401))
            return
        except LiveHAError as err:
            last_error = err
            time.sleep(2)
    raise LiveHAError(f"Home Assistant did not become reachable: {last_error}")


def get_access_token(base_url: str) -> str:
    """Log in through HA's auth-code flow and return an access token."""
    step = http_request(
        base_url,
        "POST",
        "/auth/login_flow",
        json_body={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
        },
    )
    flow_id = step["flow_id"]
    result = http_request(
        base_url,
        "POST",
        f"/auth/login_flow/{flow_id}",
        json_body={
            "client_id": CLIENT_ID,
            "username": AUTH_USER,
            "password": AUTH_PASSWORD,
        },
    )
    if result.get("type") != "create_entry":
        raise LiveHAError(f"Unexpected auth flow result: {result}")

    token_data = http_request(
        base_url,
        "POST",
        "/auth/token",
        form_body={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": result["result"],
        },
    )
    return token_data["access_token"]


def create_servents_config_entry(base_url: str, token: str) -> None:
    """Create the ServEnts config entry through HA's config-flow API."""
    step = http_request(
        base_url,
        "POST",
        "/api/config/config_entries/flow",
        token=token,
        json_body={"handler": "servents"},
    )
    if step.get("type") == "create_entry":
        return
    if step.get("type") != "form":
        raise LiveHAError(f"Unexpected ServEnts config flow start: {step}")

    result = http_request(
        base_url,
        "POST",
        f"/api/config/config_entries/flow/{step['flow_id']}",
        token=token,
        json_body={},
    )
    if result.get("type") != "create_entry":
        raise LiveHAError(f"Unexpected ServEnts config flow result: {result}")


def call_service(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    payload: dict[str, Any],
) -> Any:
    """Call a Home Assistant service through the REST API."""
    return http_request(
        base_url,
        "POST",
        f"/api/services/{domain}/{service}",
        token=token,
        json_body=payload,
    )


def websocket_url(base_url: str) -> str:
    """Return HA's WebSocket API URL for a base HTTP URL."""
    if base_url.startswith("https://"):
        return f"wss://{base_url.removeprefix('https://')}/api/websocket"
    if base_url.startswith("http://"):
        return f"ws://{base_url.removeprefix('http://')}/api/websocket"
    raise LiveHAError(f"Unsupported Home Assistant base URL: {base_url}")


async def websocket_receive_json(ws, timeout: float) -> dict[str, Any]:
    """Receive one JSON WebSocket message from HA."""
    message = await ws.receive(timeout=timeout)
    if message.type is WSMsgType.TEXT:
        return json.loads(message.data)
    if message.type is WSMsgType.ERROR:
        raise LiveHAError(f"Home Assistant WebSocket failed: {ws.exception()}")
    raise LiveHAError(f"Unexpected Home Assistant WebSocket message: {message.type}")


async def async_call_service_and_wait_for_event(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    payload: dict[str, Any],
    event_type: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Subscribe to an HA event, call a service, and return the next event."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with ClientSession(headers=headers) as session:
        async with session.ws_connect(websocket_url(base_url)) as ws:
            auth_required = await websocket_receive_json(ws, timeout_seconds)
            if auth_required.get("type") != "auth_required":
                raise LiveHAError(f"Unexpected WebSocket auth start: {auth_required}")

            await ws.send_json({"type": "auth", "access_token": token})
            auth_result = await websocket_receive_json(ws, timeout_seconds)
            if auth_result.get("type") != "auth_ok":
                raise LiveHAError(f"Unexpected WebSocket auth result: {auth_result}")

            await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": event_type})
            subscribe_result = await websocket_receive_json(ws, timeout_seconds)
            if not subscribe_result.get("success"):
                raise LiveHAError(f"Event subscription failed: {subscribe_result}")

            async with session.post(f"{base_url}/api/services/{domain}/{service}", json=payload) as response:
                text = await response.text()
                if response.status != 200:
                    raise LiveHAError(f"Unexpected HTTP {response.status} for {domain}.{service}: {text}")

            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                event_message = await websocket_receive_json(ws, max(deadline - time.monotonic(), 0.1))
                if event_message.get("type") == "event":
                    return event_message["event"]

    raise LiveHAError(f"Timed out waiting for Home Assistant event {event_type!r}")


def call_service_and_wait_for_event(
    base_url: str,
    token: str,
    domain: str,
    service: str,
    payload: dict[str, Any],
    event_type: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Synchronously call a service and capture the next matching HA event."""
    return asyncio.run(
        async_call_service_and_wait_for_event(
            base_url,
            token,
            domain,
            service,
            payload,
            event_type,
            timeout_seconds,
        )
    )


def assert_event_data(event: dict[str, Any], expected_data: dict[str, Any]) -> None:
    """Assert a captured HA event has exactly the expected data payload."""
    data = event.get("data")
    if data != expected_data:
        raise LiveHAError(f"Unexpected event data. Expected {expected_data!r}, got {data!r}")


def find_servent_entity_state(base_url: str, token: str, servent_id: str) -> dict[str, Any] | None:
    """Find a live entity by the ServEnts routing attribute."""
    states = http_request(base_url, "GET", "/api/states", token=token)
    for state in states:
        attributes = state.get("attributes") or {}
        if attributes.get("servent_id") == servent_id:
            return state
    return None


def find_entity_state_by_entity_id(base_url: str, token: str, entity_id: str) -> dict[str, Any] | None:
    """Find a live entity by its HA entity_id."""
    states = http_request(base_url, "GET", "/api/states", token=token)
    for state in states:
        if state.get("entity_id") == entity_id:
            return state
    return None


def wait_for_live_entity(base_url: str, token: str, expected_state: str, timeout_seconds: int) -> dict[str, Any]:
    """Wait until the ServEnts sensor has the expected HA state."""
    return wait_for_servent_entity(base_url, token, SERVENT_ID, expected_state, timeout_seconds)


def wait_for_servent_entity(
    base_url: str,
    token: str,
    servent_id: str,
    expected_state: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Wait until a ServEnt entity has the expected HA state."""
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = find_servent_entity_state(base_url, token, servent_id)
        if last_state is not None and last_state.get("state") == expected_state:
            return last_state
        time.sleep(1)
    raise LiveHAError(f"ServEnt entity {servent_id} did not reach state {expected_state!r}; last state was {last_state}")


def wait_for_servent_attributes(
    base_url: str,
    token: str,
    servent_id: str,
    expected_attributes: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Wait until a ServEnt entity has the expected attribute subset."""
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = find_servent_entity_state(base_url, token, servent_id)
        attributes = (last_state or {}).get("attributes") or {}
        if all(attributes.get(key) == value for key, value in expected_attributes.items()):
            return last_state
        time.sleep(1)
    raise LiveHAError(
        f"ServEnt entity {servent_id} did not get attributes {expected_attributes!r}; last state was {last_state}"
    )


def wait_for_entity_id_state(
    base_url: str,
    token: str,
    entity_id: str,
    expected_state: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Wait until a known HA entity_id has the expected state."""
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = find_entity_state_by_entity_id(base_url, token, entity_id)
        if last_state is not None and last_state.get("state") == expected_state:
            return last_state
        time.sleep(1)
    raise LiveHAError(f"Entity {entity_id} did not reach state {expected_state!r}; last state was {last_state}")


def wait_for_entity_absent(base_url: str, token: str, entity_id: str, timeout_seconds: int) -> None:
    """Wait until a known HA entity_id disappears from the state machine."""
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = find_entity_state_by_entity_id(base_url, token, entity_id)
        if last_state is None:
            return
        time.sleep(1)
    raise LiveHAError(f"Entity {entity_id} was not removed; last state was {last_state}")


def run_smoke(base_url: str, token: str) -> str:
    """Exercise config entry setup and existing sensor create/update path."""
    create_servents_config_entry(base_url, token)

    call_service(
        base_url,
        token,
        "servents",
        "create_entity",
        {
            "entities": [
                {
                    "entity_type": "sensor",
                    "servent_id": SERVENT_ID,
                    "name": "Live HA Temperature",
                    "default_state": 0,
                    "fixed_attributes": {"phase": "0"},
                    "device_definition": {
                        "device_id": "live-ha-device",
                        "name": "Live HA Device",
                        "manufacturer": "ServEnts",
                        "model": "Live Harness",
                        "version": "0",
                    },
                }
            ]
        },
    )
    state = wait_for_live_entity(base_url, token, "0", 30)
    entity_id = state["entity_id"]

    call_service(
        base_url,
        token,
        "servents",
        "update_state",
        {
            "servent_id": SERVENT_ID,
            "state": 21.5,
            "attributes": {"source": "live-ha"},
        },
    )
    state = wait_for_live_entity(base_url, token, "21.5", 30)
    attributes = state.get("attributes") or {}
    if attributes.get("source") != "live-ha" or attributes.get("phase") != "0":
        raise LiveHAError(f"Live entity attributes were not preserved: {attributes}")

    call_service(
        base_url,
        token,
        "servents",
        "update_state",
        {
            "servent_id": SERVENT_ID,
            "available": False,
        },
    )
    wait_for_entity_id_state(base_url, token, entity_id, "unavailable", 30)

    call_service(
        base_url,
        token,
        "servents",
        "update_state",
        {
            "servent_id": SERVENT_ID,
            "available": True,
        },
    )
    state = wait_for_entity_id_state(base_url, token, entity_id, "21.5", 30)
    if (state.get("attributes") or {}).get("source") != "live-ha":
        raise LiveHAError(f"Availability restore clobbered attributes: {state}")

    call_service(
        base_url,
        token,
        "servents",
        "update_state",
        {
            "servent_id": SERVENT_ID,
            "attributes": {"source": "attribute-only", "phase2": "attrs"},
        },
    )
    state = wait_for_entity_id_state(base_url, token, entity_id, "21.5", 30)
    attributes = state.get("attributes") or {}
    if attributes.get("source") != "attribute-only" or attributes.get("phase2") != "attrs":
        raise LiveHAError(f"Attribute-only update failed: {attributes}")

    call_service(
        base_url,
        token,
        "servents",
        "update_state",
        {
            "servent_id": SERVENT_ID,
            "state": 22.5,
            "attributes": {"merged": "yes"},
            "available": True,
            "merge_attributes": True,
        },
    )
    state = wait_for_entity_id_state(base_url, token, entity_id, "22.5", 30)
    attributes = state.get("attributes") or {}
    if attributes.get("source") != "attribute-only" or attributes.get("merged") != "yes":
        raise LiveHAError(f"Merge-attribute update failed: {attributes}")

    call_service(
        base_url,
        token,
        "servents",
        "remove_entity",
        {
            "servent_id": SERVENT_ID,
        },
    )
    wait_for_entity_absent(base_url, token, entity_id, 30)

    call_service(
        base_url,
        token,
        "servents",
        "create_entity",
        {
            "entities": [
                {
                    "entity_type": "sensor",
                    "servent_id": SERVENT_ID,
                    "name": "Live HA Temperature",
                    "default_state": 30,
                    "restore_state": False,
                    "fixed_attributes": {"phase": "3"},
                    "device_definition": {
                        "device_id": "live-ha-device",
                        "name": "Live HA Device",
                        "manufacturer": "ServEnts",
                        "model": "Live Harness",
                        "version": "0",
                    },
                }
            ]
        },
    )
    recreated = wait_for_live_entity(base_url, token, "30", 30)
    recreated_attributes = recreated.get("attributes") or {}
    if recreated_attributes.get("phase") != "3":
        raise LiveHAError(f"Removed entity did not recreate cleanly: {recreated}")

    call_service(
        base_url,
        token,
        "servents",
        "create_entity",
        {
            "entities": [
                {
                    "entity_type": "text",
                    "servent_id": TEXT_SERVENT_ID,
                    "name": "Live HA Text",
                    "default_state": "hello",
                    "min_length": 1,
                    "max_length": 20,
                    "mode": "text",
                    "fixed_attributes": {"phase": "4"},
                },
                {
                    "entity_type": "date",
                    "servent_id": DATE_SERVENT_ID,
                    "name": "Live HA Date",
                    "default_state": "2026-07-05",
                    "fixed_attributes": {"phase": "4"},
                },
                {
                    "entity_type": "time",
                    "servent_id": TIME_SERVENT_ID,
                    "name": "Live HA Time",
                    "default_state": "12:30:15",
                    "fixed_attributes": {"phase": "4"},
                },
                {
                    "entity_type": "date_time",
                    "servent_id": DATETIME_SERVENT_ID,
                    "name": "Live HA Datetime",
                    "default_state": "2026-07-05T12:30:15+00:00",
                    "fixed_attributes": {"phase": "4"},
                },
                {
                    "entity_type": "event",
                    "servent_id": EVENT_SERVENT_ID,
                    "name": "Live HA Event",
                    "event_types": ["pressed", "held"],
                    "device_class": "button",
                    "fixed_attributes": {"phase": "4"},
                },
            ]
        },
    )
    text_state = wait_for_servent_entity(base_url, token, TEXT_SERVENT_ID, "hello", 30)
    date_state = wait_for_servent_entity(base_url, token, DATE_SERVENT_ID, "2026-07-05", 30)
    time_state = wait_for_servent_entity(base_url, token, TIME_SERVENT_ID, "12:30:15", 30)
    datetime_state = wait_for_servent_entity(
        base_url,
        token,
        DATETIME_SERVENT_ID,
        "2026-07-05T12:30:15+00:00",
        30,
    )
    event_state = find_servent_entity_state(base_url, token, EVENT_SERVENT_ID)
    if event_state is None:
        raise LiveHAError("Event entity was not created")

    call_service(base_url, token, "text", "set_value", {"entity_id": text_state["entity_id"], "value": "world"})
    wait_for_servent_entity(base_url, token, TEXT_SERVENT_ID, "world", 30)

    call_service(base_url, token, "date", "set_value", {"entity_id": date_state["entity_id"], "date": "2026-07-06"})
    wait_for_servent_entity(base_url, token, DATE_SERVENT_ID, "2026-07-06", 30)

    call_service(base_url, token, "time", "set_value", {"entity_id": time_state["entity_id"], "time": "13:45:00"})
    wait_for_servent_entity(base_url, token, TIME_SERVENT_ID, "13:45:00", 30)

    call_service(
        base_url,
        token,
        "datetime",
        "set_value",
        {"entity_id": datetime_state["entity_id"], "datetime": "2026-07-06T13:45:00+00:00"},
    )
    wait_for_servent_entity(base_url, token, DATETIME_SERVENT_ID, "2026-07-06T13:45:00+00:00", 30)

    call_service(
        base_url,
        token,
        "servents",
        "trigger_event",
        {
            "servent_id": EVENT_SERVENT_ID,
            "event_type": "pressed",
            "attributes": {"confidence": 0.93},
        },
    )
    wait_for_servent_attributes(
        base_url,
        token,
        EVENT_SERVENT_ID,
        {"event_type": "pressed", "confidence": 0.93},
        30,
    )

    call_service(
        base_url,
        token,
        "servents",
        "create_entity",
        {
            "entities": [
                {
                    "entity_type": "light",
                    "servent_id": LIGHT_SERVENT_ID,
                    "name": "Live HA Light",
                    "default_state": {"state": False, "brightness": 25},
                    "supports_brightness": True,
                    "optimistic": True,
                    "fixed_attributes": {"phase": "6"},
                },
                {
                    "entity_type": "cover",
                    "servent_id": COVER_SERVENT_ID,
                    "name": "Live HA Cover",
                    "default_state": {"state": "closed", "position": 0},
                    "supports_position": True,
                    "supports_stop": True,
                    "optimistic": True,
                    "fixed_attributes": {"phase": "6"},
                },
                {
                    "entity_type": "fan",
                    "servent_id": FAN_SERVENT_ID,
                    "name": "Live HA Fan",
                    "default_state": {"state": False},
                    "supports_percentage": True,
                    "preset_modes": ["auto", "boost"],
                    "optimistic": True,
                    "fixed_attributes": {"phase": "6"},
                },
            ]
        },
    )
    light_state = wait_for_servent_entity(base_url, token, LIGHT_SERVENT_ID, "off", 30)
    cover_state = wait_for_servent_entity(base_url, token, COVER_SERVENT_ID, "closed", 30)
    fan_state = wait_for_servent_entity(base_url, token, FAN_SERVENT_ID, "off", 30)

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "light",
        "turn_on",
        {"entity_id": light_state["entity_id"], "brightness": 180},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": LIGHT_SERVENT_ID,
            "entity_type": "light",
            "command": {"state": True, "brightness": 180},
        },
    )
    light_state = wait_for_servent_entity(base_url, token, LIGHT_SERVENT_ID, "on", 30)
    if (light_state.get("attributes") or {}).get("brightness") != 180:
        raise LiveHAError(f"Light optimistic brightness was not applied: {light_state}")

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "cover",
        "open_cover",
        {"entity_id": cover_state["entity_id"]},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": COVER_SERVENT_ID,
            "entity_type": "cover",
            "command": {"action": "open"},
        },
    )
    wait_for_servent_entity(base_url, token, COVER_SERVENT_ID, "opening", 30)

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "fan",
        "set_percentage",
        {"entity_id": fan_state["entity_id"], "percentage": 55},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": FAN_SERVENT_ID,
            "entity_type": "fan",
            "command": {"percentage": 55},
        },
    )
    fan_state = wait_for_servent_entity(base_url, token, FAN_SERVENT_ID, "on", 30)
    if (fan_state.get("attributes") or {}).get("percentage") != 55:
        raise LiveHAError(f"Fan optimistic percentage was not applied: {fan_state}")

    call_service(
        base_url,
        token,
        "servents",
        "create_entity",
        {
            "entities": [
                {
                    "entity_type": "climate",
                    "servent_id": CLIMATE_SERVENT_ID,
                    "name": "Live HA Climate",
                    "default_state": "off",
                    "hvac_modes": ["off", "heat"],
                    "supports_target_temperature": True,
                    "supports_target_temperature_range": False,
                    "min_temp": 15,
                    "max_temp": 25,
                    "temp_step": 0.5,
                    "fan_modes": ["auto", "high"],
                    "preset_modes": ["eco", "boost"],
                    "swing_modes": ["off", "on"],
                    "temperature_unit": "C",
                    "optimistic": True,
                    "fixed_attributes": {"phase": "7"},
                },
                {
                    "entity_type": "climate",
                    "servent_id": CLIMATE_RANGE_SERVENT_ID,
                    "name": "Live HA Climate Range",
                    "default_state": {
                        "hvac_mode": "heat_cool",
                        "target_temp_low": 19,
                        "target_temp_high": 24,
                    },
                    "hvac_modes": ["off", "heat_cool"],
                    "supports_target_temperature": False,
                    "supports_target_temperature_range": True,
                    "min_temp": 15,
                    "max_temp": 30,
                    "temp_step": 0.5,
                    "temperature_unit": "C",
                    "optimistic": True,
                    "fixed_attributes": {"phase": "7"},
                },
            ]
        },
    )
    climate_state = wait_for_servent_entity(base_url, token, CLIMATE_SERVENT_ID, "off", 30)
    climate_range_state = wait_for_servent_entity(
        base_url,
        token,
        CLIMATE_RANGE_SERVENT_ID,
        "heat_cool",
        30,
    )

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "climate",
        "set_hvac_mode",
        {"entity_id": climate_state["entity_id"], "hvac_mode": "heat"},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": CLIMATE_SERVENT_ID,
            "entity_type": "climate",
            "command": {"hvac_mode": "heat"},
        },
    )
    wait_for_servent_entity(base_url, token, CLIMATE_SERVENT_ID, "heat", 30)

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "climate",
        "set_temperature",
        {"entity_id": climate_state["entity_id"], "temperature": 22.5},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": CLIMATE_SERVENT_ID,
            "entity_type": "climate",
            "command": {"target_temperature": 22.5},
        },
    )
    wait_for_servent_attributes(base_url, token, CLIMATE_SERVENT_ID, {"temperature": 22.5}, 30)

    event = call_service_and_wait_for_event(
        base_url,
        token,
        "climate",
        "set_temperature",
        {"entity_id": climate_range_state["entity_id"], "target_temp_low": 20, "target_temp_high": 26},
        "servent.entity_command",
        30,
    )
    assert_event_data(
        event,
        {
            "servent_id": CLIMATE_RANGE_SERVENT_ID,
            "entity_type": "climate",
            "command": {"target_temp_low": 20.0, "target_temp_high": 26.0},
        },
    )
    wait_for_servent_attributes(
        base_url,
        token,
        CLIMATE_RANGE_SERVENT_ID,
        {"target_temp_low": 20.0, "target_temp_high": 26.0},
        30,
    )

    config = http_request(base_url, "GET", "/api/config", token=token)
    return str(config.get("version", "unknown"))


def print_container_logs(args: argparse.Namespace, container_name: str) -> None:
    """Print HA container logs to stderr."""
    result = run_command(
        [*docker_run_base(args), "logs", container_name],
        check=False,
    )
    print("\n--- Home Assistant container logs ---", file=sys.stderr)
    print(result.stdout, file=sys.stderr)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


def stop_container(args: argparse.Namespace, container_name: str) -> None:
    """Stop and remove the HA container."""
    run_command([*docker_run_base(args), "rm", "-f", container_name], check=False)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="homeassistant/home-assistant:stable")
    parser.add_argument("--docker-bin", default=os.environ.get("DOCKER", "docker"))
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--keep-container", action="store_true")
    parser.add_argument(
        "--volume-suffix",
        default=os.environ.get("SERVENTS_DOCKER_VOLUME_SUFFIX", ""),
        help="Optional Docker bind mount suffix, for example 'z' on SELinux hosts.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the live Home Assistant smoke test."""
    args = parse_args()
    container_name = f"servents-live-ha-{os.getpid()}-{secrets.token_hex(4)}"
    container_started = False

    try:
        run_command([*docker_run_base(args), "version"], capture=True)
        prepare_runtime(args)
        wheel = build_data_model_wheel()
        preinstall_data_model(args, wheel)
        create_auth_user(args)
        start_home_assistant(args, container_name)
        container_started = True
        port = container_port(args, container_name)
        base_url = f"http://127.0.0.1:{port}"
        wait_for_home_assistant(base_url, args.timeout)
        token = get_access_token(base_url)
        ha_version = run_smoke(base_url, token)
    except Exception as err:  # noqa: BLE001 - CLI should report and clean up
        if container_started:
            print_container_logs(args, container_name)
        print(f"Live Home Assistant validation failed: {err}", file=sys.stderr)
        return 1
    finally:
        if container_started and not args.keep_container:
            stop_container(args, container_name)
        elif container_started:
            print(f"Keeping Home Assistant container {container_name}", file=sys.stderr)
        if not args.keep_container:
            remove_runtime_tree(args)

    print(f"Live Home Assistant validation passed against HA {ha_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
