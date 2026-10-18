#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
skip_browser=false
if [[ "${1:-}" == "--skip-browser" ]]; then skip_browser=true; fi
if [[ ! -f "$project_root/pyproject.toml" ]]; then
  printf '%s\n' "Extract the complete Paper SA project before running this installer." >&2
  exit 1
fi
printf '\nPaper SA installer - managed Python 3.12 and local-account installation.\n'
if command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
elif [[ -x "$HOME/.local/bin/uv" ]]; then
  uv_bin="$HOME/.local/bin/uv"
else
  installer="$(mktemp)"
  trap 'rm -f -- "$installer"' EXIT
  if command -v curl >/dev/null 2>&1; then
    curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh -o "$installer"
  elif command -v wget >/dev/null 2>&1; then
    wget -q https://astral.sh/uv/install.sh -O "$installer"
  else
    printf '%s\n' "Install curl or wget with your system package manager, then retry." >&2
    exit 1
  fi
  sh "$installer"
  uv_bin="$HOME/.local/bin/uv"
fi
"$uv_bin" python install 3.12
constraints="$(mktemp)"
trap 'rm -f -- "$constraints"; if [[ -n "${installer:-}" ]]; then rm -f -- "$installer"; fi' EXIT
"$uv_bin" export --project "$project_root" --frozen --no-dev --no-emit-project --no-hashes --output-file "$constraints" >/dev/null
"$uv_bin" tool install --force --python 3.12 --constraint "$constraints" "$project_root"
bin_dir="$("$uv_bin" tool dir --bin)"
"$uv_bin" tool update-shell || true
if [[ "$skip_browser" == false ]]; then
  "$bin_dir/paper-sa" install-browser || printf '%s\n' "Browser download failed. Use manual mode or retry: paper-sa install-browser"
fi
"$bin_dir/paper-sa" --version
printf '\nInstalled. Open a new terminal and run: paper-sa\n'
printf 'Or run directly: %s/paper-sa\n' "$bin_dir"
if [[ "$(uname -s)" == Linux ]]; then
  printf '%s\n' "If Chromium reports missing shared libraries, install your distribution's browser dependencies (see docs/SETUP.md)."
fi
