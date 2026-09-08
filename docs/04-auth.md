# Auth

## Principles

- **No public signup.** The only way to create an account is the CLI, run
  locally by the app owner. This removes an entire class of web-exposed
  attack surface (bot signups, credential-stuffing registration, etc.).
- Sessions use a JWT in an `httpOnly` cookie — never accessible to
  JavaScript, so an XSS bug can't exfiltrate it.

## CLI account management (`spark-cli`, Typer)

```
uv run spark-cli create-user --username alice          # prompts for password (hidden input)
uv run spark-cli create-user --username alice --password '...'   # non-interactive (careful with shell history)
uv run spark-cli list-users
uv run spark-cli deactivate-user --username alice
uv run spark-cli reset-password --username alice
```

- `create-user` refuses to run if the username already exists.
- Password is hashed with **argon2id** (`argon2-cffi`) before being stored;
  the plaintext is never written to disk or logged.
- Minimal password policy enforced client-side (CLI prompt) and
  server-side (shared validator): length >= 12.

## Login flow (web)

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant D as SQLite

    B->>F: GET /login
    F-->>B: HTML form (+ CSRF token)
    B->>F: POST /login (username, password, csrf_token)
    F->>D: SELECT user WHERE username=?
    F->>F: argon2.verify(password, hash)
    alt valid
        F->>F: issue JWT (sub=user_id, exp=+7d)
        F-->>B: Set-Cookie session=<jwt>; HttpOnly; Secure; SameSite=Lax
        F-->>B: 303 redirect to /dashboard
    else invalid
        F-->>B: 401, re-render form with generic error
    end
```

- Generic error message on failure ("invalid username or password"),
  never revealing whether the username exists.
- Basic rate limiting on `/login` (e.g. in-memory token bucket per IP,
  fine for a personal app) to slow down brute force.

## Protecting routes

- A FastAPI dependency (`get_current_user`) reads the cookie, verifies the
  JWT signature/expiry, loads the user, and is applied to every
  dashboard/import route. Missing/invalid token → redirect to `/login`
  (for full page GETs) or `401` (for HTMX partial fetches, handled
  client-side to redirect).

## CSRF mitigation

Because auth relies on a cookie that the browser sends automatically,
state-changing endpoints (`POST /login`, `POST /logout`, `POST /import`)
require:
1. `SameSite=Lax` on the cookie (blocks most cross-site POSTs), and
2. a per-session CSRF token rendered in every form and required on submit
   (double-submit pattern), checked before processing the request.

`GET` requests (including HTMX partials that only read data) never
mutate state, so they don't need the CSRF token.

## Logout

`POST /logout` clears the cookie (`Max-Age=0`) — JWT itself isn't
server-side revoked (stateless), acceptable given the short expiry and
personal-app threat model. If needed later, a `token_version` column on
`user` can be added to invalidate all existing tokens on demand.
