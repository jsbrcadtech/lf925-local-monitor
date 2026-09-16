#!/usr/bin/env python3
"""Generate a small IOCtrl identifier report from a sanitized text trace."""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

HEX = re.compile(r"(?<![0-9A-Fa-f])0x([0-9A-Fa-f]{3,8})(?![0-9A-Fa-f])")
DEC = re.compile(r"\b(?:ioctrl|type|cmd)\s*[:=]\s*(\d{3,6})\b", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    text = args.input.read_text(encoding="utf-8", errors="replace")

    counts: collections.Counter[int] = collections.Counter()
    for m in HEX.finditer(text):
        counts[int(m.group(1), 16)] += 1
    for m in DEC.finditer(text):
        counts[int(m.group(1))] += 1

    lines = ["# IOCtrl evidence summary", "", "| ID | Decimal | Mentions |", "|---:|---:|---:|"]
    for value, count in counts.most_common():
        lines.append(f"| `0x{value:04X}` | {value} | {count} |")
    lines += ["", "> Frequency is evidence of occurrence only; it does not establish semantics.", ""]
    out = "\n".join(lines)
    if args.out:
        args.out.write_text(out, encoding="utf-8")
    else:
        print(out)


if __name__ == "__main__":
    main()
