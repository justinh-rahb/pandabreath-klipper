#!/usr/bin/env python3
"""Patch Panda Breath firmware UI/HA temperature caps from 60 C to 70 C.

Takes a stock BIQU ESP32-C3 app-image .bin and writes a patched .bin that
unlocks 70 C in the web UI and (where present) Home Assistant discovery. The
hardware safety cutoff in the firmware (around 105 C) is untouched.

Each patch is located by searching for a unique anchor string, so this works
across firmware versions (1.0.1, 1.0.2, 1.0.3, 1.0.4, ...) without per-version
offset tables. Patches whose anchor is absent on a given version are skipped
with a warning rather than aborting.

Internally: load the .bin via esptool, mutate the matching string bytes inside
the relevant segment, then re-serialize. esptool handles checksum + SHA-256
validation hash automatically, so the output is a flashable, signed image.

Usage:
    python3 patch_panda_breath_70c.py <stock.bin> <patched.bin>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from esptool.bin_image import LoadFirmwareImage


# Each patch: (description, old bytes, new bytes, required).
# old must be the EXACT bytes to find; old and new must be the SAME LENGTH
# because we are not relocating anything inside the segment.
PATCHES = (
    ("HA discovery cap (set_temp)",
     b'max":60', b'max":70', False),
    ("HA discovery cap (warehouse)",
     b'max":60', b'max":70', False),
    ("Web UI outgoing input clamp (settings)",
     b"> 60) settingstempValue = 60", b"> 70) settingstempValue = 70", True),
    ("Web UI outgoing input clamp (actual)",
     b"> 60) actualtempValue = 60",  b"> 70) actualtempValue = 70",  True),
    ("Warning copy (English)",
     b"Exceeding 60", b"Exceeding 70", True),
    # The Chinese warning carries the bare ASCII "60" embedded inside the
    # UTF-8 sequence "超过60°C". Anchor on the unique "超过" prefix.
    ("Warning copy (Chinese)",
     b"\xe8\xb6\x85\xe8\xbf\x8760", b"\xe8\xb6\x85\xe8\xbf\x8770", True),
    ("Web UI incoming state clamp (tempValue0)",
     b"> 60) tempValue0 = 60", b"> 70) tempValue0 = 70", True),
    ("Web UI incoming state clamp (tempValue)",
     b"> 60) tempValue = 60",  b"> 70) tempValue = 70",  True),
)


def patch_segment_bytes(segments, old: bytes, start_from: tuple[int, int]) -> tuple[int, int, int] | None:
    """Find `old` in segments starting at (seg_index, offset). Returns
    (seg_index, offset, load_addr) of the hit, or None."""
    s_idx, s_off = start_from
    for i in range(s_idx, len(segments)):
        off = s_off if i == s_idx else 0
        idx = segments[i].data.find(old, off)
        if idx >= 0:
            return i, idx, segments[i].addr + idx
    return None


def apply_patches(src: Path, dst: Path) -> None:
    img = LoadFirmwareImage('esp32c3', str(src))
    # esptool returns immutable bytes for .data; convert to bytearray so we
    # can mutate in place. save() will pick up the mutated bytes. Also stub
    # .name (only set when loading from ELF; save() reads it unconditionally).
    for seg in img.segments:
        seg.data = bytearray(seg.data)
        if not hasattr(seg, 'name'):
            seg.name = ''

    # Cursor per anchor to handle duplicate-anchor patches (e.g. the two HA
    # discovery caps that share the literal `max":60`).
    cursors: dict[bytes, tuple[int, int]] = {}
    for desc, old, new, required in PATCHES:
        if len(old) != len(new):
            raise SystemExit(f"length mismatch in patch {desc!r}")
        hit = patch_segment_bytes(img.segments, old, cursors.get(old, (0, 0)))
        if hit is None:
            if required:
                raise SystemExit(
                    f"Patch precondition failed: {desc} — anchor {old!r} not found"
                )
            print(f"skip:  {desc} (anchor not present in this firmware)")
            continue
        seg_i, off, load_addr = hit
        img.segments[seg_i].data[off : off + len(old)] = new
        cursors[old] = (seg_i, off + len(old))
        print(f"patch: {desc} @ seg{seg_i} +0x{off:x} (load 0x{load_addr:08x})")

    img.save(str(dst))
    print(f"wrote {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("src", type=Path, help="stock .bin")
    parser.add_argument("dst", type=Path, help="output patched .bin")
    args = parser.parse_args()
    apply_patches(args.src, args.dst)


if __name__ == "__main__":
    main()
