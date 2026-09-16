# Validated protocol notes

These values were observed on the LF925-2HD reference setup. They are interoperability notes, not a complete vendor protocol specification.

## PTZ

IOCtrl `0x1001`, 8-byte payload:

| Direction | Payload |
|---|---|
| Up | `01 08 00 00 00 00 00 00` |
| Down | `02 08 00 00 00 00 00 00` |
| Left | `03 08 00 00 00 00 00 00` |
| Right | `06 08 00 00 00 00 00 00` |

## Night light

### Preset / RGB — `0x07D4`

Eight-byte payload. Preset code is byte 0, remaining bytes zero.

| Code | Observed meaning |
|---:|---|
| `0x01` | orange |
| `0x02` | beige |
| `0x03` | yellow |
| `0x04` | green |
| `0x05` | blue |
| `0x06` | purple |
| `0x07` | white |
| `0x10` | rainbow |
| `0x11` | rainbow red phase |
| `0x12` | rainbow blue phase |

Custom RGB uses `20 RR GG BB 00 00 00 00`.

A preset value `0x00` appeared during transitions but was not independently validated as a generic OFF command, so the public API does not use it for power-off.

### Power / brightness — `0x07C8`

Four bytes: `[enabled][brightness][00][00]`.

Observed brightness bytes: `12`, `57`, `98`.

Observed examples include `01 0c 00 00`, `01 39 00 00`, `01 62 00 00`, and OFF as `00 62 00 00`.

### Timer — `0x07CC`

12 bytes, three little-endian 32-bit words:

```text
<enabled><seconds><reserved>
```

Validated seconds: `0`, `900`, `1800`, `3600`.

## Lullaby

### Track / stop — `0x0735`

8 bytes:

```text
<uint32 0><int32 sound_index>
```

Validated tracks `0..10`; stop uses `-1`.

### Volume / timer — `0x0731`

24 bytes, six little-endian words:

```text
<0><timer_seconds><volume><1><0><0>
```

Validated volume values: `1`, `3`, `5`. Validated timers: `0`, `900`, `1800`, `3600`.

A four-byte zero `0x07BA` preflight was observed immediately before `0x0731`; its standalone meaning remains unknown. The reference shim preserves that sequence.

## Temperature — `0x07D1`

Observed payload length: 12 bytes.

Celsius decode used by the reference shim:

```text
int32le(data[0:4]) + data[9] / 10
```

The capture also contained a Fahrenheit integer at offset 4 and a fractional byte at offset 10.

## Humidity — `0x07E2`

For validated frames where `data[0] == 1` and `data[1] == 0`, humidity percent is `data[3]`.

## Native events — `0x1FFF`

The event discriminator is byte 16:

| Byte 16 | Event |
|---:|---|
| `0x01` | motion |
| `0x15` | sound / baby |
| `0x16` | temperature alert |

The native shim converts these into epoch-millisecond timestamps in the atomic state file.

## Camera-side alert configuration observed during research

These were identified as configuration message families but are intentionally not exposed by the public control API:

- motion SET/RESP `0x0324/0x0325`, GET/RESP `0x0326/0x0327`
- temperature GET/RESP `0x074B/0x074C`, SET/RESP `0x074D/0x074E`
- motion tracking GET/RESP `0x07A4/0x07A5`, SET/RESP `0x07A6/0x07A7`
- sound/cry GET/RESP `0x07B0/0x07B1`, SET/RESP `0x07B2/0x07B3`
- sound sensitivity SET/RESP `0x07DC/0x07DD`, GET/RESP `0x07DE/0x07DF`

## Official-app View All quality control

The official Android app uses IOCtrl `0x0719` in the validated path. The low-rate View All payload had byte offset 4 set to `1`; the high-rate payload was all zero. Forcing the high-rate payload materially increased receive throughput for View All during testing. See `android-official-app.md` for the scope and limitations of that observation.
