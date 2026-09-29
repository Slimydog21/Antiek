---
name: modal-compute
description: >-
    Run bounded remote compute on Modal - a disposable sandbox for code that must not run as your
    own user, a GPU job the Mac mini cannot do, or a batch that should outlive the session. Use
    when asked to run something isolated or untrusted, to use a GPU, to scale a job beyond this
    machine, or to check what Modal is costing. Also use before recommending a Modal deployment,
    because this account bills for storage by default. Not for ordinary local commands - the
    kernel runs those.
---

# modal-compute

Modal is compute this harness CALLS, not a platform that drives it. That is why it survived the
architecture review that rejected Multica, Firstmate and Goose.

**Account state, measured 2026-09-29.** The workspace is `slimydog21`, on the **Starter** plan -
`modal billing summary` reports `plan_cost` of zero with a $30 credit, not a subscription. Cash was
being billed for **storage only**: $66.65 this month, $73.56 last month, with zero compute and zero
LLM tokens. Five volumes created in May-June 2026 accounted for ~2.0 TiB at $0.09/GiB-month. All
apps and the one live inference endpoint have been stopped; **the volumes were left in place and
still bill ~$66/month** until they are deleted.

## Before you run anything

```bash
modal profile current                  # expect: slimydog21
modal app list                         # what is deployed right now
modal billing summary --json           # metered_cost / billed_cost / the breakdown by resource
```

`modal billing summary` is the cost instrument. Check it before a GPU job and after it, and quote
both numbers - Modal reports `costDollars`-style figures per resource, so the delta is the real
cost of the run, not an estimate.

## The safety contract

Every Modal run from this harness follows these four rules. They exist because the same Docker-style
capability on the grokbot machine was found listening unauthenticated on a tailnet.

1. **Network is blocked unless the task needs it.** Sandboxes isolate from the internet only when
   asked: `block_network=True`, or an explicit allowlist. Default to blocked.
2. **No secrets are injected** unless the task cannot work without one, and then a Modal Secret,
   never an env file from this Mac.
3. **A GPU run gets an explicit ceiling.** Pass a dollar budget and a wall-clock timeout, and stop
   the app afterwards. The whole monthly credit buys roughly 7.6 H100-hours, and storage has
   already consumed the credit line.
4. **Untrusted code runs in a Sandbox, not a Function.** A Function is your code; a Sandbox is for
   code you did not write.

## Sandboxes - the reason to use this at all

For generated or untrusted code, when the alternative is running it as the operator's own user on a
machine holding SSH keys, API keys and a Gmail-capable wrapper:

```python
import modal
sb = modal.Sandbox.create("python", "-c", "print('hello')", app=modal.App("probe"),
                          block_network=True, timeout=60)
print(sb.stdout.read()); sb.terminate()
```

`modal shell sb-<id>` attaches to one. Sandboxes bill about 3x Function CPU and memory rates, which
is the price of isolation - worth it, and still cents for a short run.

## Batch and GPU

```bash
modal run job.py --input data.json          # one-shot, exits when done
modal deploy job.py                          # persistent endpoints - only when something must call it
modal shell                                  # interactive container in the cloud
```

Reach for a GPU only when the task is genuinely GPU-bound. Local vision work is slow here
(DeepSeek-OCR-2 on MPS measured 3.9 tok/s), so a batch OCR over hundreds of pages is a legitimate
Modal job; a single image is not.

## Housekeeping that pays for itself

```bash
modal volume list                      # five volumes exist; four look abandoned
modal billing summary --for "last month" --json
```

Deleting a volume is **irreversible** - confirm what is inside first
(`modal volume ls <name> /`), and never delete one on the harness's own initiative. The
`antiek-tilert-glm5-weights` and `antiek-tilert-hf-cache` volumes hold re-downloadable model
weights, which makes them the cheapest legitimate cut.

## Not supported

- **Notebooks** have no CLI and no SDK object; they are a browser surface at
  https://modal.com/notebooks. Do not promise to drive them from here.
- The account is Starter, so enterprise features (SSO, audit logs, HIPAA) are unavailable, and the
  `glm-cc2` inference endpoint that used to run here has been permanently stopped.
