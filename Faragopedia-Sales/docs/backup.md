# Production backups

Nightly backup of the VPS data (`/home/ubuntu/faragopedia-data`), pulled by
**gecko** (home server), stored there as an encrypted restic repository, and
mirrored to **yeti**. No paid service. Why and how: [ADR 0012](decisions/0012-tier1-hardening.md).
Files: [`ops/backup/`](../ops/backup/).

```
VPS (London)  --rrsync -ro-->  gecko: restic repo (encrypted)  --rrsync-->  yeti: mirror
```

- **Pull, not push.** gecko holds the key. On the VPS that key is locked to
  `rrsync -ro <data dir>`: it can read that folder, and nothing else (no shell,
  no writes). The VPS holds nothing that can reach the backups, so a
  compromised VPS cannot delete or encrypt them.
- **Encrypted at rest at home.** The plain copy exists only while the script
  runs; gecko and yeti keep only the restic repo. The data is client personal
  data, so this matters.
- **Retention:** 14 daily, 8 weekly, 12 monthly. Each run reads back 10% of the
  data (`restic check`); the yeti mirror only updates after that check passes.
- **Limits:** gecko and yeti are in the same house, so one site disaster takes
  both (the live VPS copy is still in London). gecko must be on: the timer
  catches up after downtime (`Persistent=true`). For a truly separate copy
  later, add a second restic target (Backblaze's free 10 GB tier fits).

**The restic password** (`/srv/backup/faragopedia/restic-pass` on gecko) is
the only way to read the backups or yeti's mirror. Keep a copy in Vaultwarden.

## Install (once)

Host values (VPS address and port, yeti address) go in
`/etc/faragopedia-backup.conf` on gecko, not in this repo. Copy the
`ops/backup/` files plus a filled-in `faragopedia-backup.conf` and a
`known_hosts` (pinned host keys for the VPS and yeti) into a folder on gecko.

1. **yeti:** `sudo install -d -o colacho -g colacho -m 700 /mnt/storage/backups/faragopedia-gecko`
2. **gecko:** `sudo bash install-gecko.sh <folder>`. This installs restic,
   the script and timer, creates the key (or installs a pre-made one), the
   restic password and the repository, and prints the public key.
3. **Authorise the key** (comment `gecko-root-faragopedia-backup`):
   - VPS, `~ubuntu/.ssh/authorized_keys`:
     `restrict,command="rrsync -ro /home/ubuntu/faragopedia-data" ssh-ed25519 … gecko-root-faragopedia-backup`
   - yeti, `~colacho/.ssh/authorized_keys`:
     `restrict,command="rrsync /mnt/storage/backups/faragopedia-gecko" ssh-ed25519 … gecko-root-faragopedia-backup`
4. **First run:** `sudo systemctl start faragopedia-backup.service`, then
   `journalctl -u faragopedia-backup -n 20`. It ends with
   `OK: <n> pages, <n> snapshots, mirrored to yeti`.
5. Copy the restic password into Vaultwarden.
6. Optional: an Uptime Kuma **push** monitor (heartbeat 26 h), with its URL
   in `HEALTHCHECK_URL`, so a missed night raises an alert.

## Restore test (after install, then quarterly)

```bash
sudo bash -c '
export RESTIC_REPOSITORY=/srv/backup/faragopedia/restic RESTIC_PASSWORD_FILE=/srv/backup/faragopedia/restic-pass RESTIC_CACHE_DIR=/var/cache/faragopedia-backup
restic snapshots --compact
restic restore latest --target /tmp/fp-restore-test -q
find /tmp/fp-restore-test -name "*.md" | wc -l
rm -rf /tmp/fp-restore-test'
```

The page count should match the live wiki. The script backs up `.` from the
staging folder, so a snapshot's root *is* the data folder: restore `latest`
(or a snapshot id) with no sub-path, and the target holds `workspaces/…` directly.

## Real restore

1. On gecko, restore the snapshot to a folder (as above, without the `rm`).
   That folder is the contents of `~/faragopedia-data`.
2. Stop the stack in Portainer.
3. On the VPS, move the current data aside:
   `mv ~/faragopedia-data ~/faragopedia-data.broken-$(date +%F)`.
4. Copy the restored folder up as `~/faragopedia-data` (scp/rsync from gecko
   with your own key; the backup key is read-only on purpose).
5. Start the stack. Check the wiki loads and the page count looks right.

If gecko itself is lost, use yeti's mirror: it is the same restic repository.
Point `restic -r` at it (copy it to any machine with restic) and use the
password from Vaultwarden.
