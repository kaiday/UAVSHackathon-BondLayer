# Deploying to Fly.io

Two Fly apps from one repo, both built from the repo root:

| App | Config | Dockerfile | What it serves |
|---|---|---|---|
| Merchant server | `fly.merchant.toml` | `Dockerfile.merchant` | UCP routes, `/console/`, `/dashboard/`, `/onboard/*`, `/docs` |
| Buyer agent | `fly.agent.toml` | `Dockerfile.agent` | the two-pane chat page at `/`, `/query` |

Deploy the merchant first: the agent needs the merchant's URL.

Both apps default to region `syd` (Sydney). Uploaded catalogues live on the
machine's own disk and are lost on every redeploy or restart.

## Before you start: pick app names

Fly app names are global. The configs use `bondlayer-merchant` and
`bondlayer-agent`; if either is taken, choose another name and change:

- `app = "..."` in `fly.merchant.toml` / `fly.agent.toml`
- `BONDLAYER_MERCHANT_URL` in `fly.agent.toml` to `https://<merchant-name>.fly.dev`

## Option A: command line (recommended)

Run everything from the repo root in PowerShell.

1. Install flyctl and log in (once):
   ```powershell
   iwr https://fly.io/install.ps1 -useb | iex
   fly auth login
   ```
2. Create and deploy the merchant server:
   ```powershell
   fly apps create bondlayer-merchant
   fly deploy --config fly.merchant.toml --ha=false
   ```
   `--ha=false` creates one machine. Without it Fly's first deploy creates two,
   and with auto-stop off both would run and double the cost.
   Check it: `https://bondlayer-merchant.fly.dev/console/` and
   `https://bondlayer-merchant.fly.dev/voltway/.well-known/ucp`.
3. Create and deploy the buyer agent:
   ```powershell
   fly apps create bondlayer-agent
   # optional: model-written rationale instead of the template sentence
   fly secrets set OPENAI_API_KEY=sk-... --config fly.agent.toml
   fly deploy --config fly.agent.toml --ha=false
   ```
   Check it: `https://bondlayer-agent.fly.dev/merchant-health` should say
   `"reachable": true`, then open `https://bondlayer-agent.fly.dev/`.

Redeploy after a change: re-run the same `fly deploy --config ...` command.

## Option B: Fly dashboard ("Launch an app" from GitHub)

Push your branch first; the dashboard builds from GitHub, not your laptop.
Create two apps from the same repository.

| Field | Merchant app | Agent app |
|---|---|---|
| App name | `bondlayer-merchant` (or your own) | `bondlayer-agent` (or your own) |
| Branch | the branch you pushed | same |
| CPU / Memory | shared-cpu-1x / 256MB | shared-cpu-1x / 512MB |
| Environment variables | none | `BONDLAYER_MERCHANT_URL` = `https://<merchant-name>.fly.dev` (optional: `OPENAI_API_KEY`) |
| Managed Postgres | leave unticked | leave unticked |
| Working directory | leave empty | leave empty |
| Config path | `fly.merchant.toml` | `fly.agent.toml` |

The dashboard may create two machines per app. Check with
`fly status --config fly.merchant.toml` and, if there are two, run
`fly scale count 1 --config fly.merchant.toml` (same for the agent).

## Keeping both apps awake (for example, 15 days of judging)

Both configs are already always on: `auto_stop_machines = "off"` and
`min_machines_running = 1`. Neither app sleeps when idle, so there is no
cold start. Nothing needs to ping them.

Check that exactly one machine per app is `started`:

```powershell
fly status --config fly.merchant.toml
fly status --config fly.agent.toml
```

Fly can still restart a machine for host maintenance or a crash. It comes
back by itself, but uploaded catalogues are lost when it does.

When the 15 days are over, stop paying for them:

```powershell
fly scale count 0 --config fly.agent.toml
fly scale count 0 --config fly.merchant.toml
# or delete them entirely:
fly apps destroy bondlayer-agent
fly apps destroy bondlayer-merchant
```

## Everyday commands

```powershell
fly status --config fly.merchant.toml        # machines and health checks
fly logs   --config fly.agent.toml           # live logs
fly scale count 0 --config fly.merchant.toml # stop it (no running cost)
fly scale count 1 --config fly.merchant.toml # start it again
fly apps destroy bondlayer-agent             # delete an app
```

## Things to know

- **Cost.** Both apps run one machine 24/7, so you pay for two small
  always-on machines (256MB and 512MB, shared CPU) for as long as they run.
  Check current rates at https://fly.io/pricing. Fly needs a card on the
  account. Scale both to 0 when you are done.
- **Network.** Deployed, the agent reaches the merchant over the public
  internet, and `OPENAI_API_KEY` (if set) calls OpenAI. The local `run.ps1`
  demo still needs no network.
- **Secrets.** `.dockerignore` keeps `*.pem` and `.env` files out of both
  images. Put keys in `fly secrets`, never in `fly.agent.toml`.
- **The merchant's `/` is empty.** Open `/console/` on the merchant app.
