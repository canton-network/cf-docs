#!/usr/bin/env bash
# Runs a command with Python + openpyxl and LibreOffice from nixpkgs, nothing installed system-wide.
# `soffice` on PATH is the real LibreOffice binary: the nix wrapper launches it through `open`,
# which returns before the work is done.
set -euo pipefail
exec nix-shell -I nixpkgs=channel:nixpkgs-unstable -p 'python3.withPackages (ps: [ ps.openpyxl ])' libreoffice-bin --run "
  shim=\$(mktemp -d)
  app=\$(dirname \$(dirname \$(readlink -f \$(command -v soffice))))/Applications/LibreOffice.app/Contents/MacOS/soffice
  printf '#!/bin/sh\nexec %s \"\$@\"\n' \"\$app\" > \"\$shim/soffice\"; chmod +x \"\$shim/soffice\"
  export PATH=\"\$shim:\$PATH\"
  $*
"
