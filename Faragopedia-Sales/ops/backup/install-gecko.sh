#!/usr/bin/env bash
# One-time install on gecko:  sudo bash install-gecko.sh <bundle dir>
# The bundle dir holds: this repo's ops/backup files, faragopedia-backup.conf,
# known_hosts, and (optionally) a pre-generated faragopedia_backup key pair.
set -euo pipefail
B="${1:?usage: sudo bash install-gecko.sh <bundle dir>}"
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

command -v restic >/dev/null || apt-get install -y restic

install -m 755 "$B/faragopedia-backup" /usr/local/sbin/faragopedia-backup
install -m 644 "$B/faragopedia-backup.service" "$B/faragopedia-backup.timer" /etc/systemd/system/
install -m 600 "$B/faragopedia-backup.conf" /etc/faragopedia-backup.conf
install -d -m 700 /root/.ssh
install -m 644 "$B/known_hosts" /root/.ssh/known_hosts_faragopedia_backup

if [ ! -f /root/.ssh/faragopedia_backup ]; then
  if [ -f "$B/faragopedia_backup" ]; then
    install -m 600 "$B/faragopedia_backup" /root/.ssh/faragopedia_backup
    install -m 644 "$B/faragopedia_backup.pub" /root/.ssh/faragopedia_backup.pub
    shred -u "$B/faragopedia_backup"
  else
    ssh-keygen -q -t ed25519 -N "" -C gecko-root-faragopedia-backup -f /root/.ssh/faragopedia_backup
  fi
fi

BASE=/srv/backup/faragopedia
install -d -m 700 "$BASE"
if [ ! -f "$BASE/restic-pass" ]; then
  (umask 077; head -c 32 /dev/urandom | base64 > "$BASE/restic-pass")
fi
if [ ! -f "$BASE/restic/config" ]; then
  RESTIC_PASSWORD_FILE="$BASE/restic-pass" restic init -q -r "$BASE/restic"
fi

systemctl daemon-reload
systemctl enable --now faragopedia-backup.timer
echo
echo "Installed. Public key (authorise on the VPS and yeti):"
cat /root/.ssh/faragopedia_backup.pub
echo
echo "IMPORTANT: copy the restic password into Vaultwarden now:"
echo "  sudo cat $BASE/restic-pass"
echo "Without it the backups (and yeti's mirror) cannot be read."
