# Optional research helpers

These scripts support narrow static-analysis workflows for software you are authorized to inspect. They are not required by the runtime bridge.

Install the optional dependency in an isolated environment:

```bash
python -m venv .venv
. .venv/bin/activate
pip install androguard
```

## `dump_apk_methods.py`

Lists DEX methods from an APK and optionally filters by repeatable `--match` substrings.

```bash
python tools/research/dump_apk_methods.py --apk path/to/app.apk --match ioctrl --match camera
```

## `extract_vtech_receive_paths.py`

Filters method/class names for receive/event/IOCtrl terms that were useful during this project. It is a discovery helper, not a semantic decoder.

## `generate_ioctrl_evidence.py`

Turns a text trace containing IOCtrl-like hex/decimal identifiers into a small Markdown frequency/evidence report. Use it on your own sanitized traces; do not commit sensitive captures.
