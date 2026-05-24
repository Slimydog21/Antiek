# example_uppercase_formatter

The canonical worked example referenced by `docs/extensions/HOOK_CONTRACT.md`.

## What it does

Registers a `PostCallHook` on the `message_formatter` seam. When the substrate's
formatter returns a result dict containing `messages`, this hook uppercases the
`content` of any message whose `role == "system"`.

## Before/after

```python
# Substrate primitive returns:
{"messages": [{"role": "system", "content": "You are a research assistant."}]}

# After this extension's post-hook:
{"messages": [{"role": "system", "content": "YOU ARE A RESEARCH ASSISTANT."}]}
```

## Use as template

```bash
cp -r antiek_extensions/example_uppercase_formatter antiek_extensions/my_extension
# Edit extension.py + extension.toml; update register() to attach your hook
antiek hooks list  # confirm [loaded]
```

## Disable

```bash
touch antiek_extensions/example_uppercase_formatter/.disabled
# Or:
antiek hooks disable project:example_uppercase_formatter
```
