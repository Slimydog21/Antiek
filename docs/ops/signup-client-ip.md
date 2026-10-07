# Signup client-IP attribution

The signup limiter uses ASGI `request.client.host`. The application does not
read `CF-Connecting-IP`, `X-Real-IP` or `X-Forwarded-For` directly.

The production path is Cloudflare edge → cloudflared → loopback Caddy → loopback
Uvicorn. Caddy binds `127.0.0.1` and trusts only `127.0.0.1/32` for the edge's
`CF-Connecting-IP`. It overwrites both upstream IP headers with its parsed
`{client_ip}`. Uvicorn explicitly trusts forwarded headers only from
`127.0.0.1`. An untrusted peer's headers cannot select another limiter bucket.
Local origin processes are inside this proxy trust boundary; IP attribution
never establishes an account or grants private access.

Caddy's [trusted proxy and client-IP settings](https://caddyserver.com/docs/caddyfile/options#trusted-proxies)
provide the parsed address. `trusted_proxies_strict` requires Caddy 2.8 or newer.
Cloudflare documents the [edge header and Worker exceptions](https://developers.cloudflare.com/fundamentals/reference/http-headers/#cf-connecting-ip).
This contract assumes visitor IP headers are enabled and same-zone Workers do
not replace visitor attribution. Root must verify the active zone configuration.

Before enabling public signup, Root must validate and activate the rendered
Caddy configuration and matching service arguments through normal deployment.
The previous `{remote_host}` forwarding groups tunnel visitors under loopback;
updating application code alone does not repair that configuration.

The source tests execute the installed Uvicorn middleware with trusted and
untrusted ASGI peers, IPv4/IPv6 visitors and forged headers. They also check the
template contract. They do not execute Caddy or establish live edge attribution.
The rollout needs an actual controlled external request with forged forwarding
headers that cannot renew its IP budget, and an independent external visitor
whose budget remains separate. Missing parsed attribution stays in the
loopback bucket; do not enable signup while that degradation remains observed.

Keep mailbox links, claim secrets, cookies, provider keys and addresses out of
the deployment transcript. Report only configuration identity, status, limiter
behavior and value-free account phases.
