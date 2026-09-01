#!/usr/bin/env bash
#
# One-time server preparation. Run this ONCE on a fresh VPS, as root.
#
#     ssh root@YOUR_SERVER 'bash -s' < deploy/bootstrap-server.sh
#
# It installs what the panel needs, creates a user that is NOT root to run it,
# lays out the directories, and closes everything except SSH and the web.
#
# Deliberately separate from deploy.sh. This changes the machine; that ships
# code. Mixing them means every routine deploy re-runs package installs and
# firewall edits, which is how a deploy script slowly becomes something nobody
# dares run.
set -euo pipefail

APP_USER=mailpilot
APP_DIR=/opt/mailpilot

echo "==> packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  python3 python3-venv python3-pip \
  nginx rsync ufw ca-certificates curl

echo "==> service account"
# The API runs as this user, not as root. A bug in a web process that runs as
# root is a compromised machine; the same bug here costs one directory.
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

echo "==> directories"
mkdir -p "$APP_DIR"/{api,web,data}
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# nginx runs as www-data and has to WALK to $APP_DIR/web. `o+x` grants exactly
# that — traverse, not list: www-data still cannot enumerate $APP_DIR, and
# cannot enter data/ at all. Without it nginx 403s on every request while
# looking, misleadingly, like a config problem.
chmod o+x "$APP_DIR"

# the database and the generated secret live here and nowhere else
chmod 750 "$APP_DIR/data"

echo "==> python environment"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
chown -R "$APP_USER:$APP_USER" "$APP_DIR/venv"

echo "==> secrets"
# The JWT secret is generated ONCE, into the data directory. Left to itself the
# app would write it beside its own code — which deploy.sh replaces — and every
# deploy would silently sign out every user in the middle of their work.
ENV_FILE="$APP_DIR/data/api.env"
if [[ ! -f "$ENV_FILE" ]]; then
  {
    echo "MAILPILOT_SECRET=$(openssl rand -hex 32)"
    echo "MAILPILOT_DB=$APP_DIR/data/mailpilot.db"
  } > "$ENV_FILE"
fi
chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo "==> firewall"
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

echo "==> nginx"
rm -f /etc/nginx/sites-enabled/default

echo
echo "Server ready. Now run deploy/deploy.sh from your machine."
