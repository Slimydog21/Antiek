# Antiek Memory MCP Server — End-to-End Verification Report

**Date:** 2026-08-13  
**Scope:** master-spec §13.8 developer surface verification  
**Worktree:** /tmp/antiek-wt-memory-mcp (main tip)

---

## 1. Verified Protocol Surface

### 1.1 Three Resources (§13.8)

| # | URI Template | Status | Notes |
|---|---|---|---|
| 1 | `antiek://private/notes/{user_id}/{note_id}` | ✅ Implemented | Queries notebook_blocks + notebooks; per-user owner filter |
| 2 | `antiek://public/notes/{note_id}` | ✅ Implemented | Filters on `content_class = 'user_public_contribution'` |
| 3 | `antiek://books/{isbn}/{chunk_id}` | ✅ Implemented | Resolves chunk via chunks + documents join |

All three return `application/json` MIME type.

### 1.2 Four Tools (§13.8)

| # | Tool Name | Status | Input Schema |
|---|---|---|---|
| 1 | `search_personal` | ✅ Implemented | `query` (required), `top_k`, `include_private` |
| 2 | `search_public` | ✅ Implemented | `query` (required), `top_k` |
| 3 | `cite_source` | ✅ Implemented | `id` (required), `id_type` enum |
| 4 | `record_attribution` | ✅ Implemented | `chunk_id` (required), `investigation_id` (required), `session_dwell_seconds` |

### 1.3 Protocol Methods

| Method | Status | Notes |
|---|---|---|
| `initialize` | ✅ | Returns protocolVersion 2024-11-05, capabilities (tools + resources), serverInfo |
| `tools/list` | ✅ | Returns all 4 tools with name, description, inputSchema |
| `tools/call` | ✅ | Dispatches to handler_fns; returns content + isError; -32601 on unknown tool |
| `resources/list` | ✅ | Returns 3 URI templates with name, description, mimeType |
| `resources/read` | ✅ | Resolves via resource_handler; returns contents array; -32602 on missing |

### 1.4 Prompt-Injection Envelope (§13.8.3)

Content from `resources/read` (private notes) and `tools/call` (search_public) is wrapped in:
```xml
<antiek:content trusted="false">...</antiek:content>
```
Verified by E2E test assertions on the wire response.

### 1.5 Signing / Rug-Pull Defense

- `compute_tool_hash()` — deterministic SHA-256 over canonical JSON (name, description, input_schema)
- `render_well_known_manifest()` — generates `.well-known/mcp-tools.json` with per-tool hashes
- Existing endpoint test (`test_api_mcp_well_known.py`) verifies manifest ↔ signing module consistency

---

## 2. Gaps Found and Fixed

### 2.1 Missing `__main__.py` (FIXED)

**Gap:** No subprocess entry point existed. `python -m tools.antiek_memory` would fail with `No module named tools.antiek_memory.__main__`.

**Fix:** Created `tools/antiek_memory/__main__.py` with:
- Cold-start schema init via `init_database_at_path()`
- Real substrate handlers for all 4 tools (queries DuckDB via `connect_read`/`connect_write`)
- Resource handler resolving all 3 URI patterns
- Prompt-injection envelope wrapping in resource + search_public handlers
- Attribution recording into `attribution_audit` table (no escrow touch)

### 2.2 No E2E Subprocess Test Harness (FIXED)

**Gap:** Existing tests (`tests/test_antiek_memory_mcp.py`) were in-process unit tests using the `AntiekMemoryServer` object directly. No test verified the actual stdio JSON-RPC wire protocol.

**Fix:** Created `tests/tools/test_antiek_memory_mcp.py` — 23 tests spawning the server as a subprocess and driving JSON-RPC over stdin/stdout.

### 2.3 Handler Wiring Gap (BY DESIGN)

The `AntiekMemoryServer` is a scaffold with injectable handlers (`handler_fns`, `resource_handler`). No production wiring existed. The `__main__.py` provides the first concrete wiring against the real substrate.

---

## 3. Test Results

### 3.1 E2E Subprocess Harness (NEW)

```
$ cd /tmp/antiek-wt-memory-mcp && uv run --frozen --extra pdf --extra urls --extra embedding --extra docs --with pytest python -m pytest tests/tools/test_antiek_memory_mcp.py -q

23 passed, 1 warning in 14.54s
```

**Test classes:**
- `TestInitializeHandshake` (1 test)
- `TestToolsList` (6 tests)
- `TestResourcesList` (3 tests)
- `TestResourcesRead` (4 tests)
- `TestToolsCallSearchPersonal` (2 tests)
- `TestToolsCallSearchPublic` (1 test)
- `TestToolsCallCiteSource` (2 tests)
- `TestToolsCallRecordAttribution` (1 test)
- `TestErrorHandling` (3 tests)

### 3.2 Existing In-Process Tests (UNCHANGED)

```
$ cd /tmp/antiek-wt-memory-mcp && uv run --frozen --with pytest python -m pytest tests/test_antiek_memory_mcp.py -q

12 passed, 1 warning in 0.39s
```

---

## 4. Files Created/Modified

| File | Action | Description |
|---|---|---|
| `tools/antiek_memory/__main__.py` | **Created** | Subprocess entry point with real substrate handlers |
| `tests/tools/test_antiek_memory_mcp.py` | **Created** | E2E subprocess harness (23 tests) |

No existing files were modified.

---

## 5. Commands and Outputs

```bash
# Run E2E tests
cd /tmp/antiek-wt-memory-mcp && uv run --frozen --extra pdf --extra urls --extra embedding --extra docs --with pytest python -m pytest tests/tools/test_antiek_memory_mcp.py -q
# Output: 23 passed, 1 warning in 14.54s

# Run existing unit tests (regression check)
cd /tmp/antiek-wt-memory-mcp && uv run --frozen --with pytest python -m pytest tests/test_antiek_memory_mcp.py -q
# Output: 12 passed, 1 warning in 0.39s

# Verify subprocess entry point
cd /tmp/antiek-wt-memory-mcp && python -c "from tools.antiek_memory.__main__ import main; print('import ok')"
# Output: import ok
```

---

## 6. §13.8 Compliance Summary

| Requirement | Status |
|---|---|
| Three URI-addressable resources | ✅ Verified |
| Four canonical tools | ✅ Verified |
| JSON-RPC 2.0 over stdio | ✅ Verified |
| Prompt-injection envelope (§13.8.3) | ✅ Verified |
| Rug-pull defense (signed tool descriptions) | ✅ Verified (pre-existing) |
| Per-user OAuth scope (private resource) | ⚠️ Placeholder (handler uses `__operator__` default; OAuth not wired) |
| Attribution recording (§13.8 IR 2) | ✅ Verified (writes to attribution_audit, no escrow touch) |
