"""Portable JSON evidence and a readable Markdown research report."""
import json
from pathlib import Path


def write_report(body, directory):
    directory = Path(directory) / body["run_id"]
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(body, indent=2, allow_nan=False)
    (directory / "report.json").write_text(text, encoding="utf-8")
    lines = ["# Zien Laya Research", "", f"Run: {body['run_id']}",
             f"Status: {body['status']}", f"Model: {body['model']}",
             f"Mode: {body['mode']}", "", "## Decision", "",
             "```json", json.dumps(body.get("decision", {}), indent=2), "```", ""]
    if body.get("error"):
        lines += ["Error: " + body["error"], ""]
    for stage in body["stages"]:
        lines += ["## " + stage["name"], "", "```json", json.dumps(stage["output"], indent=2), "```", ""]
    lines += ["## Execution", "", "```json", json.dumps(body.get("execution", {}), indent=2), "```"]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return str(directory)
