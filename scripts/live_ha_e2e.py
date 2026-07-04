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


ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = ROOT / ".tmp" / "live-ha"
CONFIG_DIR = LIVE_ROOT / "config"
WHEELS_DIR = LIVE_ROOT / "wheels"
USER_SITE_DIR = LIVE_ROOT / "user-site"
COMPONENT_SRC = ROOT / "custom_components" / "servents"
COMPONENT_DST = CONFIG_DIR / "custom_components" / "servents"
DATA_MODEL_DIR = ROOT / "servents-data-model"
SERVENT_ID = "live-ha-temperature"
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


def find_live_entity_state(base_url: str, token: str) -> dict[str, Any] | None:
    """Find the live sensor by the ServEnts routing attribute."""
    states = http_request(base_url, "GET", "/api/states", token=token)
    for state in states:
        attributes = state.get("attributes") or {}
        if attributes.get("servent_id") == SERVENT_ID:
            return state
    return None


def wait_for_live_entity(base_url: str, token: str, expected_state: str, timeout_seconds: int) -> dict[str, Any]:
    """Wait until the ServEnts sensor has the expected HA state."""
    deadline = time.monotonic() + timeout_seconds
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_state = find_live_entity_state(base_url, token)
        if last_state is not None and last_state.get("state") == expected_state:
            return last_state
        time.sleep(1)
    raise LiveHAError(f"Live entity did not reach state {expected_state!r}; last state was {last_state}")


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
    wait_for_live_entity(base_url, token, "0", 30)

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
