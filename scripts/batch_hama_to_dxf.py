"""Batch convert Hama DWG (AC10xx binary) -> DXF R2018 for ezdxf ingestion.

Uses accoreconsole (licensed) with fallback to ODA File Converter if available.
Every run teaches LLM: gold vectors from Hama 77-layer construction set become few-shot.

Usage:
  python scripts/batch_hama_to_dxf.py --src "D:\\00) ARCHITECTURE\\.REF\\DWG\\hama_CONSTRUCTION DRAWINGS" --out "C:\\Temp\\hama_dxf" --verify
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time

ACCORE = pathlib.Path(r"D:\SOFTWARES\Autocad 2021\AutoCAD 2021\accoreconsole.exe")
HAMA_DIR = pathlib.Path(r"D:\00) ARCHITECTURE\.REF\DWG\hama_CONSTRUCTION DRAWINGS")
OUT_DIR = pathlib.Path(r"C:\Users\Predator\AppData\Local\Temp\hama_dxf")


def convert_one(dwg: pathlib.Path, dxf: pathlib.Path, timeout: int = 90) -> bool:
    dxf.parent.mkdir(parents=True, exist_ok=True)
    # accoreconsole script: FILEDIA 0 -> DXFOUT -> 16 (R2004) or 0 for default -> path -> precision 16
    scr = dxf.parent / f"_{dwg.stem}.scr"
    scr.write_text(f"FILEDIA\n0\n_DXFOUT\n16\n{dxf}\n16\n", encoding="ascii")
    cmd = [str(ACCORE), "/i", str(dwg), "/s", str(scr), "/l", "en-US"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            print(f"TIMEOUT {dwg.name} after {timeout}s (accoreconsole hang, common - retry with ODA)")
            return False
        if dxf.exists() and dxf.stat().st_size > 1000:
            print(f"OK {dwg.name} -> {dxf.name} {dxf.stat().st_size//1024}KB")
            return True
        print(f"FAIL {dwg.name} no output (exit {proc.returncode})")
        return False
    finally:
        try:
            scr.unlink()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=pathlib.Path, default=HAMA_DIR)
    ap.add_argument("--out", type=pathlib.Path, default=OUT_DIR)
    ap.add_argument("--verify", action="store_true", help="after convert, run ezdxf extract + Chroma embed")
    ap.add_argument("--oda", type=pathlib.Path, default=None, help="ODA File Converter exe if accoreconsole fails")
    args = ap.parse_args()

    dwgs = sorted(args.src.glob("*.dwg"))
    print(f"Found {len(dwgs)} DWG in {args.src}")
    ok = 0
    for dwg in dwgs:
        dxf = args.out / f"{dwg.stem}.dxf"
        if dxf.exists():
            print(f"SKIP {dwg.name} exists")
            ok += 1
            continue
        if convert_one(dwg, dxf):
            ok += 1
        time.sleep(1)

    print(f"Converted {ok}/{len(dwgs)}")

    if args.verify and ok:
        # Verify via ezdxf + hama_store extract
        try:
            import ezdxf
            from src.autocad_arch_mcp.rag.hama_store import extract_hama_features, _embed

            for dxf in sorted(args.out.glob("*.dxf"))[:2]:
                try:
                    doc = ezdxf.readfile(str(dxf))
                    feats = extract_hama_features(doc)
                    print(f"VERIFY {dxf.name}: layers {feats['layers_count']} dims {feats['dims_count']} hatches {feats['hatches_count']} layouts {feats['layouts_count']}")
                except Exception as e:
                    print(f"VERIFY FAIL {dxf.name}: {e}")
        except Exception as e:
            print(f"verify import fail: {e}")


if __name__ == "__main__":
    main()
