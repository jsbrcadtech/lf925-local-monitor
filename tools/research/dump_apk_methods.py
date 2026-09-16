#!/usr/bin/env python3
"""List DEX methods from an APK using Androguard."""
from __future__ import annotations

import argparse
from pathlib import Path

from androguard.misc import AnalyzeAPK


def method_name(method_analysis) -> str:
    m = method_analysis.get_method()
    return f"{m.get_class_name()}->{m.get_name()}{m.get_descriptor()}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True, type=Path)
    ap.add_argument("--match", action="append", default=[],
                    help="case-insensitive substring; may be repeated")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    if not args.apk.is_file():
        raise SystemExit(f"APK not found: {args.apk}")

    _apk, _dex, dx = AnalyzeAPK(str(args.apk))
    needles = [x.lower() for x in args.match]
    rows = sorted({method_name(ma) for ma in dx.get_methods()})
    if needles:
        rows = [r for r in rows if any(n in r.lower() for n in needles)]

    text = "\n".join(rows) + ("\n" if rows else "")
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
