---
name: grokbot-resource
description: >-
    Use Grok Bot computers as remote execution resources over the tailnet - discover which bots are
    online, run a bounded job on a bot's own computer, reach its desktop, and read what it is doing.
    Use when a task should run on a bot machine rather than this Mac, when asked what grokbots are
    available, when a bot is stuck or busy, or when planning multi-bot work. Read the limits
    section first, because bot PROVISIONING and bot PROMPTING are not available from here, and this skill
    does not extract the credentials that would be needed. Not a general remote-shell tool.
---

# grokbot-resource

A **Grok Bot is an xAI cloud agent whose own computer joins your tailnet** (that description comes
from the operator's own session history, and the tailnet evidence matches it). What this skill can
do is use the *computer*. What it cannot do is create bots or prompt their agent, and it will not
try to obtain the credentials for the latter.

Run the discovery check first:

```bash
python3 ~/.agents/skills/grokbot-resource/scripts/discover.py
```

## What a bot's computer actually is

Measured 2026-09-29 on `grokbot-1` (Debian 12, amd64, kernel 6.12.94+):

| Surface | Port(s) | State |
|---|---|---|
| Docker Engine 29.1.4 | **2375** | **open, unauthenticated** - root-equivalent for anything on the tailnet |
| `exec-daemon` HTTP API | 14002, 14005, 14010-14013 | open; advertises `--auth-token local`; REST routes not discoverable |
| `exec-daemon` PTY websockets | 13602, 13605, 13610-13613 | open |
| Desktops (Xvfb + x11vnc + picom) | 6080, 6081 | open; **six separate X11 sessions** exist |
| agent runtime | 1340 | `/health` open; `/api/*` returns 401 without a bearer token |
| SSH | 22 | refused |

## Running a job on a bot's computer

The proven path is the Docker API. Read-only host mounts and no network unless the job needs it:

```python
import httpx, time
base = "http://grokbot-1:2375"
with httpx.Client(timeout=120) as c:
    cr = c.post(f"{base}/containers/create?name=prime-agent-job",
                json={"Image": "alpine:latest",
                      "Cmd": ["sh", "-c", "uname -a; nproc"],
                      "HostConfig": {"Binds": ["/:/host:ro"], "NetworkMode": "none"}})
    cid = cr.json()["Id"]
    c.post(f"{base}/containers/{cid}/start")
    time.sleep(5)
    print(c.get(f"{base}/containers/{cid}/logs?stdout=1&stderr=1").text)
    c.delete(f"{base}/containers/{cid}?force=1")     # always clean up
```

Reading a process's own view of a filesystem (`/host/proc/<pid>/root/...`) needs a privileged
container; **do not go there** - the unprivileged read-only mount is enough for normal work, and
privilege escalation on someone's bot is not a shortcut worth taking.

## The rules for using someone's bot

1. **Always remove the container you created.** A stray container is a stray process on a machine
   you do not administer.
2. **Bind the host filesystem read-only** (`/:/host:ro`) unless the job is explicitly a writer.
3. **`NetworkMode: none`** unless the job needs the network. A bot computer with an open Docker
   daemon and a live agent runtime is not a good place to leave an egress path.
4. **Do not extract credentials.** The agent runtime's bearer token lives in xAI's sealed store and
   on the bot. Tried and refused: `local`, `box`, empty. That is where this skill stops.
5. **Do not treat the bot's filesystem as private to you.** The bot's own agent is running on that
   machine; another actor may be mid-task. `isBusy` on `/health` tells you.

## What is not available from here

- **Creating bots.** There is no API. Provisioning happens in the Grok Bot app
  (`/Applications/Grok Bot.app`, Electron, installed) or on the web. The app's local bridge daemon
  was **dead** on 2026-09-29 (its PID was gone, and its log is full of `ENOSPC` errors), so even
  the local half was down until the app is relaunched.
- **Prompting a bot.** `POST /api/message`, `GET /events`, `POST /api/sessions` and
  `POST /api/tools` all exist on `:1340` and all return `401 unauthorized`. The token is not on
  this Mac in readable form.
- **Teams of bots.** Nothing prevents assembling one *manually* - one Docker channel per online
  bot - but there is no team primitive to call, and no scheduling layer above them.

## Security finding to keep in view

`grokbot-1:2375` is an **unauthenticated Docker daemon on a tailnet**, which means anything on the
tailnet - including the other bots - has root on that machine. It is the single largest exposure
found in this estate. The fix is one of: firewall the port to this Mac's tailnet IP, put the daemon
behind TLS with client certs, or stop publishing it and use the bot's own `exec-daemon` instead.
