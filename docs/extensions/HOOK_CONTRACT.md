# Hook Contract — Antiek substrate extension authoring guide

**Audience:** anyone writing an extension that augments or replaces substrate
behavior, including future Claude Code instances tasked with extending Antiek.

**Status:** stable. The contract is the public surface; the implementation
behind it can evolve, but the shapes described here will not break without
a documented deprecation cycle.

## What a hook is

An **extension** is a Python module discovered at:

* `<project_root>/antiek_extensions/<name>/extension.py` — project-local
* `~/.antiek/extensions/<name>/extension.py` — operator-global

The module must define one top-level callable:

```python
def register(registry: HookRegistry) -> None:
    ...
```

`register` is called once per session start. Use it to attach **hooks** to
**declared seams** in the registry.

A **hook** is a callable implementing one of three Protocols:

* `PreCallHook` — runs *before* the substrate primitive
* `PostCallHook` — runs *after* (receives the primitive's result)
* `OnErrorHook` — runs *only if* the primitive raised

A **seam** is a named integration point the substrate has declared. Hooks
target seams by id (e.g. `"token_count"`, `"edit_validator"`, `"message_formatter"`).

## The three lifecycle stages

For one substrate-primitive invocation, the registry executes:

```
  pre  hooks (priority asc, registration order tiebreak)
        ↓  may rewrite kwargs, may short-circuit via HookShortCircuit(result)
  primitive(**kwargs)
        ↓  if raises, error hooks may recover
  post hooks (priority asc)
        ↓
  return result
```

### PreCallHook

```python
def __call__(self, ctx: HookContext, **kwargs: Any) -> dict[str, Any] | None:
    ...
```

Return value semantics:

* `dict` — replacement kwargs forwarded to the next pre hook / primitive
* `None` — leave kwargs unchanged
* `raise HookShortCircuit(result)` — skip the primitive entirely; post hooks
  still run with `result`

**Do not mutate** the input `kwargs` dict. Return a new dict if changes are
needed. Mutation would leak between hooks and break isolation.

### PostCallHook

```python
def __call__(self, ctx: HookContext, result: Any, **kwargs: Any) -> Any:
    ...
```

Always returns a result. The unmodified `result` is fine; transform if needed.

### OnErrorHook

```python
def __call__(self, ctx: HookContext, exc: BaseException, **kwargs: Any) -> Any | None:
    ...
```

Return value semantics:

* non-`None` — treated as a recovered result; subsequent error hooks **do not run**
* `None` — delegate to the next error hook
* `raise` — replaces the original exception in the chain

If no error hook returns non-`None`, the original exception is re-raised
by the registry.

## How to declare an extension

Minimal `extension.py`:

```python
from substrate.hooks import HookRegistry, HookContext, PostCallHook


class _UpperCaseFormatter:
    """Uppercase system-message content after formatting."""

    def __call__(self, ctx: HookContext, result, **kw):
        if isinstance(result, dict) and "messages" in result:
            for m in result["messages"]:
                if m.get("role") == "system":
                    m["content"] = m["content"].upper()
        return result


def register(registry: HookRegistry) -> None:
    registry.register_hook(
        seam_id="message_formatter",
        hook=_UpperCaseFormatter(),
        stage="post",
        extension_id="uppercase_formatter:v1",
        priority=100,  # late — runs after other formatters
    )
```

## Isolation rules

Extensions are loaded into the same Python process as the substrate. The
contract you accept by writing an extension:

* You **may** read substrate's public API (`substrate.hooks`,
  `substrate.observability.burn`, `substrate.conversation`, etc.).
* You **may not** read private state of sibling extensions.
* You **may not** import substrate internals beyond the documented public
  modules. Reading underscore-prefixed symbols means your extension will
  break on substrate updates even within a major version.
* You **may** raise exceptions; the registry catches them via the error-hook
  chain.

## Priority semantics

Hooks for a given (seam, stage) execute in order of `(priority, registration_order)`,
both ascending. Lower priority runs first.

Conventions:

* `priority=0` (default) — common case; treated as "no opinion"
* `priority < 0` — early; you want to run before other extensions
* `priority > 0` — late; you want the last word

The substrate itself does not register hooks at priority levels reserved for
extensions. Priority collisions are deterministic (registration order breaks
ties) but the operator should keep priorities distinct for clarity.

## Common pitfalls

| Pitfall | What goes wrong | Fix |
|---|---|---|
| Importing a substrate internal symbol | Breaks on substrate refactor | Only import from `substrate.hooks` public API |
| Mutating the kwargs dict in a pre-hook | Sibling hooks see your mutation | Return a new dict instead |
| Raising on every input in a post hook | Error-hook chain runs; result discarded | Return the unmodified result instead |
| Long-running work in a pre hook | Every primitive call now takes longer | Move expensive work into a separate primitive |
| Reading `os.environ` directly | Lints fail (SPR-07 R2) | Use `substrate.config` or accept env via `register()` argument |
| Module-level mutable globals in `extension.py` | Lints fail (SPR-07 R3) | Store state in a class instance |

## The seam catalog

Standard seams declared by substrate at session start:

| Seam | Stage(s) | Purpose | Example use |
|---|---|---|---|
| `token_count` | pre | Count tokens in `text` for `model` | Replace heuristic `len/4` with tiktoken |
| `edit_validator` | post | Validate union of files after EditTransaction commit | Run ruff / mypy on touched files |
| `message_formatter` | post | Mutate the formatted messages dict | Inject per-project style hints |
| `model_select` | pre | Route a task to a model | Use Haiku for lookups, Opus for synthesis |
| `tool_dispatch` | pre, post, err | Wrap any agent tool call | Add per-tool timing telemetry |
| `run_script_dispatch` | pre, post | Wrap deno script execution | Per-script policy escalation review |
| `compaction_summarize` | pre | Replace the LLM summarizer | Use a smaller model for cheap summarization |

Extensions may declare their own seams in `register()` for inter-extension
coordination.

## Disabling extensions

* Per-session: set env var that the operator-CLI manages (extension-specific).
* Persistent: `touch antiek_extensions/<name>/.disabled`. The loader respects
  the marker at discovery time. `antiek hooks disable project:<name>` is the
  CLI equivalent.

## Worked-example extensions

* `antiek_extensions/example_uppercase_formatter/` — minimal post-hook on
  `message_formatter`. Use as a copy-paste template.
* `antiek_extensions/example_token_counter/` — heuristic-replacement on
  `token_count`. Use as the template for swapping in real tokenizers.
* `antiek_extensions/example_edit_validator/` — collects file paths edited;
  template for plugging in lint/type-check.

## Verification

A new extension is verified by:

1. `antiek hooks list` — confirm it appears as `[loaded]` with the hooks you registered.
2. `antiek hooks inspect <scope>:<name>` — confirm the seam, stage, priority match what you wrote.
3. Drive a real agent turn that exercises the seam; check `antiek burn report` and (where relevant) `.antiek/conversation/<session>/events.jsonl` for the expected effect.

A hook that does not appear in step 1 means the loader rejected it — check
`antiek hooks list` output for the `[failed]` entry and the error string.
