#!/usr/bin/env bash
#
# Back up the panel's database.
#
#     ./backup.sh              take one now
#     ./backup.sh --verify     take one and prove it opens
#     ./backup.sh --restore FILE
#
# Installed on the server at /opt/mailpilot/backup.sh and run nightly by cron.
#
# WHY NOT `cp`. The database runs in WAL mode, so at any moment the committed
# state is split between mailpilot.db and mailpilot.db-wal — and the WAL here
# is routinely LARGER than the database. Copying just the .db file gives you a
# file that opens fine and is missing everything written since the last
# checkpoint. Copying both, non-atomically, can give you a torn pair that
# opens and then fails on a query nobody runs until they need it.
#
# `VACUUM INTO` asks SQLite itself for a consistent snapshot, taken under its
# own locking, with the WAL already folded in. It is the only method here that
# cannot produce a file that looks fine and is not.
#
# WHAT IS IN IT. Every contact, every campaign, the OpenAI key and the Gmail
# refresh token. Treat a backup file exactly as carefully as the server.
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/mailpilot}
DB="$APP_DIR/data/mailpilot.db"
# Inside the mounted volume, because the container writes them and it sees
# $APP_DIR/data as /data. That also means backups sit on the SAME DISK as the
# database, which protects against the likely failures — a bad deploy, an
# accidental --empty, logical corruption, a mistake at 2am — and not against
# losing the disk. Copy them off the box for that; see the note at the end.
DEST="$APP_DIR/data/backups"
KEEP_DAYS=${KEEP_DAYS:-14}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

die() { echo "backup: $*" >&2; exit 1; }

# ---------------------------------------------------------------- restore
if [[ "${1:-}" == "--restore" ]]; then
  FILE=${2:?usage: backup.sh --restore FILE}
  [[ -f "$FILE" ]] || die "no such file: $FILE"

  # Prove it before trusting it. Restoring a corrupt backup over a working
  # database turns a recoverable problem into an unrecoverable one.
  docker run --rm -v "$(dirname "$FILE")":/b alpine:latest sh -c \
    "apk add --no-cache sqlite >/dev/null 2>&1 && sqlite3 /b/$(basename "$FILE") 'PRAGMA integrity_check;'" \
    | grep -q '^ok$' || die "that file does not pass an integrity check — NOT restoring"

  echo "==> stopping the panel"
  docker stop mailpilot-panel >/dev/null
  SAFETY="$DEST/before-restore-$STAMP.db"
  mkdir -p "$DEST"
  cp "$DB" "$SAFETY" 2>/dev/null || true
  echo "    current database kept at $SAFETY"

  cp "$FILE" "$DB"
  rm -f "$DB-wal" "$DB-shm"      # stale WAL against a swapped file is corruption
  chown --reference="$DEST" "$DB" 2>/dev/null || true

  echo "==> starting the panel"
  docker start mailpilot-panel >/dev/null
  sleep 3
  curl -fsS --max-time 10 http://127.0.0.1:8000/api/health >/dev/null \
    && echo "restored from $FILE, and the panel is answering" \
    || die "restored, but the panel is not answering — check: docker logs mailpilot-panel"
  exit 0
fi

# ----------------------------------------------------------------- backup
[[ -f "$DB" ]] || die "no database at $DB"
mkdir -p "$DEST"
OUT="$DEST/mailpilot-$STAMP.db"

# Run sqlite INSIDE the app container: it already has the right version and
# the volume mounted, so there is nothing to install on the host.
docker exec mailpilot-panel python -c "
import sqlite3, sys
src = sqlite3.connect('/data/mailpilot.db')
src.execute(\"VACUUM INTO '/data/backups/$(basename "$OUT")'\")
src.close()
" || die "VACUUM INTO failed — is the container running?"

[[ -s "$OUT" ]] || die "the backup came out empty"
SIZE=$(du -h "$OUT" | cut -f1)

# Prove it opens and holds what it should. A backup nobody has ever restored
# is a hope, not a backup.
if [[ "${1:-}" == "--verify" ]]; then
  ROWS=$(docker exec mailpilot-panel python -c "
import sqlite3
c = sqlite3.connect('/data/backups/$(basename "$OUT")')
print(c.execute('PRAGMA integrity_check').fetchone()[0],
      c.execute('SELECT COUNT(*) FROM contacts').fetchone()[0],
      c.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0])
")
  echo "    integrity/contacts/campaigns: $ROWS"
  [[ "$ROWS" == ok* ]] || die "the backup does not pass an integrity check"
fi

# Keep a fortnight. Long enough to notice a problem that started a week ago,
# short enough that the disk does not fill with copies of a key and a token.
find "$DEST" -name 'mailpilot-*.db' -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true

echo "backed up to $OUT ($SIZE); $(find "$DEST" -name 'mailpilot-*.db' | wc -l) kept"
echo
echo "These sit on the same disk as the database. That covers a bad deploy, an"
echo "accidental wipe and logical corruption. It does NOT cover losing the box."
echo "To keep a copy elsewhere, from your own machine:"
echo "  scp root@THIS_SERVER:$DEST/\$(ssh root@THIS_SERVER ls -t $DEST | head -1) ."
