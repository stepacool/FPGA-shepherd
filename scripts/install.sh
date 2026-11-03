#!/usr/bin/env sh
# FPGA Shepherd end-user installer.
# Installs uv if needed, then installs the shepherd CLI as a uv tool.
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/FrankP89/FPGA-shepherd/main/scripts/install.sh | sh
# Override the install source:
#   SHEPHERD_SOURCE=git+https://github.com/FrankP89/FPGA-shepherd.git sh install.sh
set -eu

DEFAULT_SOURCE="git+https://github.com/FrankP89/FPGA-shepherd.git"
SHEPHERD_SOURCE="${SHEPHERD_SOURCE:-$DEFAULT_SOURCE}"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

ensure_path() {
  # Common uv install locations (fresh install may not be on PATH yet).
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  echo "uv not found; installing uv…"
  curl -LsSf "${UV_INSTALL_URL}" | sh
  ensure_path
  if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv install finished but \`uv\` is not on PATH" >&2
    echo "  try: export PATH=\"\$HOME/.local/bin:\$PATH\" and re-run this script" >&2
    exit 1
  fi
}

install_shepherd() {
  ensure_path
  echo "Installing FPGA Shepherd (shepherd) from ${SHEPHERD_SOURCE}…"
  uv tool install --force --upgrade "${SHEPHERD_SOURCE}"
}

main() {
  install_uv
  install_shepherd
  ensure_path

  if ! command -v shepherd >/dev/null 2>&1; then
    echo "Shepherd was installed, but \`shepherd\` is not on PATH yet."
    echo "Add uv's bin dir to PATH (or run: uv tool update-shell), then open a new shell:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    if command -v uv >/dev/null 2>&1; then
      uv tool update-shell >/dev/null 2>&1 || true
      echo "  (attempted \`uv tool update-shell\` — open a new shell to pick it up)"
    fi
    exit 0
  fi

  echo
  shepherd --version
  echo
  echo "Done. Next:"
  echo "  cd my-fpga-project"
  echo "  shepherd init"
}

main
