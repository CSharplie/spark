# Auth

## Principles

- **No public signup.** The only way to create an account is the CLI, run
  by the app owner on the host (or inside the container). This removes an
  entire class of web-exposed attack surface (bot signups,
  registration abuse, etc.).
- Sessions use a JWT in an `HttpOnly` cookie: JavaScript can't read it,
  so an XSS bug can't exfiltrate the token (it could still act within the
  page, hence the CSP — see [01-architecture.md](./01-architecture.md#security-posture-owasp-oriented)).

## CLI account management (`spark-cli`, Typer)

```
uv run spark-cli create-user                                     # prompts for username and password
uv run spark-cli create-user --username alice                    # prompts for password (hidden, confirmed)
uv run spark-cli create-user --username alice --password '...'   # non-interactive (careful with shell history)
uv run spark-cli list-users                                      # id, username, active/inactive, created date
uv run spark-cli deactivate-user --username alice
uv run spark-cli reset-password --username alice [--password '...']
```

In Docker: `docker compose exec app spark-cli <command>`.

- Every command first runs `init_db()` (`SQLModel.metadata.create_all`):
  on an empty database it creates the full schema. Real migrations are
  still Alembic's job — a database created this way has no Alembic stamp
  (run `alembic stamp head` once before relying on `alembic upgrade`).
- `create-user` refuses an existing username.
- Passwords must be at least **12 characters** (checked by the CLI for
  `create-user` and `reset-password`), and are hashed with **Argon2id**
  (`argon2-cffi`) before storage; the plaintext is never stored or logged.
- `deactivate-user` sets `is_active = false`: the account can't log in and
  its existing sessions stop working on the next request. There is no
  reactivate command yet.
- `reset-password` doesn't revoke existing sessions (see [Logout](#logout)).

## Login flow (web)

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant D as SQLite

    B->>F: GET /login
    F-->>B: HTML form + Set-Cookie csrf_token
    B->>F: POST /login (username, password, csrf_token)
    F->>F: rate limit check (10 requests / 5 min; failed-password cooldown)
    F->>D: SELECT user WHERE username=?
    F->>F: argon2 verify (dummy hash if user unknown)
    alt CSRF ok, user active, password ok
        F->>F: issue JWT (HS256, sub=user_id, iat, exp)
        F-->>B: 303 → / (then 303 → /dashboard), Set-Cookie session=<jwt>
    else otherwise
        F-->>B: 401, form re-rendered with a generic error and a new CSRF token
    end
```

- **Generic error** on any failure ("Invalid username or password"), and
  an Argon2 verification is always performed — against a precomputed
  dummy hash for unknown usernames — so neither the message nor the
  response time reveals whether a username exists.
- **Rate limiting** (`app/core/rate_limit.py`): sliding window, in memory,
  **10 attempts per client IP per 300 s**; beyond that, `429`. Every
  `POST /login` counts, successful or not. State is per process and lost
  on restart. Behind a reverse proxy, the client IP is the proxy's unless
  Uvicorn is configured to trust forwarded headers.
- **Failed-password cooldown**: after **3 failed credential attempts from
  the same client IP within 5 minutes**, further login attempts from that
  IP receive `429` with a `Retry-After` header for **5 minutes**. Invalid
  CSRF submissions do not count, and a successful login clears that IP's
  failure count. This is also in-memory and per process.

### Session cookie

| Property | Value |
|---|---|
| Name | `session` |
| Content | JWT, HS256, signed with `SPARK_SECRET_KEY`; claims `sub` (user id), `iat`, `exp` |
| Lifetime | `SPARK_JWT_EXPIRE_MINUTES` (default 10080 = 7 days), also used as cookie `Max-Age` |
| Flags | `HttpOnly`, `SameSite=Lax`, `Secure` when `SPARK_ENV=production` |

## Protecting routes

`get_current_user` (`app/core/deps.py`) reads the `session` cookie,
verifies the JWT signature and expiry, and loads the user. It is a
dependency of every route except `/login`, `/healthz` and static files. A
missing/invalid/expired token or an inactive user raises
`NotAuthenticated`, which the app turns into `303 → /login` — for pages
and HTMX partials alike (HTMX follows the redirect and swaps in the login
page; there's no special client-side handling).

## CSRF

Because auth relies on a cookie the browser sends automatically, every
state-changing endpoint — `POST /login`, `POST /logout`, `POST /import`,
`POST /settings/city`, `POST /settings/temperatures/sync` — checks a
**double-submit token**:

1. Pages with forms (`/login`, `/dashboard`, `/dashboard/annual`,
   `/import`, `/settings`) generate a random token, render it in a hidden
   `csrf_token` field, and set it as the `csrf_token` cookie (`HttpOnly`,
   `SameSite=Lax`, `Secure` in production).
2. On submit, the field and the cookie must both be present and equal
   (`secrets.compare_digest`); otherwise `403` (`401` with a fresh token
   for login).
3. HTMX `POST`s that only swap part of the page don't rotate the token,
   so the forms still on screen stay valid.

The token is not tied to the session: opening another page rotates the
cookie, which can invalidate a form left open in another tab (reload it).
`GET` requests, including all HTMX partials, never mutate state and don't
need the token.

## Logout

`POST /logout` (CSRF-checked) deletes the `session` cookie and redirects
to `/login`. The JWT itself isn't revoked server-side (stateless): a
copied token stays valid until it expires, and a password reset doesn't
invalidate it either — acceptable for a personal app. Deactivating the
user does block it. If needed later, a `token_version` column on `user`
could invalidate all tokens on demand.
