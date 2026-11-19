"""Build the optional zillers_native shared library (single C++17 file, no dependencies).

Usage:  python native/build.py [--out DIR]

Output (default core/quant/_native/): zillers_native.dll | libzillers_native.so | libzillers_native.dylib
Compilers tried: MSVC (cl, found via vcvars64.bat), g++, clang++.
The library is optional: core.quant falls back to pure Python when it is absent.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "native" / "src" / "zillers_native.cpp"


def lib_name() -> str:
    if sys.platform.startswith("win"):
        return "zillers_native.dll"
    if sys.platform == "darwin":
        return "libzillers_native.dylib"
    return "libzillers_native.so"


def find_vcvars() -> str | None:
    pats = [
        r"C:\Program Files\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat",
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Auxiliary\Build\vcvars64.bat",
    ]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / lib_name()
    with tempfile.TemporaryDirectory() as tmp:
        if sys.platform.startswith("win") and not shutil.which("g++") and not shutil.which("clang++"):
            vcvars = None if shutil.which("cl") else find_vcvars()
            if vcvars is None and not shutil.which("cl"):
                raise SystemExit("No C++ compiler found (need MSVC Build Tools, g++ or clang++).")
            prefix = f'call "{vcvars}" >nul && ' if vcvars else ""
            # object/import-lib files land in the temp cwd; only the DLL goes to the target
            cmd = f'{prefix}cl /nologo /O2 /EHsc /std:c++17 /LD "{SRC}" /Fe:"{target}"'
            subprocess.run(cmd, shell=True, check=True, cwd=tmp)
        else:
            cxx = shutil.which("g++") or shutil.which("clang++")
            if cxx is None:
                raise SystemExit("No C++ compiler found (need g++ or clang++).")
            subprocess.run([cxx, "-O3", "-std=c++17", "-shared", "-fPIC", "-static-libstdc++", "-static-libgcc", str(SRC), "-o", str(target)], check=True)
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "core" / "quant" / "_native")
    args = ap.parse_args()
    print(build(args.out))
