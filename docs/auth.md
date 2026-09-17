# Authentication

PromPilot is open by default: anyone who can reach the port can use it. Set a
password and it isn't.

```
AUTH_PASSWORD=change-me         # enables the sign-in screen
AUTH_API_TOKEN=…                # optional: scripts send  Authorization: Bearer <token>
AUTH_SESSION_TTL=30d            # how long a sign-in lasts
AUTH_COOKIE_SECURE=true         # set behind HTTPS so the cookie is HTTPS-only
SECRET_KEY=…                    # signs sessions and encrypts stored passwords
```

- Sessions are signed, HttpOnly, SameSite=Lax cookies; nothing is stored
  server-side, so restarts don't sign anyone out.
- Every `/api` route requires a session or the API token, except
  `/api/auth/*` and `/healthz`.
- Five wrong passwords from one address pause sign-in for 30 seconds.
- One shared password, one role. For per-user accounts put PromPilot behind
  an authenticating proxy (oauth2-proxy, Authelia, your ingress) — OIDC
  support is planned.

## The secret key

`SECRET_KEY` signs session cookies and encrypts project Prometheus passwords
in the database. Leave it unset and PromPilot generates one on first start
and keeps it in `DATA_DIR/secret.key` (mode 600). Set it explicitly when you
run more than one replica or want to control rotation. If the key is lost,
stored project passwords can't be decrypted: sign in, open each project and
re-enter its password.

Instances created before 0.2 held passwords in plain text; they are
encrypted automatically on the first start with 0.2.
