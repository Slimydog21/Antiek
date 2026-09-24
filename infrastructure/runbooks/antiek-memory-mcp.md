# Antiek Memory MCP — deployment gate and client registration

**Status, 2026-09-24: multi-account registration blocked.** The executable
MCP server is a stdio process (`python -m tools.antiek_memory`). Its scoped
read/write containment is proposed in [PR #3436](https://github.com/Slimydog21/Antiek/pull/3436),
not established on a deployed revision. The repository does not contain an
SSH-principal-to-account binding or an HTTP MCP transport. Do not register a
remote client for private data using a caller-selected
`ANTIEK_MEMORY_OWNER` value.

## Implemented surfaces

| Surface | Source | Present behavior |
|---|---|---|
| Stdio JSON-RPC process | `tools/antiek_memory/__main__.py`, `server.py` | Reads graph data in a process bound to the launch environment's owner value. That environment value is not authentication. |
| Public tool-description manifest | `GET /.well-known/mcp-tools.json` in `interfaces/research/api/app.py` | Publishes tool descriptions and hashes. It does not serve MCP calls. |
| HTTP MCP transport | None | `/mcp` and OAuth/session-to-MCP adapters are not implemented here. |
| Production service unit | `infrastructure/ansible/templates/antiek.service.j2` | Starts the HTTP Uvicorn app, not a stdio MCP server. |

The manifest hash lets a client compare descriptions **if that client
implements the comparison**. This repository does not prove that Claude
Desktop, ChatGPT, or another client fetches the manifest, compares hashes,
or terminates on drift. A successful manifest fetch is not a successful MCP
connection or authorization check.

The proposed stdio patch in PR #3436 binds private reads to the process
owner, filters public search by class and current body rights, and refuses
book bodies and attribution writes until entitlement and investigation
authority can be joined. It does not turn the launch environment into a
verified account identity. See
[`docs/handoff/r15-mcp-auth-boundary-20260924.md`](../../docs/handoff/r15-mcp-auth-boundary-20260924.md)
for its exact scope.

## Required SSH launch boundary

The former Claude Desktop and CLI recipes logged in as `root` and placed
`ANTIEK_MEMORY_OWNER=<your-user-id>` in a caller-controlled remote command.
A client with that SSH key could choose another person's owner ID before
starting stdio MCP. Those recipes are withdrawn; do not use or copy them.

To make SSH stdio suitable for distinct accounts, implement and review all
of the following on the server before publishing a client configuration:

1. Give each authorized account a distinct SSH key or certified principal.
   Maintain the principal-to-`owner_user_id` mapping in a server-controlled
   file or key restriction that the client cannot edit.
2. Use a dedicated, unprivileged service identity with only the graph
   access needed for MCP. Disable shell, PTY, agent/port forwarding, and
   arbitrary commands for the connector key. A forced command must derive
   the owner from the authenticated key/principal mapping and set
   `ANTIEK_MEMORY_OWNER` itself. It must ignore client environment requests,
   command arguments, and `SSH_ORIGINAL_COMMAND` as owner evidence.
3. Pin `ANTIEK_DUCKDB_PATH` in server-controlled configuration to the
   authorized live graph path; reject an unset or different path before
   launch. The HTTP unit sets `{{ antiek_state_dir }}/antiek.duckdb`, whereas
   the standalone launcher otherwise falls back to
   `~/.antiek/research_graph.duckdb`.
   Verify the connector opens the intended graph, not an empty or stale one.
   Launch the exact reviewed code revision and verify `tools` is installed
   in that environment; `pyproject.toml` does not put it in the explicit
   wheel package list.
4. Prove the connector starts without schema writes and can read while the
   live HTTP writer is active. The current launcher calls
   `init_database_at_path`, whose failed read-only probe can enter a write
   path. A separate DuckDB process may also fail to open the file while the
   HTTP process owns a read-write handle. In a local DuckDB 1.4.4 two-process
   probe on 2026-09-24, the read-only open failed with a conflicting file
   lock while the writer held the graph file; this is not a production test.
   If either occurs, change the architecture (for example, a
   same-process authenticated adapter or a
   declared read-only snapshot with freshness controls) before registration.
   Do not loosen DB privileges or copy a private live file to work around it.
5. Exercise two separately authenticated accounts through the actual SSH
   connector. Each may read its own private note; each must get the same
   generic denial for the other's note and citation. Attempt to override
   the owner in the remote command, environment, and JSON-RPC arguments;
   none may change the bound owner. Test an unmapped and revoked key.
6. Repeat the public-search rights negatives (T3/NC license stamped as T1,
   missing arXiv linkback, takedown) and book/attribution denials on that
   serving revision. Bound and measure candidate-scan latency under a
   common query before declaring the public search operational.

Only after this gate passes should a client registration use a server-issued
fixed connector command. The owner must not be a placeholder the client
fills in. Keep the executable private to trusted local operators until then.

## HTTP catalog path

ChatGPT-style remote HTTP registration requires a new `/mcp` transport and
an authentication adapter. The existing HTTP signed-session middleware
and `distinct_signed_owner` mapper are possible server-side ingredients;
they do not currently authenticate stdio JSON-RPC. The present stateless
session-cookie verifier does not by itself revoke one issued session.
Define the HTTP tool, resource, and streaming protocol contract, then prove
two signed accounts, expiry, explicit revocation, and wrong-owner
denials on the integrated adapter before listing a catalog URL. Do not register `https://api.antiek.ai/mcp` as if it
already existed.

## Verification and failures

- `GET /.well-known/mcp-tools.json` returning hashes proves only that the
  HTTP app generated a manifest. A hash mismatch is meaningful only when
  the actual client verifier detects and rejects it.
- A private `tools/call` denial from stdio is governed by the process-bound
  owner and current handler checks. An HTTP auth cookie or service token
  is not consumed by this executable.
- `systemctl status antiek` checks the HTTP Uvicorn service. It does not
  establish that an MCP stdio client connected or passed its authorization
  tests.
- `python -m tools.antiek_memory.server` only imports the module; the
  executable entry point is `python -m tools.antiek_memory`.

## Source references

- `tools/antiek_memory/__main__.py` — executable, owner environment read,
  and handlers.
- `tools/antiek_memory/server.py` — JSON-RPC dispatch and process binding.
- `interfaces/research/api/app.py` and
  `interfaces/research/api/account_memory_identity.py` — existing HTTP
  session authentication and owner mapping, not wired to stdio MCP.
- `docs/master-product-spec.md` §13.8 — intended product behavior; this
  runbook distinguishes that intent from implemented and deployed evidence.
