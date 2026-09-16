#!/usr/bin/env python3
"""Find likely VTech receive/event/IOCtrl methods in an APK."""
from __future__ import annotations

import argparse
from pathlib import Path

from androguard.misc import AnalyzeAPK

DEFAULT_TERMS = (
    "ioctrl", "receive", "recv", "notification", "motion", "sound",
    "temperature", "humidity", "alarm", "camera", "tutk", "avapi",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True, type=Path)
    ap.add_argument("--term", action="append", default=[])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if not args.apk.is_file():
        raise SystemExit(f"APK not found: {args.apk}")

    _apk, _dex, dx = AnalyzeAPK(str(args.apk))
    terms = tuple(x.lower() for x in (args.term or DEFAULT_TERMS))
    hits = []
    for ma in dx.get_methods():
        m = ma.get_method()
        name = f"{m.get_class_name()}->{m.get_name()}{m.get_descriptor()}"
        if any(term in name.lower() for term in terms):
            hits.append(name)

    text = "\n".join(sorted(set(hits))) + ("\n" if hits else "")
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
