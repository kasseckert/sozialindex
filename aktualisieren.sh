#!/usr/bin/env bash
# Daten abrufen und Index berechnen (für den Betrieb ohne GitHub, z. B. per cron).
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a      # optionale GENESIS-Zugangsdaten
echo "=== $(date '+%Y-%m-%d %H:%M') Aktualisierung"
python3 etl/abrufen.py "$@"
python3 etl/index_berechnen.py
echo "Fertig."
