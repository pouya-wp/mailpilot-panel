#!/usr/bin/env bash
#
# Ship the current working tree to the server, as a container behind Traefik.
#
#     ./deploy/deploy.sh root@187.77.141.155 panel.srv1896911.hstgr.cloud
#
# Safe to run repeatedly.
#
# WHY A CONTAINER. This machine already runs Traefik on 80/443, fronting an n8n
# stack that has been up for weeks. Traefik discovers services through the
# Docker API and gets certificates from Let's Encrypt automatically, so
# arriving as a labelled container means HTTPS without touching Traefik's
# configuration and without any chance of a port conflict taking n8n down.
#
# WHY ONE SSH CONNECTION. This was four — one per upload, one to build — until
# the provider firewall went up. It rate-limits new connections and started
# dropping the second, so every step passed alone and the sequence failed every
# time. ControlMaster multiplexing is the usual answer and does not work under
# Git Bash on Windows. So the code, the panel, the Dockerfile AND the server-side
# script all travel in one tarball, piped through a single ssh that extracts it
# and runs the script it just received.
#
# What this never touches: $APP_DIR/data. The database and the JWT secret live
# there, mounted into the container, so rebuilding cannot lose a customer's
# campaigns or sign everybody out.
set -euo pipefail

TARGET="${1:-}"
DOMAIN="${2:-panel.srv1896911.hstgr.cloud}"
if [[ -z "$TARGET" ]]; then
  echo "usage: $0 user@host [domain]" >&2
  exit 2
fi

APP_DIR=/opt/mailpilot
NAME=mailpilot-panel
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> tests"
( cd "$HERE/backend" && python -m pytest tests/ -q ) || {
  echo "Tests failed. Not deploying." >&2
  exit 1
}

echo "==> building the panel"
( cd "$HERE" && npm run build )

echo "==> staging"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/build/api" "$STAGE/build/web"

# tar-to-tar rather than cp, so the excludes are honoured on the way through
tar -cf - -C "$HERE/backend" \
    --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.secret' --exclude='*.db' --exclude='tests' \
    app run.py requirements.txt | tar -xf - -C "$STAGE/build/api"
tar -cf - -C "$HERE/dist" . | tar -xf - -C "$STAGE/build/web"
cp "$HERE/deploy/Dockerfile" "$STAGE/build/Dockerfile"
cp "$HERE/deploy/remote.sh"  "$STAGE/build/remote.sh"

echo "==> uploading and building (one connection)"
# The tar is consumed by `tar -xzf -`, which frees stdin before remote.sh runs.
tar -czf - -C "$STAGE" build \
  | ssh -o BatchMode=yes -o ServerAliveInterval=20 "$TARGET" \
      "set -e
       mkdir -p '$APP_DIR'
       rm -rf '$APP_DIR/build'
       tar -xzf - -C '$APP_DIR'
       DOMAIN='$DOMAIN' NAME='$NAME' APP_DIR='$APP_DIR' bash '$APP_DIR/build/remote.sh'"

echo
echo "Deployed. https://${DOMAIN}/"
