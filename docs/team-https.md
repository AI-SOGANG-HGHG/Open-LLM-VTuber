# Team-only HTTPS access

Use a single public web-service port, TCP 443, for both the Studio and its
WebSocket conversation connection. The existing application stays on
`127.0.0.1:12393`. Caddy authenticates every request before forwarding it,
including the WebSocket upgrade. It removes the login Authorization header
before forwarding to the application. The backend keeps using its private
Gemini configuration.

| Endpoint | Access |
|---|---|
| TCP 443 | Public HTTPS, protected by a team username and password |
| TCP 12393 | Loopback application, accessed through Caddy |
| TCP 80 / UDP 443 | Not used by this gateway configuration |

SSH administration is separate from these web-service ports.

## Hostname and login

An owned domain is optional for the initial team deployment. An IP-based DNS
hostname from [sslip.io](https://sslip.io/) resolves to the IP embedded in its
name. This server's initial hostname is `vtuber-3-35-188-221.sslip.io`. This is
a third-party development hostname, not a domain owned by the team. If the
server's public IP changes, the address and certificate configuration need
updating. A team-owned domain can replace it later.

The browser prompts for the team username and password. This is a shared
gateway login, not an implementation of individual application accounts or
per-user data permissions. On this server, the generated login information
is in `private/web-access.env`, mode 600, inside a mode-700 directory. This
directory is ignored by Git and Docker. It is separate from the Gemini `.env`.
Share the login only with the intended team members.

The root-only `/etc/open-llm-vtuber-gateway/access.env` contains:

```dotenv
VTUBER_HOSTNAME=vtuber-3-35-188-221.sslip.io
VTUBER_USERNAME=team
VTUBER_PASSWORD_HASH=replace_with_a_caddy_bcrypt_hash
```

Generate a hash interactively with `caddy hash-password --algorithm bcrypt`.
Do not put a plaintext password in the Caddyfile or in shell command arguments.
The service reads this root-owned file; the Caddyfile contains only variable
placeholders. Restart the gateway after changing its environment file.

## Service

Install the Caddy binary separately; this server uses official release 2.11.9,
verified against its SHA-512 checksum manifest and GitHub SHA-256 digest.
Use the dedicated unprivileged `vtuber-gateway` system user, with home
`/var/lib/open-llm-vtuber-gateway` and login shell `/usr/sbin/nologin`.

Install `deploy/Caddyfile` as `/etc/open-llm-vtuber-gateway/Caddyfile` and
`deploy/open-llm-vtuber-gateway.service` in `/etc/systemd/system/`.
The unit grants only the capability needed to bind port 443, cannot access
home directories, and stores its certificates under its own state directory.

```bash
sudo systemd-analyze verify /etc/systemd/system/open-llm-vtuber-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now open-llm-vtuber-gateway.service
sudo systemctl status open-llm-vtuber-gateway.service
```

Caddy uses Let's Encrypt's TLS-ALPN challenge on 443. HTTP certificate
challenges, HTTP redirects, and HTTP/3 are disabled, so neither TCP 80 nor
UDP 443 is required. Certificate issuance and renewal require public TCP 443
to reach this server. See [Caddy's certificate validation documentation](https://caddyserver.com/docs/automatic-https#acme-challenges).

## AWS firewall and verification

Allow inbound HTTPS/TCP 443 to the instance in its AWS firewall, in addition
to the server's listener. For public certificate validation, IPv4 source
`0.0.0.0/0` is supported; team access is checked by the gateway login.
Do not expose the backend port for this configuration.

For EC2, edit the instance's security-group inbound rules. For Lightsail,
use the instance's Networking / IPv4 firewall settings. The current server's
role was denied `DescribeInstances` and an `AuthorizeSecurityGroupIngress`
permission check with `DryRun`, so firewall changes cannot be performed with
that role. A local listening port alone does not prove external access.

Once the public certificate is issued, run:

```bash
.venv/bin/python tools/check_gateway.py
```

This verifies trusted HTTPS; rejection of missing/wrong credentials; the
authenticated Studio, runtime and model resources; and anonymous rejection
plus authenticated initialization of the real WebSocket. It makes no model
API calls. The same checks also passed against an isolated loopback HTTPS
instance with a dedicated test CA during setup.

On 2026-11-15, after the user added the AWS HTTPS rule, all 12 checks passed
through the public hostname with normal certificate verification. The gateway
had obtained its public certificate through the production ACME endpoint.
A separate Chromium check used the public URL with certificate verification
enabled: TLS 1.3, secure browser context, successful team authentication,
the Studio's embedded live WebSocket connection, and Mao's loaded Live2D canvas
with rendered frames and no JavaScript errors. It made zero model calls.
The listener check confirmed public TCP 443 and loopback-only TCP 12393,
with no port-80 listener. Physical microphone/speaker output remains unverified.
