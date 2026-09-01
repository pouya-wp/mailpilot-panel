# MailPilot API

Python backend for the admin panel. FastAPI + SQLite, no ORM.

```bash
cd backend
pip install -r requirements.txt
python run.py                  # http://127.0.0.1:8000/api
```

Interactive docs: **http://127.0.0.1:8000/api/docs**

Sign in with any seeded account — they all share one password:

| email | role |
|---|---|
| `pouya@acme.io` | owner |
| `sara@acme.io` | admin |
| `noah@acme.io` | editor |
| `mia@acme.io` | analyst |

Password: `mailpilot`

```bash
python run.py --reload         # restart on edit
python run.py --reseed         # drop every table and seed again
python run.py --port 9000
python -m pytest tests -q      # 58 tests, no mocks
```

---

## Why it looks like this

**Three dependencies.** `fastapi`, `uvicorn`, `pydantic[email]`. Passwords use
`hashlib.scrypt` and JWTs are signed with `hmac`, both from the standard
library — so there is no `passlib` (unmaintained, and broken against modern
bcrypt on Python 3.13) and no `python-jose`. The database is stdlib `sqlite3`.
Fewer moving parts is the whole point: the thing has to start and work on a
machine that has never seen it before.

**No ORM.** The schema is fixed and hand-shaped, every query is a page's worth
of columns, and the database is one file. SQLAlchemy would add a dependency, a
migration story and a lazy-load footgun without removing real work. What
`db.py` *does* provide is the part that hand-written SQL actually needs:
per-request connections with foreign keys and WAL genuinely enabled, dict-like
rows, and helpers that only ever bind parameters.

**Every name is bilingual.** Campaign names, agent roles and contact names are
*content*, not interface strings, so they do not belong in the frontend's i18n
dictionaries — but the API must not pick a language on the client's behalf
either. So every human-readable field comes back as `{"en": …, "fa": …}`,
matching the `loc(value, lang)` helper the React app already uses. That is what
keeps the language switch instant and client-side.

**The AI routes are a deterministic stub.** `/ai/compose` and `/ai/segment`
have exactly the shape a real model call would have — same request, same
response, same failure modes (credit exhaustion, guardrail violations, a paused
agent) — but the text comes from a table. The frontend can be built and tested
against it with no API key, no cost and no flakiness. Swapping in a real
provider touches one function per route: `_draft` and `_compile` in
`app/routers/ai.py`.

---

## What is enforced server-side

These are the rules a client must not be trusted to remember, so none of them
live in the UI:

- **Campaign state machine.** draft → scheduled → running → sent. Pausing a
  campaign that is not running is `409`, not a silent no-op. A campaign with no
  audience cannot send.
- **Opt-out consistency.** Unsubscribing writes to the contact *and* the
  suppression list in one transaction, and a suppressed address cannot be
  re-added by an import. The two can never disagree.
- **Agent autonomy.** An agent set to `suggest` or `approve` cannot reach a
  customer unattended, whatever the caller asks for. `/agents/{id}/run` is
  always a dry run.
- **Experiment thresholds.** A variant cannot be promoted below 95% confidence.
  Calling noise is the most expensive mistake this product can make.
- **Segment rules.** Field names are matched against an allow-list before they
  reach SQL, so a rule can never name an arbitrary column.
- **Owner floor.** A workspace always keeps at least one active owner; the
  paths that would remove the last one refuse.
- **Search wildcards.** `%` and `_` in a query are escaped, so searching for
  "20%" finds the one campaign that says 20% rather than everything.

## Authentication

Two credentials, deliberately not interchangeable:

- **Bearer JWT** — a signed-in human. Carries a role; role gates everything.
  Refresh tokens are stored hashed and are single-use: refreshing rotates the
  token, and replaying a burnt one revokes the whole family.
- **`X-API-Key`** — a machine. Carries scopes (`analytics:read`,
  `contacts:rw`, `*`), never a role, and is refused outright on anything
  human-only such as `/team`. A key that could do everything an owner can is a
  key that turns one leaked secret into a total compromise.

Keys are stored as a SHA-256 hash. The plaintext is returned exactly once, at
creation, and cannot be recovered.

## Layout

```
backend/
  app/
    config.py      settings from env, working defaults
    db.py          sqlite layer + full schema
    security.py    scrypt passwords, HS256 JWT, API keys
    domain.py      bilingual helpers, role matrix, metrics
    deps.py        who is calling, and may they
    serial.py      row -> JSON, shaped for the React app
    schemas.py     request bodies (pydantic)
    seed.py        the same records the frontend mock ships
    main.py        app, CORS, error shape, /health, /meta
    routers/
      auth.py        login, refresh, me, permissions
      campaigns.py   list, detail, lifecycle
      audience.py    contacts, segments, suppression, CSV import
      agents.py      agents, inbox, experiments, journeys
      analytics.py   dashboard, breakdowns, SSE live stream, deliverability
      workspace.py   team, billing, domains, developers, settings, activity
      ai.py          composer, segment builder
  tests/test_api.py  58 end-to-end tests
```

## Connecting the frontend

The API is mounted at `/api`, which the Vite dev server already proxies
(`vite.config.js` → `proxy: { '/api': … }`). Point that proxy at port 8000:

```js
proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } }
```

Then the client calls `/api/...` in both dev and production with no
environment-specific base URL. CORS is configured for ports 4300/4301/5173 as
well, for the case where the SPA is served from somewhere else.

IDs match the frontend mock verbatim (`c-401`, `nova`, `vip`, `t-1`, …), so the
two data sources can be diffed record by record while the migration is in
flight.
