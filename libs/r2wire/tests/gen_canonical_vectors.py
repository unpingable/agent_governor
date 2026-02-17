# SPDX-License-Identifier: Apache-2.0
"""Generate golden canonical JSON vectors from receipt_kernel.

Run once to produce tests/data/canonical_vectors.json, then commit.
The test suite asserts byte-identity against these vectors.

Usage:
    cd libs/r2wire
    PYTHONPATH=../receipt_kernel/src:src python3 tests/gen_canonical_vectors.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from receipt_kernel.envelope import canonical_json as kernel_canonical
from r2wire.canonical import canonical_json_bytes as r2_canonical


CASES = [
    ("sorted_keys", {"b": 2, "a": 1}),
    ("unicode_nfc", {"s": "e\u0301"}),  # combining accent
    ("nested", {"x": [{"z": 3, "y": 2}]}),
    ("bool_int_edge", {"t": True, "i": 1}),
    ("empty", {}),
    ("string_escaping", {"q": 'he said "hello"'}),
    ("null_value", {"a": None, "b": 1}),
    ("deep_nesting", {"a": {"b": {"c": {"d": 1}}}}),
]


def main() -> int:
    out = []
    mismatches = 0

    for name, obj in CASES:
        kb = kernel_canonical(obj)
        # nfc=False for receipt_kernel compat (kernel doesn't NFC)
        rb = r2_canonical(obj, nfc=False)

        if kb != rb:
            print(f"MISMATCH {name}:")
            print(f"  kernel: {kb}")
            print(f"  r2wire: {rb}")
            mismatches += 1

        out.append({
            "name": name,
            "input": obj,
            "expected_utf8": kb.decode("utf-8"),
        })

    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "canonical_vectors.json"
    dest.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {dest} ({len(out)} vectors)")

    if mismatches:
        print(f"\n{mismatches} MISMATCHES — fix before committing!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
