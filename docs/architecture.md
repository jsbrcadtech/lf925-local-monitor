# Architecture

## Design goals

The reference deployment keeps exactly one authenticated native TUTK/Kalay session open per camera. Media, typed control messages, telemetry and event reception all ride that existing session. Sidecars consume local IPC/state and never create their own camera connection.

## Media path

```text
native session
  |- decrypted Annex-B H.264 -> stdout -> go2rtc exec producer
  `- PCMA/Alaw receive audio -> FIFO -> audio-only FFmpeg -> RTSP push -> same go2rtc stream
```

A combined audio/video FFmpeg path was rejected because it introduced roughly 30-60+ seconds of latency in the tested setup. Keeping H.264 direct and audio separate preserved low video latency.

The tested audio path used an FFmpeg delay near `adelay=1500`; this is an environment-specific synchronization value, not a protocol constant.

## Reference go2rtc topology

| Camera | Stream | API | RTSP | WebRTC |
|---|---|---:|---:|---:|
| CAM1 | `vtech_baby` | 1984 | 8554 | 8555 |
| CAM2 | `vtech_baby_2` | 1985 | 8556 | 8557 |

CAM2 was isolated in a second go2rtc instance because the tested upstream revision exhibited a producer lifecycle race. The exact patch and base commit are retained in `patches/`.

## Runtime IPC

The native integration shim uses a runtime directory such as `/run/vtech` and creates per-camera endpoints:

```text
/run/vtech/cam1.sock
/run/vtech/cam1.state.json
/run/vtech/cam2.sock
/run/vtech/cam2.state.json
```

The Unix datagram socket accepts a small symbolic command grammar. The state file is rewritten atomically and is read by the Python API. The runtime directory should be mode `0700`; socket/state files should be mode `0600`.

## Local services

- API: `127.0.0.1:8787` by default
- kiosk: `0.0.0.0:8790` by default
- go2rtc ports: configurable; reference values above

The kiosk proxies API requests so the API can stay on loopback.

## Failure model

The browser UI treats a dead API runtime or a stale `last_video_ms` timestamp as a visible fault. A camera being reachable at the transport layer is not sufficient; the media timestamp must continue advancing.
