#!/usr/bin/env bash
#
# The server half of a deploy. Travels up inside the same tarball as the code
# and is run once it lands, so the whole deploy is ONE ssh connection.
#
# Reads three variables from the environment, set by deploy.sh:
#   DOMAIN   the hostname Traefik should route
#   NAME     the container name
#   APP_DIR  where everything lives
set -euo pipefail

: "${DOMAIN:?DOMAIN not set}"
: "${NAME:?NAME not set}"
: "${APP_DIR:?APP_DIR not set}"

mkdir -p "$APP_DIR/data"

# Google's redirect URI has to be an address a browser can reach. Behind
# Traefik the request's own host is the container's, so the public origin is
# passed in rather than guessed.

# One env file, generated once, holding the JWT signing key. Regenerating it on
# every deploy would invalidate every session that was in flight.
ENV_FILE="$APP_DIR/data/api.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "MAILPILOT_SECRET=$(openssl rand -hex 32)" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# MAILPILOT_DB must never come from this file, and an older install has it.
#
# Back when the API ran on the host under systemd, the env file quite correctly
# said /opt/mailpilot/data/mailpilot.db. Inside a container that same path is
# not the volume — the volume is mounted at /data — so it resolves to the
# image's own writable layer, and `docker rm -f` on the next deploy takes the
# database with it. The path is identical, the filesystem is not, and the panel
# comes back up cheerfully reporting "created an empty installation".
#
# The image sets MAILPILOT_DB=/data/mailpilot.db. Anything in the env file
# overrides it, so the line is stripped here rather than trusted.
if grep -q '^MAILPILOT_DB=' "$ENV_FILE"; then
  echo "  removing a stale MAILPILOT_DB from api.env (it pointed off the volume)"
  grep -v '^MAILPILOT_DB=' "$ENV_FILE" > "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

echo "  building image..."
docker build -q -t "$NAME:latest" "$APP_DIR/build" >/dev/null

# Replaced, not restarted: the image changed, so the old container is gone.
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -e "MAILPILOT_PUBLIC_URL=https://$DOMAIN" \
  -v "$APP_DIR/data:/data" \
  -p 127.0.0.1:8000:8000 \
  --label traefik.enable=true \
  --label "traefik.http.routers.mailpilot.rule=Host(\`$DOMAIN\`)" \
  --label traefik.http.routers.mailpilot.entrypoints=websecure \
  --label traefik.http.routers.mailpilot.tls.certresolver=letsencrypt \
  --label traefik.http.services.mailpilot.loadbalancer.server.port=8000 \
  "$NAME:latest" >/dev/null

# Prove it came up rather than assuming: a container that exits a second later
# still counts as "started" to `docker run`.
for _ in $(seq 1 15); do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "  container is answering."
    # Cheap, and it is the check that would have caught the volume bug: the
    # file the app opened must be the one on the mount, not one inside the
    # container that the next deploy deletes.
    if ! docker exec "$NAME" test -s /data/mailpilot.db; then
      echo "  WARNING: /data/mailpilot.db is missing — the database is NOT on the volume." >&2
    fi
    docker image prune -f >/dev/null 2>&1 || true
    exit 0
  fi
  sleep 2
done

echo "container did not answer. Recent log:" >&2
docker logs --tail 40 "$NAME" >&2
exit 1
