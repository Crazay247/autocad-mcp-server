"""Generate golden DXF files for version-matrix (R2018 vs R2013).

Usage:
  uv run python tests/generate_golden.py
  uv run python tests/generate_golden.py --out tests/fixtures/goldens

Produces:
  - golden_r2018_NBC.dxf  (AC1032, R2018 — required for AutoCAD 2021)
  - golden_r2013_NBC.dxf  (AC1027, R2013 — legacy, for matrix comparison)

Triple-linkage: layer + dimstyle + version are verified in test_ezdxf_nbc_backend.
Goldens are checked into fixtures for snapshot testing.
"""

from __future__ import annotations

import argparse
import pathlib
import hashlib

import ezdxf

NBC_LAYERS = [
    "A-WALL",
    "A-WALL-230",
    "A-WALL-115",
    "A-DOOR",
    "A-WIND",
    "A-DIM",
    "A-GRID",
    "A-ANNO",
    "G-TTLB",
    "V-PORT",
]


def make_doc(version: str) -> ezdxf.Drawing:
    doc = ezdxf.new(version)
    for n in NBC_LAYERS:
        if n not in doc.layers:
            doc.layers.add(n)
    if "NBC-100" not in doc.dimstyles:
        doc.dimstyles.new("NBC-100")
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_text("शयन कक्ष", height=250, dxfattribs={"layer": "A-ANNO"}).set_placement((500, 500))
    return doc


def main():
    parser = argparse.ArgumentParser(description="Generate golden DXF for NBC (R2018 vs R2013)")
    parser.add_argument("--out", type=str, default="tests/fixtures/goldens", help="output directory")
    args = parser.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    for ver, name in [("R2018", "golden_r2018_NBC.dxf"), ("R2013", "golden_r2013_NBC.dxf")]:
        doc = make_doc(ver)
        p = outdir / name
        doc.saveas(str(p))
        h = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        # verify roundtrip
        doc2 = ezdxf.readfile(str(p))
        print(f"{name}: {doc2.dxfversion} layers={len(list(doc2.layers))} sha256:{h} -> {p}")

    # Also test that R2018 is AC1032
    doc_r2018 = ezdxf.new("R2018")
    assert doc_r2018.dxfversion == "AC1032", f"R2018 should be AC1032, got {doc_r2018.dxfversion}"
    doc_r2013 = ezdxf.new("R2013")
    assert doc_r2013.dxfversion == "AC1027"
    print("Version-matrix OK: R2018=AC1032, R2013=AC1027")


if __name__ == "__main__":
    main()
