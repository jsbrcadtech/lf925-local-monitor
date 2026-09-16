#!/usr/bin/env python3
"""Typed local HTTP API for the LF925 native bridge.

This sidecar never opens a TUTK/Kalay session. The native bridge owns the
camera session and exposes a per-camera AF_UNIX datagram command socket plus an
atomic JSON state snapshot under ``VTECH_RUNTIME_DIR``.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

API_VERSION = 1
DEFAULT_RUNTIME_DIR = "/run/vtech"
DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8787
MAX_BODY = 16 * 1024
CAMERA_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

PTZ_DIRECTIONS = {"up", "down", "left", "right"}
LIGHT_PRESETS = {
    "orange": 0x01,
    "beige": 0x02,
    "yellow": 0x03,
    "green": 0x04,
    "blue": 0x05,
    "purple": 0x06,
    "white": 0x07,
    "rainbow": 0x10,
    "rainbow_red": 0x11,
    "rainbow_blue": 0x12,
}
LIGHT_BRIGHTNESS_VALUES = {12, 57, 98}
TIMER_VALUES = {0, 900, 1800, 3600}
LULLABY_TRACK_VALUES = set(range(11)) | {-1}
LULLABY_VOLUME_VALUES = {1, 3, 5}

CAPABILITIES = {
    "video": True,
    "receive_audio": True,
    "ptz": ["up", "down", "left", "right"],
    "night_light": {
        "power": True,
        "brightness_values": sorted(LIGHT_BRIGHTNESS_VALUES),
        "rgb": True,
        "presets": list(LIGHT_PRESETS),
        "timer_seconds": sorted(TIMER_VALUES),
    },
    "lullaby": {
        "tracks": sorted(LULLABY_TRACK_VALUES),
        "volume_values": sorted(LULLABY_VOLUME_VALUES),
        "timer_seconds": sorted(TIMER_VALUES),
    },
    "temperature": True,
    "humidity": True,
    "events": {
        "motion": True,
        "sound_baby": True,
        "temperature_alert": True,
    },
    "talkback": False,
}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _int(value: Any, name: str, *, minimum: int | None = None,
         maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be an integer")
    if minimum is not None and value < minimum:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be <= {maximum}")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be boolean")
    return value


def _one_of(value: Any, name: str, allowed: set[int] | set[str]) -> Any:
    if value not in allowed:
        raise ApiError(HTTPStatus.BAD_REQUEST,
                       f"{name} must be one of {sorted(allowed)}")
    return value


def _rgb(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3:
        raise ApiError(HTTPStatus.BAD_REQUEST, "rgb must be [r, g, b]")
    r, g, b = (_int(v, "rgb component", minimum=0, maximum=255)
               for v in value)
    return r, g, b


class BridgeRuntime:
    def __init__(self, runtime_dir: str, cameras: list[str], timeout: float = 3.0):
        self.runtime_dir = Path(runtime_dir)
        self.timeout = timeout
        self.cameras = cameras
        for camera in cameras:
            if not CAMERA_RE.fullmatch(camera):
                raise ValueError(f"invalid camera alias: {camera!r}")

    def require_camera(self, camera: str) -> None:
        if camera not in self.cameras:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown camera")

    def socket_path(self, camera: str) -> Path:
        self.require_camera(camera)
        return self.runtime_dir / f"{camera}.sock"

    def state_path(self, camera: str) -> Path:
        self.require_camera(camera)
        return self.runtime_dir / f"{camera}.state.json"

    def command(self, camera: str, line: str) -> str:
        """Send one bounded symbolic command to native and wait for its ACK."""
        self.require_camera(camera)
        server_path = self.socket_path(camera)
        if not server_path.exists():
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE,
                           "native bridge command socket unavailable")

        client_addr = (
            "\0vtech-api-"
            f"{os.getpid()}-{threading.get_ident()}-{secrets.token_hex(8)}"
        )
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.bind(client_addr)
            sock.settimeout(self.timeout)
            sock.sendto(line.encode("ascii"), str(server_path))
            try:
                reply = sock.recv(512).decode("utf-8", "replace").strip()
            except socket.timeout as exc:
                raise ApiError(HTTPStatus.GATEWAY_TIMEOUT,
                               "native bridge command ACK timeout") from exc
        except OSError as exc:
            raise ApiError(
                HTTPStatus.SERVICE_UNAVAILABLE,
                f"native bridge command failed: {exc.strerror or exc}",
            ) from exc
        finally:
            sock.close()

        if reply == "OK" or reply.startswith("OK "):
            return reply
        if reply.startswith("ERR "):
            raise ApiError(HTTPStatus.BAD_GATEWAY,
                           reply[4:] or "native bridge rejected command")
        raise ApiError(HTTPStatus.BAD_GATEWAY, "invalid native bridge ACK")

    def runtime_alive(self, camera: str) -> bool:
        try:
            self.command(camera, "PING")
            return True
        except ApiError:
            return False

    def read_state(self, camera: str) -> dict[str, Any]:
        self.require_camera(camera)
        fallback: dict[str, Any] = {
            "schema_version": 1,
            "camera_id": camera,
            "online": False,
            "session_state": "unavailable",
            "temperature_c": None,
            "humidity_percent": None,
            "updated_ms": None,
            "last_rx_ms": None,
            "last_video_ms": None,
            "last_audio_ms": None,
            "last_motion_ms": None,
            "last_sound_ms": None,
            "last_temperature_alert_ms": None,
        }
        try:
            state = json.loads(self.state_path(camera).read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            state = fallback.copy()
        if not isinstance(state, dict):
            state = fallback.copy()

        for key, value in fallback.items():
            state.setdefault(key, value)
        state["camera_id"] = camera
        alive = self.runtime_alive(camera)
        state["runtime_alive"] = alive
        if not alive:
            state["online"] = False
            state["session_state"] = "unavailable"
        state["capabilities"] = CAPABILITIES
        return state


def build_command(action: str, body: dict[str, Any]) -> str:
    if action == "ptz":
        direction = body.get("direction")
        if not isinstance(direction, str):
            raise ApiError(HTTPStatus.BAD_REQUEST, "direction must be a string")
        direction = direction.lower()
        _one_of(direction, "direction", PTZ_DIRECTIONS)
        return f"PTZ {direction.upper()}"

    if action == "light":
        allowed = {"enabled", "brightness", "rgb", "preset"}
        unknown = set(body) - allowed
        if unknown:
            raise ApiError(HTTPStatus.BAD_REQUEST,
                           f"unsupported light fields: {sorted(unknown)}")
        if "rgb" in body and "preset" in body:
            raise ApiError(HTTPStatus.BAD_REQUEST, "use rgb or preset, not both")

        enabled = None
        if "enabled" in body:
            enabled = _bool(body["enabled"], "enabled")

        brightness = None
        if "brightness" in body:
            brightness = _int(body["brightness"], "brightness")
            _one_of(brightness, "brightness", LIGHT_BRIGHTNESS_VALUES)

        if enabled is False:
            if "rgb" in body or "preset" in body:
                raise ApiError(HTTPStatus.BAD_REQUEST,
                               "enabled=false cannot include rgb or preset")
            return f"LIGHT POWER 0 {brightness if brightness is not None else 98}"

        commands: list[str] = []
        if "rgb" in body:
            r, g, b = _rgb(body["rgb"])
            commands.append(f"LIGHT RGB {r} {g} {b}")
        elif "preset" in body:
            preset = body["preset"]
            if not isinstance(preset, str) or preset not in LIGHT_PRESETS:
                raise ApiError(HTTPStatus.BAD_REQUEST,
                               f"preset must be one of {list(LIGHT_PRESETS)}")
            commands.append(f"LIGHT PRESET {LIGHT_PRESETS[preset]}")

        if brightness is not None:
            commands.append(f"LIGHT POWER 1 {brightness}")
        elif enabled is True and not commands:
            commands.append("LIGHT POWER 1 98")

        if not commands:
            raise ApiError(HTTPStatus.BAD_REQUEST, "no light operation supplied")
        return " ; ".join(commands)

    if action == "light_timer":
        seconds = _int(body.get("seconds"), "seconds")
        _one_of(seconds, "seconds", TIMER_VALUES)
        return f"LIGHT_TIMER {seconds}"

    if action == "lullaby":
        track = _int(body.get("track"), "track")
        _one_of(track, "track", LULLABY_TRACK_VALUES)
        return f"LULLABY_TRACK {track}"

    if action == "lullaby_params":
        volume = _int(body.get("volume"), "volume")
        timer_seconds = _int(body.get("timer_seconds"), "timer_seconds")
        _one_of(volume, "volume", LULLABY_VOLUME_VALUES)
        _one_of(timer_seconds, "timer_seconds", TIMER_VALUES)
        return f"LULLABY_PARAMS {volume} {timer_seconds}"

    raise ApiError(HTTPStatus.NOT_FOUND, "unknown action")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "LF925LocalAPI/1.0"

    @property
    def app(self) -> "ApiServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[lf925-api] {self.address_string()} {fmt % args}", flush=True)

    def _authorized(self) -> bool:
        token = self.app.api_token
        if not token:
            return True
        auth = self.headers.get("Authorization", "")
        return auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], token)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, err: ApiError) -> None:
        self._json(int(err.status), {"ok": False, "error": err.message})

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
        return False

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid Content-Length") from exc
        if length <= 0 or length > MAX_BODY:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid JSON body length")
        try:
            body = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid JSON") from exc
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
        return body

    @staticmethod
    def _camera_route(path: str) -> tuple[str, str | None] | None:
        parts = [p for p in path.split("?")[0].split("/") if p]
        if len(parts) < 4 or parts[:3] != ["api", "v1", "cameras"]:
            return None
        return parts[3], "/".join(parts[4:]) if len(parts) > 4 else None

    def do_GET(self) -> None:
        if not self._require_auth():
            return
        try:
            path = self.path.split("?")[0]
            if path == "/health":
                self._json(HTTPStatus.OK, {"ok": True, "api_version": API_VERSION})
                return
            if path == "/api/v1/cameras":
                states = [self.app.runtime.read_state(cam)
                          for cam in self.app.runtime.cameras]
                self._json(HTTPStatus.OK, {"ok": True, "cameras": states})
                return
            route = self._camera_route(self.path)
            if route:
                camera, action = route
                if action in (None, "state"):
                    self._json(HTTPStatus.OK,
                               {"ok": True,
                                "state": self.app.runtime.read_state(camera)})
                    return
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")
        except ApiError as err:
            self._error(err)

    def do_POST(self) -> None:
        if not self._require_auth():
            return
        try:
            route = self._camera_route(self.path)
            if not route:
                raise ApiError(HTTPStatus.NOT_FOUND, "not found")
            camera, action = route
            action_map = {
                "ptz": "ptz",
                "light": "light",
                "light/timer": "light_timer",
                "lullaby": "lullaby",
                "lullaby/params": "lullaby_params",
            }
            if action not in action_map:
                raise ApiError(HTTPStatus.NOT_FOUND, "not found")
            command = build_command(action_map[action], self._body())
            ack = self.app.runtime.command(camera, command)
            self._json(HTTPStatus.OK,
                       {"ok": True, "camera_id": camera, "ack": ack})
        except ApiError as err:
            self._error(err)


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], runtime: BridgeRuntime,
                 api_token: str | None):
        super().__init__(address, ApiHandler)
        self.runtime = runtime
        self.api_token = api_token


def main() -> None:
    bind = os.getenv("VTECH_API_BIND", DEFAULT_BIND)
    port = int(os.getenv("VTECH_API_PORT", str(DEFAULT_PORT)))
    runtime_dir = os.getenv("VTECH_RUNTIME_DIR", DEFAULT_RUNTIME_DIR)
    cameras = [c.strip() for c in os.getenv("VTECH_CAMERAS", "cam1").split(",")
               if c.strip()]
    if not cameras:
        raise SystemExit("VTECH_CAMERAS contains no camera aliases")
    runtime = BridgeRuntime(runtime_dir, cameras)
    server = ApiServer((bind, port), runtime, os.getenv("VTECH_API_TOKEN") or None)
    print(f"[lf925-api] listening on http://{bind}:{port} cameras={','.join(cameras)}",
          flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
