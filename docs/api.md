# Local HTTP API

The API is deliberately semantic. It does not expose arbitrary IOCtrl IDs or payloads.

Default base URL: `http://127.0.0.1:8787`

If `VTECH_API_TOKEN` is set, send `Authorization: Bearer <token>`.

## Health and state

```http
GET /health
GET /api/v1/cameras
GET /api/v1/cameras/cam1/state
```

Representative state fields:

```json
{
  "camera_id": "cam1",
  "online": true,
  "runtime_alive": true,
  "session_state": "connected",
  "temperature_c": 22.5,
  "humidity_percent": 47,
  "last_rx_ms": 1789580000000,
  "last_video_ms": 1789580000000,
  "last_audio_ms": 1789580000000,
  "last_motion_ms": 1789580000000,
  "last_sound_ms": 1789580000000,
  "last_temperature_alert_ms": 1789580000000
}
```

Timestamps are Unix epoch milliseconds. Missing observations are `null`/zero depending on the native writer version.

## PTZ

```http
POST /api/v1/cameras/cam1/ptz
Content-Type: application/json

{"direction":"left"}
```

Directions: `up`, `down`, `left`, `right`.

## Night light

Apply preset and brightness:

```json
{"enabled":true,"preset":"blue","brightness":57}
```

Custom RGB:

```json
{"rgb":[128,0,128]}
```

Turn off:

```json
{"enabled":false}
```

The OFF operation uses the validated `0x07C8` power contract (`enabled=0`) and keeps a valid brightness byte. If no brightness is supplied, the API uses the captured value `98`.

Timer:

```http
POST /api/v1/cameras/cam1/light/timer

{"seconds":900}
```

Allowed timer values: `0`, `900`, `1800`, `3600`.

## Lullaby

Track/stop:

```http
POST /api/v1/cameras/cam1/lullaby

{"track":3}
```

Tracks are `0..10`; `-1` means stop.

Volume/timer:

```http
POST /api/v1/cameras/cam1/lullaby/params

{"volume":3,"timer_seconds":1800}
```

Allowed volumes: `1`, `3`, `5`.

## Native symbolic grammar

The Python side maps requests to a bounded grammar over the per-camera Unix datagram socket:

```text
PING
PTZ UP|DOWN|LEFT|RIGHT
LIGHT POWER <0|1> <12|57|98>
LIGHT PRESET <validated-code>
LIGHT RGB <r> <g> <b>
LIGHT_TIMER <0|900|1800|3600>
LULLABY_TRACK <-1..10>
LULLABY_PARAMS <1|3|5> <0|900|1800|3600>
```

A request may contain at most two semicolon-separated operations, used for combinations such as preset plus brightness.
