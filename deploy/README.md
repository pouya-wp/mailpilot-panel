# Deploying MailPilot

Two scripts. `bootstrap-server.sh` prepares a machine once; `deploy.sh` ships
code every time after that.

```
your machine                     the VPS
────────────                     ───────
npm run build  ──── dist/ ─────▶ /opt/mailpilot/web    (nginx serves this)
backend/app    ─── tar|ssh ────▶ /opt/mailpilot/api    (uvicorn runs this)
                                 /opt/mailpilot/data   (never touched by a deploy)
```

Nothing listens on the public interface except nginx. The API is bound to
`127.0.0.1:8000` and reached only through the `/api/` proxy, so it never has to
be its own TLS terminator or static file server.

---

## First time

```bash
ssh root@187.77.141.155 'bash -s' < deploy/bootstrap-server.sh
```

Installs Python, nginx and ufw; creates a `mailpilot` system user that the API
runs as (**not** root); generates a JWT secret into `/opt/mailpilot/data/api.env`;
opens SSH, HTTP/HTTPS and 8080.

## Every time

```bash
./deploy/deploy.sh root@187.77.141.155
```

Runs the test suite first and refuses to deploy if it fails. Then builds,
copies both halves, installs dependencies, restarts, and polls `/api/health`
until it answers — so a deploy that breaks the app fails loudly instead of
leaving a dead server behind.

## This server is shared

`187.77.141.155` already runs **Traefik on 80/443**, fronting an **n8n** stack
and **PostgreSQL**, all of it up for weeks before this panel arrived. So nginx
here listens on **8080** and touches nothing else. Do not move it to 80: that
is what would take n8n down.

The panel is at **http://187.77.141.155:8080/**

When there is a domain, the better home for this is a Traefik route beside n8n
rather than a second web server — Traefik already terminates TLS and renews
Let's Encrypt certificates for everything else on the box.

## After the first deploy

Open `http://187.77.141.155:8080/`, sign in, and the setup wizard runs. That is
where the brand, the modules, the OpenAI key and the agent are configured.

The default owner account comes from `bootstrap()`:

- **email** `owner@example.com`
- **password** `mailpilot`

**Change it immediately.** Or create the install with your own credentials
before the first sign-in:

```bash
ssh root@187.77.141.155 \
  '/opt/mailpilot/venv/bin/python /opt/mailpilot/api/run.py --empty \
     --owner-email you@yourdomain.com --owner-password "a-long-passphrase"'
```

---

## Connecting Gmail

The agent sends through the customer's own Google account. That takes a Google
Cloud project, made once per deployment by whoever installs the panel — the
customer never sees it.

1. **console.cloud.google.com** → create a project (or reuse one).
2. **APIs & Services → Library** → enable the **Gmail API**.
3. **APIs & Services → OAuth consent screen** → External. Add these scopes,
   which are the only three the panel asks for:
   - `.../auth/gmail.send`
   - `.../auth/gmail.readonly`
   - `.../auth/userinfo.email`
   While the app is in *Testing*, add the customer's address under **Test
   users** — Google refuses anyone else. Publishing removes that limit and, for
   `gmail.readonly`, requires Google's verification review.
4. **Credentials → Create credentials → OAuth client ID → Web application.**
   Under **Authorised redirect URIs** paste exactly what the panel shows in
   Setup → Sending:

   ```
   https://<the panel's domain>/api/google/callback
   ```

   A single character out — `http` for `https`, a trailing slash, the IP
   instead of the hostname — and Google rejects the sign-in with
   `redirect_uri_mismatch`. This is the step that goes wrong.
5. Paste the client ID and secret into **Setup → Sending** in the panel. The
   secret is stored server-side and never comes back out.
6. Hand over. The customer opens **Settings → Sending**, presses *Connect a
   Google account*, and grants access to their own mailbox.

### What the panel can and cannot do with that grant

It can send as the customer and read their inbox to show replies. It cannot
delete mail, cannot change filters or forwarding, and cannot touch account
settings — `https://mail.google.com/` is deliberately not requested.

### Sending limits

Google's, not ours: roughly **500 recipients a day** on a personal account and
**2000** on Workspace. The sender paces itself and leaves the remainder queued
rather than pushing past a rejection, so a campaign larger than the daily limit
finishes over several days instead of burning the account's reputation in an
afternoon.

To stop a deployment sending at all — a staging copy pointed at real data, say
— set `MAILPILOT_SENDER=0` in `/opt/mailpilot/data/api.env` and restart. The
queue still fills; nothing drains it.

---

## HTTPS — read this before going live

The panel is currently served over **plain HTTP**. Sign-in credentials and the
session token cross the network in the clear, and anyone on the path can read
them. That is acceptable for a few hours of testing and not acceptable for a
customer.

Let's Encrypt will not issue a certificate for a bare IP address, so this needs
a domain name. Once you have one pointing at the server:

```bash
# 1. put the domain in the nginx config
ssh root@187.77.141.155 \
  "sed -i 's/server_name _;/server_name panel.yourdomain.com;/' \
   /etc/nginx/sites-available/mailpilot && nginx -t && systemctl reload nginx"

# 2. get a certificate — certbot rewrites the config and sets up renewal
ssh root@187.77.141.155 \
  'apt-get install -y certbot python3-certbot-nginx && \
   certbot --nginx -d panel.yourdomain.com --redirect --agree-tos -m you@yourdomain.com'
```

Until then, treat the deployment as a staging environment and do not put real
customer contacts in it.

---

## Operating it

```bash
# logs, live
ssh root@187.77.141.155 'journalctl -u mailpilot-api -f'

# restart just the API
ssh root@187.77.141.155 'systemctl restart mailpilot-api'

# back up everything that matters — the database and the deployment config
ssh root@187.77.141.155 'sqlite3 /opt/mailpilot/data/mailpilot.db ".backup /tmp/mp.db"' \
  && scp root@187.77.141.155:/tmp/mp.db ./backup-$(date +%F).db
```

Back up with `.backup`, not `cp`: copying a SQLite file while the API is
writing to it can capture a torn page, and you will not discover that until you
try to restore.

## What is deliberately not deployed

- **The voice server** (`server/tts.mjs`). It downloads a ~90MB speech model
  and the support agent falls back to the browser's own speech synthesis
  without it. Add it later if the voice matters.
- **Demo data.** A fresh install comes up empty — one owner account and
  nothing else. `run.py --demo` fills it, and should never be run on a machine
  a customer will see.

## Scaling past this

One uvicorn worker, one SQLite file. That is genuinely fine for a single
customer's mailing list, and it is the reason the service file pins
`--workers 1`: concurrent writers against one SQLite file is how they get
corrupted. Growing past it means moving to Postgres, not adding workers.
