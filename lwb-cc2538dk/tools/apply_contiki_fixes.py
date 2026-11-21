#!/usr/bin/env python3
"""Apply the two narrowly scoped fixes to the uploaded Contiki port, idempotently."""
import argparse
from pathlib import Path
import re


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("contiki", type=Path)
    args = ap.parse_args()
    root = args.contiki.expanduser().resolve()
    changes = [
        ("cpu/cc2538/rtimer-arch.h", "#define RTIMER_ARCH_SECOND 32768S",
         "#define RTIMER_ARCH_SECOND 32768UL"),
        ("cpu/cc2538/cc2538.lds", "} > FLASH_FW= 0", "} > FLASH_FW = 0"),
    ]
    prepared = []
    for name, old, new in changes:
        p = root / name
        text = p.read_text()
        if old in text:
            if text.count(old) != 1:
                raise SystemExit("Ambiguous match: " + str(p))
            prepared.append((p, text.replace(old, new)))
        elif new in text or (name.endswith("rtimer-arch.h") and
                             re.search(r"(?m)^\s*#define\s+RTIMER_ARCH_SECOND\s+32768(?:UL|U|L)?\s*$", text)):
            print("Already suitable:", p)
        else:
            raise SystemExit("Different port: inspect manually before editing " + str(p))
    for p, text in prepared:
        p.write_text(text)
        print("Patched:", p)


if __name__ == "__main__":
    main()
