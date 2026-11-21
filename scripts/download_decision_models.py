"""Download the THX-02 and Laya weights into work/models/, pinned to an exact Hugging Face commit.

Run with the isolated model venv (it has huggingface_hub). On Windows the models run in WSL, because
Application Control blocks PyTorch's DLLs; keep the weights on WSL's Linux disk for fast loading:
    wsl ~/.zillers-models-venv/bin/python scripts/download_decision_models.py --dest ~/zillers-models
    wsl ~/.zillers-models-venv/bin/python scripts/download_decision_models.py --dest ~/zillers-models --check

The resolved commit hashes are written to work/models/REVISIONS.json so the same weights can be
re-downloaded later. Only safetensors/JSON/tokenizer files are fetched; THX-02's GPU thinker, mobile
build and images, and Laya's multilingual checkpoint and eval data, are skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "work" / "models"
MODELS = {
    "thx02": {"repo": "HAL-X-AI/THX-02", "ignore": ["thinker/*", "mobile/*", "assets/*", "*.md"]},
    "laya": {"repo": "convaiinnovations/laya", "ignore": ["multilingual/*", "eval/*", "assets/*", "*.md"]},
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="only report what is on disk")
    ap.add_argument("--only", choices=sorted(MODELS), help="download one model")
    ap.add_argument("--dest", default=str(DEST), help="weights folder (default work/models)")
    args = ap.parse_args()
    dest = Path(args.dest).expanduser()
    from huggingface_hub import HfApi, snapshot_download

    pins_path = dest / "REVISIONS.json"
    pins = json.loads(pins_path.read_text()) if pins_path.is_file() else {}
    for name, spec in MODELS.items():
        if args.only and name != args.only:
            continue
        target = dest / name
        if args.check:
            files = [p for p in target.rglob("*") if p.is_file()] if target.exists() else []
            gb = sum(p.stat().st_size for p in files) / 1e9
            print(f"{name}: {len(files)} files, {gb:.2f} GB, revision {pins.get(name, {}).get('revision', '?')}")
            continue
        revision = pins.get(name, {}).get("revision") or HfApi().model_info(spec["repo"]).sha
        print(f"{name}: downloading {spec['repo']}@{revision[:12]} -> {target}", flush=True)
        snapshot_download(spec["repo"], revision=revision, local_dir=str(target), ignore_patterns=spec["ignore"])
        pins[name] = {"repo": spec["repo"], "revision": revision}
        dest.mkdir(parents=True, exist_ok=True)
        pins_path.write_text(json.dumps(pins, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
