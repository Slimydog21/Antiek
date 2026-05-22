# Antiek Memory MCP — deployment + client registration

**Status: ready to deploy as of 2026-05-22.** The MCP server code,
the rug-pull defense manifest, and the well-known endpoint are all
live on `main`. What remains is the operator-side step of
registering the server with the MCP clients that should connect
(Claude Desktop, ChatGPT MCP catalog, local CLIs, etc.).

For the master-spec background see §13.8. For the server
implementation see `tools/antiek_memory/`.

---

## What the substrate exposes

| Surface | Where |
|---|---|
| MCP stdio server (JSON-RPC over stdin/stdout) | `tools/antiek_memory/server.py` |
| Tool description signing | `tools/antiek_memory/signing.py` |
| `.well-known/mcp-tools.json` manifest | `GET https://api.antiek.ai/.well-known/mcp-tools.json` |

The manifest is public by design (no auth). MCP clients fetch it
on first connect, verify each tool's `description_sha256` matches
the hash they compute locally from the tools/list response, and
**terminate the session if any hash drifts**. This is the
Invariant-Labs rug-pull defense from §13.8.

---

## Registering with Claude Desktop

1. Open Claude Desktop → **Settings** → **Developer** → **Edit config**.
2. Add an entry to `mcpServers`:

```json
{
  "mcpServers": {
    "antiek-memory": {
      "command": "ssh",
      "args": [
        "-i", "/Users/<you>/.ssh/antiek_ed25519",
        "root@167.235.202.98",
        "cd /opt/antiek && /opt/antiek/.venv/bin/python -m tools.antiek_memory.server"
      ]
    }
  }
}
```

Replace `<you>` with your username. The Claude Desktop client
will spawn the server over SSH when it needs to call a tool.

3. Restart Claude Desktop.
4. In a conversation, ask Claude to "search my private notes for X".
   Claude should call the `search_personal` tool; the response
   surfaces in the conversation.

### Verifying the rug-pull defense

After Claude Desktop spawns the server, it fetches
`https://api.antiek.ai/.well-known/mcp-tools.json` and checks each
tool's `description_sha256`. To confirm:

```bash
curl -s https://api.antiek.ai/.well-known/mcp-tools.json | jq .
```

Expected output: a `{version, server, tools[]}` object with one
entry per canonical tool. The four canonical tools per §13.8 are:

- `search_personal`
- `search_public`
- `cite_source`
- `record_attribution`

If a future code change adds or modifies a tool, the manifest hashes
change and Claude Desktop's next session termination loudly with a
manifest mismatch — by design.

---

## Registering with ChatGPT MCP catalog

1. OpenAI's MCP catalog is at https://platform.openai.com/mcp (as of
   2026-05-22; check the docs for the current URL).
2. Add a new MCP server entry:
   - Server name: `Antiek Memory`
   - Transport: **HTTP** (not stdio — ChatGPT can't spawn local processes)
   - URL: `https://api.antiek.ai/mcp` (TODO: add HTTP transport adapter,
     see "HTTP transport wrapper" below)
   - Auth: **OAuth** scoped to the operator's Antiek session cookie

3. Hit "Test connection" — ChatGPT fetches the well-known manifest
   and verifies hashes before exposing the tools to a conversation.

### HTTP transport wrapper (open work)

The current server is stdio-only. ChatGPT's MCP integration needs
HTTP. This is on the Sprint-20+ backlog as a follow-on; for now,
local clients (Claude Desktop, Cursor, Continue.dev) work via the
SSH-stdio bridge above.

---

## Local CLI usage

For ad-hoc use without a chat client:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98 \
    cd /opt/antiek && /opt/antiek/.venv/bin/python -m tools.antiek_memory.server
```

Then pipe JSON-RPC frames in via stdin. The server speaks JSON-RPC 2.0
per the MCP spec.

---

## Tool descriptions + verification

All canonical tools are defined in
`tools/antiek_memory/server.py:CANONICAL_TOOLS`. Each one has:

- A stable `name` (no version suffix; version lives in the schema).
- A description in researcher's-notebook voice per §5.
- An `input_schema` JSON Schema object.

To regenerate the manifest after editing a tool:

```bash
./.venv/bin/python -c "
from tools.antiek_memory.server import CANONICAL_TOOLS
from tools.antiek_memory.signing import render_well_known_manifest
import json
print(json.dumps(render_well_known_manifest(CANONICAL_TOOLS), indent=2))
"
```

The HTTP endpoint computes the manifest at request time, so a
server restart after a tool-description change is sufficient to
make the new hashes visible.

---

## Failure modes

- **Manifest fetch fails (500/timeout):** the server isn't running or
  the Cloudflare Tunnel is down. Check `systemctl status antiek` on
  the VM.
- **Manifest hashes mismatch in clients:** a tool description was
  edited but the server wasn't restarted to pick up the new
  CANONICAL_TOOLS. Restart antiek.
- **`tools/call` rejected:** the operator's auth cookie or service
  token is missing/expired. See `infrastructure/runbooks/magic-link-auth.md`.

---

## Companion docs

- `tools/antiek_memory/` — server implementation
- `docs/master-product-spec.md` §13.8 — design rationale
- `infrastructure/runbooks/magic-link-auth.md` — auth side
