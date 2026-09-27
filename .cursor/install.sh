#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"

# User-local console scripts (pytest, ruff, agent-harness, etc.)
profile="${HOME}/.profile"
if [[ -f "${profile}" ]] && ! grep -qF '.local/bin' "${profile}"; then
  printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "${profile}"
fi
