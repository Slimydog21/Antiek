# Cloudflare Pages Setup — `app.antiek.ai`

**One-time operator action.** Sprint 11 ships the web app code but the
Pages project itself was deferred from Sprint 10 IaC (Terraform doesn't
have a `cloudflare_pages_project` resource that creates the
GitHub-connected build pipeline in one shot — that's a dashboard flow).

After this, every `git push` to `main` auto-builds + deploys
`app.antiek.ai`.

---

## Prerequisites

- DNS CNAME `app.antiek.ai → antiek-ai.pages.dev` is already configured
  (Terraform created it in Sprint 10).
- GitHub repo `Slimydog21/Antiek` is connected via the `gh auth login`
  done in Sprint 11 setup.
- The Antiek substrate is live at `https://api.antiek.ai` (Sprint 10).

## Steps

### 1. Create the Pages project

- Open https://dash.cloudflare.com
- Left sidebar: **Workers & Pages** → top-right: **Create application**
  → **Pages** tab → **Connect to Git**
- If prompted, install the Cloudflare GitHub App on your account and
  authorize access to `Slimydog21/Antiek` (you can pick "only select
  repositories" → Antiek)
- Click **Antiek** in the repo list → **Begin setup**

### 2. Build configuration

| Field | Value |
|---|---|
| Project name | **`antiek-ai`** (must match the existing CNAME target `antiek-ai.pages.dev`) |
| Production branch | `main` |
| Framework preset | None (or "Vite" if you want — it just preselects fields) |
| Build command | `cd apps/reading && npm install && npm run build` |
| Build output directory | `apps/reading/dist` |
| Root directory | (leave empty) |

### 3. Environment variables

Add one variable (under **Environment variables** in the setup form):

| Name | Value | Scope |
|---|---|---|
| `VITE_API_BASE_URL` | `https://api.antiek.ai` | Production |

This is what makes the deployed bundle call your substrate at
`api.antiek.ai` instead of trying to use same-origin paths.

### 4. Save and Deploy

Click **Save and Deploy**. First build takes ~2-3 minutes.

When it succeeds, the build log shows `dist/index.html` (~0.45 KB) +
the JS/CSS bundles. The deployment URL appears as
`https://<random>.antiek-ai.pages.dev`.

### 5. Bind to the custom domain

- After the first deploy, in the project view: **Custom domains** tab
  → **Set up a custom domain**
- Enter `app.antiek.ai` → **Continue** → **Activate domain**
- Cloudflare detects the existing CNAME and wires everything up.
- TLS provisions automatically within ~60 seconds.

### 6. Verify

```bash
curl -I https://app.antiek.ai/
# Expect: HTTP/2 200, content-type: text/html
```

Open https://app.antiek.ai in a browser. You should see Mode A
(research workstation) with the empty chat input.

Quick functional check:
1. Header shows "Antiek" + a "Research / Wrestle" toggle
2. Empty state has serif "What do you want to research?" prompt
3. Sidebar says "No investigations yet. Ask a question to start."
4. Type a tiny throwaway question, hit Cmd+Enter
5. Should POST `https://api.antiek.ai/investigations` (check
   browser DevTools → Network) and navigate to `/inv/<id>`
6. Trajectory view starts rendering phase rows live via the
   WebSocket connection to `wss://api.antiek.ai/ws/events`

If the trajectory view stays blank: the WebSocket isn't connecting.
Check DevTools console for a `wss://` error. Common cause: the
`VITE_API_BASE_URL` env var wasn't set during build (the bundle
falls back to same-origin and tries `wss://app.antiek.ai/ws/events`,
which doesn't exist).

## After every code push

Cloudflare Pages auto-deploys on push to `main`. No manual action
needed. Build status appears in the project's **Deployments** tab.

The substrate's deploy is still manual:
```bash
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/deploy.yml
```

So pushing a change that touches BOTH the substrate AND the web app
means:
1. `git push` (triggers Pages auto-deploy of the web app)
2. `ansible-playbook deploy.yml` (deploys the substrate change)

Order matters if the new web-app version depends on a new substrate
endpoint: deploy the substrate FIRST, then the Pages build will
land. Otherwise the deployed bundle calls an endpoint that 404s for
~2-3 minutes until Pages finishes building.

## Cost

Cloudflare Pages free tier: 500 builds/month, unlimited bandwidth,
unlimited requests. Antiek is nowhere near these limits.
