# Team login over HTTPS

Studio is available at the public HTTPS address through TCP 443. Visitors see
its existing landing page and enter the team's username and password in the
page itself. Caddy handles TLS and forwards to the loopback application;
Python verifies login and protects HTTP APIs, history, models and WebSockets.
There is no HTTP Basic Authentication prompt.

| Endpoint | Access |
|---|---|
| TCP 443 | Public HTTPS; login page/assets public, application session required for private routes |
| TCP 12393 | Loopback application; server-side authentication still enforced |
| TCP 80 / UDP 443 | Not used by this gateway configuration |

SSH administration is separate from these web-service ports.

## Account and sessions

This development deployment uses one shared team account. Individual accounts,
signup, a character database and per-user data permissions are separate work.
Existing character settings remain in each browser. The team login details
are in `private/web-access.env` (mode 600 in a mode-700 ignored directory).
Model API keys are stored in the separate `.env`. Do not put either password or key in Git.

Successful login sets an opaque `__Host-studio_session` cookie with Secure,
HttpOnly, SameSite=Strict, path `/`, and an eight-hour lifetime. Sessions are
owned by the running server; refreshing restores login, while a server restart
requires signing in again. Passwords and session tokens are not put in browser
storage. Logout revokes the session, closes its active WebSockets, and updates
other open Studio tabs. There is a maximum of 128 sessions. Login attempts are
limited per client and globally, and expensive password checks are bounded.

## Private server configuration

Copy `config_templates/studio-auth.example.env` to `private/studio-auth.env`,
mode 600, and configure:

```dotenv
STUDIO_AUTH_ENABLED=true
STUDIO_AUTH_USERNAME=team
STUDIO_AUTH_PASSWORD_HASH=replace_with_a_bcrypt_hash
STUDIO_PUBLIC_ORIGIN=https://vtuber-3-35-188-221.sslip.io
```

Use `caddy hash-password --algorithm bcrypt` interactively to produce the hash.
The launcher reads the file as data, not shell code. Use the exact public HTTPS
origin, without a path. The production user service sets
`STUDIO_AUTH_REQUIRED=true` and fails closed if authentication is missing.
Standalone local runs without auth configuration retain the explicitly labeled
loopback-only preview flow. The private login file is ignored by Git and Docker.

The login page and its exact required assets are public. `/auth/session`
reports login state; `/auth/login` and `/auth/logout` use same-origin POSTs.
All other HTTP and WebSocket access requires a valid server session. Origin
checks also protect credentialed GET requests, mutations, and WebSocket
handshakes from other origins. The server does not accept browser storage or
cached Basic credentials as proof of login.

Restart the backend after changing its private auth settings:

```bash
systemctl --user restart open-llm-vtuber.service
```

## HTTPS gateway

This server uses Caddy 2.11.9, installed from its official release with checksum
verification. A dedicated `vtuber-gateway` system account runs the restricted
`deploy/open-llm-vtuber-gateway.service`. It cannot read home directories; TLS
state is stored under `/var/lib/open-llm-vtuber-gateway`.

Install `deploy/Caddyfile` as `/etc/open-llm-vtuber-gateway/Caddyfile`. The
root-only `/etc/open-llm-vtuber-gateway/access.env` supplies
`VTUBER_HOSTNAME=vtuber-3-35-188-221.sslip.io`. The proxy no longer uses a
username/password hash. Its service definition belongs in `/etc/systemd/system/`.

```bash
sudo systemd-analyze verify /etc/systemd/system/open-llm-vtuber-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now open-llm-vtuber-gateway.service
sudo systemctl reload open-llm-vtuber-gateway.service
```

Caddy uses the TLS-ALPN challenge on 443 for public certificate issuance and
renewal. HTTP challenges, HTTP redirects and HTTP/3 are disabled. See
[Caddy's certificate documentation](https://caddyserver.com/docs/automatic-https#acme-challenges).

The temporary hostname uses [sslip.io](https://sslip.io/), which resolves the IP
embedded in the name. If the public IP changes, update the address, gateway
hostname, backend public origin, and private login URL. A team-owned domain can
replace this development hostname later.

## AWS and checks

AWS must allow inbound HTTPS/TCP 443, for example IPv4 source `0.0.0.0/0`.
Team access is verified by the application. Keep port 12393 on loopback. The
instance role was denied both instance inspection and the DryRun permission
check for adding a security-group rule, so AWS console access was needed.

```bash
.venv/bin/python tools/check_gateway.py
.venv/bin/python -m unittest discover -s tests
# Optional Playwright environment, with Chromium and python-dotenv:
python tests/browser/studio_login.py
```

The gateway check uses normal certificate verification and checks the public
login page, wrong credentials, secure cookie sessions, private resources,
anonymous/cross-origin WebSocket rejection, authenticated initialization, and
logout revocation of both a copied cookie and an active socket. It makes no
model calls. The browser check covers form login, forged sessionStorage,
refresh, mobile layout, Mao Live2D/WebSocket, and cross-tab logout, also with
zero model calls. Screenshots and reports are saved under `tmp/` without
passwords or cookie values. Physical microphone/speaker output is a separate
user-device check.
