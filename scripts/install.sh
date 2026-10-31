#!/usr/bin/env sh
# FPGA Shepherd end-user installer.
# Installs uv if needed, then installs the shepherd CLI as a uv tool.
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/FrankP89/FPGA-shepherd/main/scripts/install.sh | sh
set -eu

REPO_GIT="git+https://github.com/FrankP89/FPGA-shepherd.git"
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
  echo "Installing FPGA Shepherd (shepherd)…"
  # Not on PyPI as a published release path yet — install from this repo.
  # When published: uv tool install fpga-shepherd
  uv tool install --force "${REPO_GIT}"
}

main() {
  install_uv
  install_shepherd
  ensure_path

  if ! command -v shepherd >/dev/null 2>&1; then
    echo "Shepherd was installed, but \`shepherd\` is not on PATH yet."
    echo "Add uv's bin dir to PATH, then open a new shell:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    exit 0
  fi

  echo
  echo "Done. Next:"
  echo "  cd my-fpga-project"
  echo "  shepherd init"
  echo "  shepherd --help"
}

main
