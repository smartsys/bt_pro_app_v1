#!/usr/bin/env bash
# Baut das VBT-Framework-Basis-Image (bt_pro_app_v1-vbt:latest) und zieht VBT Pro
# vom Original polakowo/vectorbt.pro per SSH-Key als BuildKit-Secret (kein Token,
# Key landet nie im Image). Eigene VBT-Pro-Lizenz nötig.
#
# Separat vom Compose, weil Compose-Build mit einem Build-Secret den buildx-bake-
# Schritt zum Absturz bringt. Compose nutzt das fertige Image danach als image:.
#
# Key-Pfad: Argument $1 oder Umgebungsvariable VBT_SSH_KEY.
#   WSL + Docker Desktop: der Key in ~/.ssh ist für die Windows-Engine nur über
#   den UNC-Pfad lesbar, z.B.:
#     \\wsl.localhost\<Distro>\home\<user>\.ssh\<keyname>
#   Native Linux/macOS: normaler Pfad, z.B. ~/.ssh/<keyname>
set -euo pipefail

KEY="${1:-${VBT_SSH_KEY:-}}"
if [ -z "$KEY" ]; then
  echo "FEHLER: Kein Key-Pfad. Aufruf: build.sh <pfad-zum-ssh-key>  (oder VBT_SSH_KEY setzen)" >&2
  exit 1
fi

# In das Service-Verzeichnis wechseln und relativen Context "." nutzen — die
# Windows-Engine übersetzt absolute /mnt/d-Pfade nicht, relative schon.
cd "$(dirname "$0")"
DOCKER_BUILDKIT=1 docker build \
  --secret "id=ssh_key,src=${KEY}" \
  -t bt_pro_app_v1-vbt:latest \
  .

echo "Fertig: bt_pro_app_v1-vbt:latest gebaut."
