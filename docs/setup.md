# Setup and native integration

## Prerequisites

The open portion of this repository assumes you already have a working native process that can authenticate to your own LF925 camera and receive/send the VTech application-layer IOCtrl traffic over its TUTK/Kalay session.

Typical host requirements:

- Linux
- Python 3.10+
- go2rtc
- FFmpeg
- C compiler and pthreads for the reference native shim/tests
- your own legitimately obtained vendor runtime/SDK pieces and camera pairing/authentication material

No vendor binary, APK, account credential, pairing secret, or license key is included here.

## 1. Bring up one native camera session

First prove a single camera can remain authenticated and continuously deliver decrypted Annex-B H.264. Do not add the HTTP API or kiosk until the native media session is stable.

The native process should call the shim with a callback that sends one IOCtrl on the already-authenticated session:

```c
int send_ioctl(void *opaque, uint32_t type,
               const uint8_t *payload, size_t len);
```

Then initialize the shim:

```c
vtech_runtime rt;
vtech_runtime_init(&rt, "cam1", "/run/vtech", send_ioctl, session_ptr);
vtech_runtime_start(&rt);
```

Feed received IOCtrl frames into:

```c
vtech_runtime_handle_rx(&rt, received_type, payload, payload_len);
```

When media arrives, update freshness timestamps:

```c
vtech_runtime_note_video(&rt);
vtech_runtime_note_audio(&rt);
```

On session state changes:

```c
vtech_runtime_set_session(&rt, 1, "connected");
```

On shutdown:

```c
vtech_runtime_stop(&rt);
```

## 2. Publish video and receive audio

Feed native H.264 stdout directly into go2rtc. Feed PCMA receive audio to an audio-only FFmpeg process and push that audio into the corresponding go2rtc stream.

Do not blindly copy an audio delay from another host. The reference setup used about `1500 ms`; measure and tune your own synchronization.

## 3. Start the typed API

```bash
VTECH_CAMERAS=cam1 \
VTECH_RUNTIME_DIR=/run/vtech \
VTECH_API_BIND=127.0.0.1 \
VTECH_API_PORT=8787 \
python3 bridge_api/vtech_api.py
```

Check:

```bash
curl http://127.0.0.1:8787/health
curl http://127.0.0.1:8787/api/v1/cameras
```

For two cameras set `VTECH_CAMERAS=cam1,cam2` and create the corresponding native socket/state files.

## 4. Start the kiosk

```bash
VTECH_API_URL=http://127.0.0.1:8787 \
VTECH_KIOSK_BIND=0.0.0.0 \
VTECH_KIOSK_PORT=8790 \
python3 kiosk/vtech_kiosk_v3.py
```

Override `VTECH_CAM1_GO2RTC_PORT`, `VTECH_CAM2_GO2RTC_PORT`, `VTECH_CAM1_STREAM`, and `VTECH_CAM2_STREAM` if your go2rtc layout differs.

## 5. Optional API token

If the API is exposed beyond loopback, configure the same bearer token on the API and kiosk:

```bash
export VTECH_API_TOKEN='use-a-long-random-value'
```

## Validation checklist

Confirm each item independently:

1. native session remains authenticated
2. H.264 timestamps advance continuously
3. receive audio remains low-latency
4. `PING` over the Unix socket returns `OK`
5. state JSON updates atomically
6. PTZ works in all four directions
7. light on/off, brightness, preset/RGB and timer work
8. lullaby start/stop, volume and timer work
9. temperature/humidity update
10. motion, sound/baby and temperature-alert timestamps update
11. browser shows a visible warning if a stream becomes stale
