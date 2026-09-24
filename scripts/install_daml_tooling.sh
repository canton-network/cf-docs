#!/usr/bin/env bash

set -euo pipefail

installer_url="${DAML_INSTALLER_URL:-https://get.digitalasset.com/install/install.sh}"
max_attempts="${DAML_INSTALL_MAX_ATTEMPTS:-3}"
retry_delay_seconds="${DAML_INSTALL_RETRY_DELAY_SECONDS:-15}"

if [[ ! "$max_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "DAML_INSTALL_MAX_ATTEMPTS must be a positive integer." >&2
  exit 2
fi

if [[ ! "$retry_delay_seconds" =~ ^[0-9]+$ ]]; then
  echo "DAML_INSTALL_RETRY_DELAY_SECONDS must be a non-negative integer." >&2
  exit 2
fi

for ((attempt = 1; attempt <= max_attempts; attempt++)); do
  echo "Installing Daml tooling (attempt ${attempt}/${max_attempts})..."
  if curl -fsSL "$installer_url" | sh; then
    exit 0
  else
    install_status=$?
  fi

  if ((attempt == max_attempts)); then
    echo "Daml tooling installation failed after ${max_attempts} attempts." >&2
    exit "$install_status"
  fi

  delay=$((retry_delay_seconds * attempt))
  echo "Daml tooling installation failed; retrying in ${delay}s." >&2
  sleep "$delay"
done
