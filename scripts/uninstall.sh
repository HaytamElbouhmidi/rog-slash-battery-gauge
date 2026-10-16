#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
    echo "Run this script with sudo: sudo bash scripts/uninstall.sh" >&2
    exit 1
fi

systemctl disable --now slash-battery.service 2>/dev/null || true
rm -f /usr/local/bin/slash-battery.py
rm -f /etc/systemd/system/slash-battery.service
rm -f /etc/systemd/system-sleep/slash-battery
systemctl daemon-reload

cat <<'MESSAGE'
Removed the script, systemd unit, and resume hook.
Previous backups and any older timer or Bash script were left in place.
To restore the ASUS factory lighting mode, configure it with asusctl if installed.
See the README for details.
MESSAGE
