# Research workflow

The finished runtime code is intentionally separated from the reverse-engineering process. If you are extending compatibility, use a narrow evidence-driven workflow rather than broad fuzzing.

## Recommended sequence

1. capture one known UI action at a time
2. identify the Java/native call path statically
3. trace only the smallest relevant method or IOCtrl boundary
4. record direction, type, exact payload, timing and visible effect
5. repeat the action enough times to separate stable bytes from incidental state
6. replay only a payload you understand on a device you own/control
7. add a typed command only after the semantic meaning is sufficiently supported
8. add a regression test for the encoding/decoding rule

## Avoid

- blind IOCtrl fuzzing
- broad native export enumeration on fragile targets
- treating a single transition packet as a stable semantic command
- committing APKs, vendor libraries, pairing data, packet captures or credentials
- exposing a raw IOCtrl passthrough in the production API

## Evidence levels

A useful internal vocabulary is:

- **proven** — replayed/validated with the expected device behavior
- **high confidence** — repeated capture/static evidence with strong semantic support
- **medium** — plausible mapping but incomplete validation
- **speculative** — observation only; do not expose as a production control

Only proven/high-confidence behavior should reach the typed public API.
