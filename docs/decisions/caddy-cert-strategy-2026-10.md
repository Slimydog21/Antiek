# Decision: origin certificate behind the tunnel is `tls internal`

**Date:** 2026-10-07 (Asia/Riyadh)
**Status:** accepted for the AWS production host; the Hetzner host keeps its
current certificate until it is retired (see Consequences)
**Closes:** the "ORIGIN CERT STORY — UNRESOLVED" comment in
`infrastructure/ansible/templates/Caddyfile.j2`; SPR-09 task 9
(`~/specs/antiek-v1-connect/SPR-09-infra-scale.md`), whose done-bar names
this record `caddy-cert-strategy-2026-09-20.md`. It was never written under
that name; this is the record that check is looking for.
**Lane:** `opus-aws-backbone-infra-20261007`

## Context

The only TLS client of Caddy is cloudflared on the same host. The tunnel
dials `https://127.0.0.1:443` with `originServerName: api.antiek.ai` and
`noTLSVerify: true` (`templates/cloudflared-config.yml.j2`). Caddy binds
loopback only, and ufw admits 22 alone; 80 and 443 have been closed to the
internet since the tunnel cutover (`setup.yml` §3, live `ufw status`,
prod-topology §3 [M]).

The Caddyfile carried no `tls` directive, so Caddy ran automatic ACME for
`api.antiek.ai`. Measured facts:

- **Production holds a Let's Encrypt (YE2) certificate for api.antiek.ai
  with notAfter 2026-12-12**, read from
  `/var/lib/caddy/.local/share/caddy/certificates/` on 2026-10-07
  (prod-topology §3 [M]). How it was first issued is not recorded.
- **A fresh host cannot get one at all.** The restore rehearsal on the
  orphan `Antiek-v1` (2026-10-07, defect D3 [M]): Let's Encrypt's HTTP-01
  probe for the public name went CF edge → the *production* tunnel →
  production Caddy, which answered 401 (it routes `/.well-known/*` to the
  API); TLS-ALPN-01 cannot pass a proxied record. With no certificate,
  `curl --resolve api.antiek.ai:443:127.0.0.1` got
  `tlsv1 alert internal error`. Behind the tunnel that is a 502 on every
  request. `noTLSVerify` does not help: it skips verification of a
  certificate, it cannot supply one.
- **The same path means production's own renewal fails** [I]. Caddy starts
  renewing about 30 days before expiry, around 2026-11-12, and the HTTP-01
  request would meet the same 401. Because the tunnel does not verify, an
  expired certificate would most likely keep serving [I], which is exactly
  the silent state the old comment warned about.

## Options

| Option | Verdict |
|---|---|
| Keep automatic ACME | Rejected. Fails on every new or rebuilt host (D3), so the AWS cutover and any DR rebuild would serve 502s. |
| **`tls internal`** (Caddy's local CA) | **Chosen.** No network, no account, no secret; issues at config load and renews locally. The client checks no certificate, so a locally issued one loses nothing. |
| Cloudflare Origin CA certificate | Workable but strictly more to carry: a 15-year private key to deliver and back up like the tunnel credential, for a client that does not verify it. Becomes the right answer only if cloudflared ever verifies the origin (below). |
| ACME DNS-01 | Rejected. Needs a Caddy build with a DNS provider module (the Cloudsmith apt package has none) and a Cloudflare token that can edit the zone, stored on the production box. |
| Plain HTTP on loopback | Rejected for now. Changes the cloudflared ingress, Caddy's listeners and auto-HTTPS behaviour across two templates other lanes own, to remove a TLS hop that costs nothing. |

## Decision

1. Caddy serves the origin with **`tls internal`** wherever this repo
   provisions a host from now on.
2. Selection, in `Caddyfile.j2`'s site block (one conditional hunk):
   - `caddy_origin_tls=internal` (set in `inventory.aws.ini.example`)
     renders `tls internal` directly;
   - otherwise the block renders `import /etc/caddy/origin-tls.d/*.caddy`.
     The AWS host's cloud-init writes
     `/etc/caddy/origin-tls.d/internal.caddy` containing `tls internal`
     (`infrastructure/terraform-aws/prod.tf`). This is load-bearing: the
     deploy workflow builds its own inventory with no host variables
     (`.github/workflows/deploy_backend.yml`, "Render the Ansible
     inventory"), so a variable alone would be dropped by the first CI
     deploy after cutover and the host would fall back to ACME and 502.
3. **Port 80:** nothing to close. ACME HTTP-01 is abandoned, `setup.yml`
   already admits only 22 (the 80/443 rules were removed as D10 in
   #3328), and Caddy's own :80 redirect listener stays on 127.0.0.1 through
   `bind`.

## Evidence that the hunk is safe for the running Hetzner host

With Caddy v2.11.3 (prod's version) [M]: the template rendered with the
default variables, on a host without `/etc/caddy/origin-tls.d/`, adapts to
JSON identical to the template without the import line (Caddy treats a glob
with no match as empty and logs a warning). With the snippet present, or with
`caddy_origin_tls=internal`, the adapted config gains exactly one TLS
automation policy, `subjects: [api.antiek.ai]`, `issuers: [internal]`, and
`caddy validate` passes for all three renders.
`tests/test_terraform_aws_invariants.py` repeats the comparison wherever
`caddy` is on PATH and checks the render either way.

## Consequences

- No external dependency remains for origin TLS on AWS. Local certificates
  are short-lived and renewed by Caddy without network access.
- Caddy will try to install its local root into the system trust store and,
  running as the `caddy` user, will log that it could not [A: Caddy treats
  this as non-fatal]. Nothing on the host needs to trust that root.
- If cloudflared is ever switched to verify the origin, `tls internal`
  stops being sufficient: either point `originRequest.caPool` at
  `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt` or move
  to an Origin CA certificate.
- **Hetzner deadline.** If the Hetzner host is still serving on 2026-11-12,
  write the same one-line snippet there
  (`install -D -m 0644 <(echo 'tls internal') /etc/caddy/origin-tls.d/internal.caddy && systemctl reload caddy`).
  It is reversible by deleting the file and reloading.

## Verification

- On the host: `openssl s_client -connect 127.0.0.1:443 -servername api.antiek.ai </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates`
  shows a "Caddy Local Authority" issuer.
- Through the tunnel, non-regression only:
  `curl -s --max-time 25 https://api.antiek.ai/health | python3 -c "import json,sys; print(json.load(sys.stdin)['build_sha'])"`
  prints a SHA. This passes before and after the change; it guards the
  path, it does not prove the mechanism.
- `grep -cE '^[[:space:]]*tls ' infrastructure/ansible/templates/Caddyfile.j2`
  returns 1.

## What would change this

- cloudflared verifying the origin (above).
- The origin becoming directly reachable without the tunnel, which would
  reopen 80/443 and make public ACME possible again. Not planned.
