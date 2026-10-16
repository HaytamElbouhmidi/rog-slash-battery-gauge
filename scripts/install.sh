#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
    echo "Run this script with sudo: sudo bash scripts/install.sh" >&2
    exit 1
fi

for command in python3 systemctl install cp date; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Missing required command: $command" >&2
        exit 1
    fi
done

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
backup_stamp=$(date -u +%Y%m%dT%H%M%SZ)

systemctl stop slash-battery.service 2>/dev/null || true

if systemctl cat slash-battery.timer >/dev/null 2>&1; then
    systemctl disable --now slash-battery.timer
fi

backup_existing() {
    local file=$1
    if [[ -e "$file" ]]; then
        local backup="${file}.backup-${backup_stamp}"
        if [[ -e "$backup" ]]; then
            echo "Backup already exists: $backup" >&2
            exit 1
        fi
        cp -a "$file" "$backup"
        echo "Backed up $file to $backup"
    fi
}

backup_existing /usr/local/bin/slash-battery.py
backup_existing /etc/systemd/system/slash-battery.service
backup_existing /etc/systemd/system-sleep/slash-battery

install -D -m 755 "$repo_dir/slash-battery.py" /usr/local/bin/slash-battery.py
install -D -m 644 "$repo_dir/systemd/slash-battery.service" /etc/systemd/system/slash-battery.service
install -D -m 755 "$repo_dir/systemd/slash-battery-resume" /etc/systemd/system-sleep/slash-battery
systemctl daemon-reload

cat <<'MESSAGE'

Installed Slash Battery Gauge. The service has not been started.

1. Preview the mapping:
   python3 /usr/local/bin/slash-battery.py --preview 30

2. Test the physical bar:
   sudo python3 /usr/local/bin/slash-battery.py --test 30 --hold 10
   sudo python3 /usr/local/bin/slash-battery.py --brightness-test --hold 10

3. When both tests look correct, enable the service:
   sudo systemctl enable --now slash-battery.service

MESSAGE
