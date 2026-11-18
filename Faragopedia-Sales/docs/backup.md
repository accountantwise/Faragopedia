# Production backups (VPS)

Nightly restic backup of `/home/ubuntu/faragopedia-data` to off-site storage.
Why and what: [ADR 0012](decisions/0012-tier1-hardening.md). Files:
[`ops/backup/`](../ops/backup/).

The data is client personal data. The destination must be in the UK or EU,
and its credentials and the restic password live with the other VPS secrets,
never in this repo. **Without the restic password the backups cannot be
read**, so store it in two places (e.g. the password manager and the secrets
`.env`).

## Install (once, on the VPS)

```bash
sudo apt-get install -y restic
sudo install -m 755 ops/backup/faragopedia-backup.sh /usr/local/bin/
sudo install -m 644 ops/backup/faragopedia-backup.{service,timer} /etc/systemd/system/
sudo install -m 600 ops/backup/faragopedia-backup.env.example /etc/faragopedia-backup.env
sudoedit /etc/faragopedia-backup.env          # repository + credentials
sudo sh -c 'openssl rand -base64 32 > /etc/faragopedia-backup.pass && chmod 600 /etc/faragopedia-backup.pass'

sudo bash -c 'set -a; . /etc/faragopedia-backup.env; restic init'
sudo systemctl daemon-reload
sudo systemctl enable --now faragopedia-backup.timer
sudo systemctl start faragopedia-backup.service   # first run now
journalctl -u faragopedia-backup.service -n 30
```

Set `HEALTHCHECK_URL` to a healthchecks.io (or Uptime Kuma push) URL, so a
missed or failed night raises an alert instead of going unnoticed.

## Restore test (do it once after install, then quarterly)

```bash
sudo bash -c 'set -a; . /etc/faragopedia-backup.env; restic snapshots --compact'
sudo bash -c 'set -a; . /etc/faragopedia-backup.env; restic restore latest --target /tmp/fp-restore-test'
sudo diff -r /home/ubuntu/faragopedia-data /tmp/fp-restore-test/home/ubuntu/faragopedia-data && echo OK
sudo rm -rf /tmp/fp-restore-test
```

## Real restore

1. Stop the stack in Portainer (so nothing writes during the restore).
2. Move the current data aside: `sudo mv ~/faragopedia-data ~/faragopedia-data.broken-$(date +%F)`.
3. `restic restore <snapshot-id> --target /` puts it back at the original path.
4. Start the stack. Check the wiki loads and the page count looks right.
5. Delete the `.broken-…` copy only once you are sure.

## Retention

14 daily, 8 weekly, 12 monthly snapshots. Each run also reads back 5% of the
stored data (`restic check --read-data-subset=5%`), so corruption shows up
within days.
