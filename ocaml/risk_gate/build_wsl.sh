#!/bin/sh
# Build the OCaml shadow risk gate as a Linux binary (for Windows hosts that run it through WSL,
# or any Linux box without dune). Needs only the OCaml native compiler: `sudo apt install ocaml`.
# Output: _build/wsl/zillers-risk-gate  (cryptoscope.execution.shadow_gate finds it automatically)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp "$here/bin/gate.ml" "$here/bin/main.ml" "$tmp/"
(cd "$tmp" && ocamlopt -w -a gate.ml main.ml -o zillers-risk-gate)
mkdir -p "$here/_build/wsl"
cp "$tmp/zillers-risk-gate" "$here/_build/wsl/zillers-risk-gate"
chmod +x "$here/_build/wsl/zillers-risk-gate"
echo "built $here/_build/wsl/zillers-risk-gate ($(ocamlopt -version))"
