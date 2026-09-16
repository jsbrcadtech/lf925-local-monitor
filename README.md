# LF925 Local Monitor

Local integration layer for the **VTech / LeapFrog LF925-2HD** baby monitor. The project keeps the camera session local and exposes video, receive audio, telemetry, events, and a small typed control API without redistributing the official app, pairing secrets, or proprietary vendor SDK binaries.

> **Project status:** stable reference implementation / maintenance. The protocol details in this repository were validated against an LF925-2HD two-camera setup. Other VTech/LeapFrog models may differ.

## What works

- one authenticated TUTK/Kalay session per camera
- decrypted Annex-B H.264 video
- low-latency go2rtc RTSP/WebRTC publishing
- receive audio using a PCMA/Alaw audio-only FFmpeg sidecar
- two-camera CAM1 / BOTH / CAM2 viewing
- PTZ: up, down, left, right
- night-light preset/RGB, brightness, power, and timer
- lullaby track, volume, and timer
- temperature and humidity
- native motion, sound/baby, and temperature-alert timestamps
- local HTTP API on port `8787`
- browser kiosk on port `8790`

Talkback is intentionally not advertised as supported.

## Architecture

```text
Camera
  -> native TUTK/VTech session supplied by the user
       |- H.264 stdout -> go2rtc
       |- PCMA FIFO -> audio-only FFmpeg -> same go2rtc stream
       |- IOCtrl telemetry/events
       |- typed AF_UNIX command socket
       `- atomic JSON state snapshot

Local API       127.0.0.1:8787
Reference kiosk 0.0.0.0:8790
```

The native session remains the sole owner of the camera connection. The API and kiosk do **not** open extra TUTK sessions.

## Important boundary

This repository is the open integration layer around a locally supplied, already-authenticated native camera session. It does **not** contain:

- the official VTech/LeapFrog APK
- TUTK/ThroughTek libraries or SDK binaries
- device pairing credentials, license keys, tokens, or cloud account data
- a complete vendor-native transport implementation

You must provide your own legitimately obtained runtime pieces and pairing/authentication material. See [docs/setup.md](docs/setup.md).

## Repository layout

```text
bridge_api/                 typed HTTP API and native integration shim
kiosk/                      single-file local browser UI
patches/                    pinned go2rtc race workaround used for CAM2
docs/                       architecture, setup, API and protocol notes
tools/research/             optional static-analysis helpers
.github/workflows/ci.yml    syntax/unit/native compile checks
```

## Quick validation

```bash
python3 -m py_compile bridge_api/vtech_api.py kiosk/vtech_kiosk_v3.py
PYTHONPATH=bridge_api python3 -m unittest bridge_api/test_vtech_api.py
cc -std=c11 -Wall -Wextra -Wno-unused-function -pthread \
  -Ibridge_api/native bridge_api/native/test_vtech_control_runtime.c \
  -o /tmp/test_vtech_runtime
/tmp/test_vtech_runtime
```

## Start the API

```bash
VTECH_CAMERAS=cam1,cam2 \
VTECH_RUNTIME_DIR=/run/vtech \
VTECH_API_BIND=127.0.0.1 \
VTECH_API_PORT=8787 \
python3 bridge_api/vtech_api.py
```

Optional bearer authentication is enabled by setting `VTECH_API_TOKEN`.

## Start the kiosk

```bash
VTECH_API_URL=http://127.0.0.1:8787 \
VTECH_KIOSK_BIND=0.0.0.0 \
VTECH_KIOSK_PORT=8790 \
python3 kiosk/vtech_kiosk_v3.py
```

The reference topology expects CAM1 go2rtc on API port `1984` with stream `vtech_baby`, and CAM2 on `1985` with stream `vtech_baby_2`. All values are configurable by environment variables.

## Why audio is separate

A combined video+audio FFmpeg remux path produced large latency during testing. The stable topology keeps H.264 on the direct go2rtc path and feeds PCMA receive audio through a separate audio-only FFmpeg process into the same stream. The reference audio delay was about `1500 ms`; tune it for your environment.

## go2rtc CAM2 patch

The reference two-camera deployment exposed a producer lifecycle race in the tested go2rtc revision. The repository includes the minimal patch and the exact upstream commit it was based on under [`patches/`](patches/). Apply it only if you reproduce the same race; do not assume newer go2rtc versions need it.

## Security notes

Keep the API bound to loopback unless you have a reason to expose it. If you bind it beyond localhost, set `VTECH_API_TOKEN` and protect the host/LAN appropriately. Runtime socket/state files are intended to live under a mode-`0700` directory with mode-`0600` files.

The API intentionally exposes semantic commands only. There is no arbitrary IOCtrl endpoint.

## Documentation

- [Architecture](docs/architecture.md)
- [Setup and integration](docs/setup.md)
- [HTTP API](docs/api.md)
- [Validated protocol notes](docs/protocol.md)
- [Official Android app observations](docs/android-official-app.md)
- [Research workflow](docs/research-workflow.md)

## Licensing and affiliation

No project-wide open-source license has been selected yet. The go2rtc patch is derived from an MIT-licensed upstream project; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

This is an unofficial interoperability project and is not affiliated with or endorsed by VTech, LeapFrog, ThroughTek, or TUTK. Product and company names are used only to identify compatible systems.
