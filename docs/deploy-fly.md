# One codebase: run locally or deploy to Fly.io

Use **`round2/dev` for application and deployment changes**. Local running and Fly.io are
two configurations of the same services. `round2-deploy` supplied the initial deployment
files; it does not need to remain a separate application-development branch.

| | Local development | Fly.io |
|---|---|---|
| Start command | `run.ps1` / `run.sh` | `fly deploy` with each app's config |
| Merchant | `http://127.0.0.1:8000` | Your merchant app's HTTPS URL |
| Buyer agent | `http://127.0.0.1:8001` | Your agent app's HTTPS URL |
| Configuration | Environment variables / root `.env` | Fly environment settings and secrets |
| Persistent data | Merchant's uploads directory | Merchant's volume mounted at `/data` |
| Request reports | Agent submits over HTTP to merchant | Same HTTP path, authenticated with a shared service token |
| Console build | Existing export, or `npm run build` after UI changes | Docker builds the console from source automatically |

## Local run

From the repository root, copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
Then run:

```powershell
$env:PYTHONUTF8 = "1"
.\run.ps1
```

On macOS/Linux, use `./run.sh`. Open <http://127.0.0.1:8000/console/>.
After changing Python code, use `.\run.ps1 -Restart` or `./run.sh --restart`.

`BONDLAYER_AI_MODE=openai` is the live mode. `BONDLAYER_AI_MODE=rules` explicitly selects
offline/reference behaviour. Real-data comparisons in either mode can create request reports;
historical fixture runs do not automatically fill real request history.

The service token is optional for direct loopback connections in local development. If you
set it in `.env`, both services load the same value. A non-loopback or deployed receiver
requires the token. No shared filesystem between the processes is required.

## Fly.io architecture

Two apps, built from the repository root:

| App | Config | Image build | Persistent storage |
|---|---|---|---|
| Merchant | `fly.merchant.toml` | `Dockerfile.merchant` | `bondlayer_data` volume at `/data` |
| Buyer agent | `fly.agent.toml` | `Dockerfile.agent` | None; reports are sent to the merchant |

The merchant owns profiles, uploaded catalogues, policy drafts, signing keys, published
benefits and saved request reports under `/data/uploads`. It also serves the console and
shopping insights. The buyer agent discovers merchants, compares offers and posts its actual
report to `POST /internal/requests`. That endpoint validates the report, checks the service
token and saves it atomically; retrying the same report ID is idempotent.

Both images install the merchant package from `bondlayer/pyproject.toml`, including OpenAI
and dotenv dependencies. The merchant image builds the Next.js export from the current
frontend source. Local `.env` files, private keys, uploads and stale build output are
excluded from the Docker context.

## Deploy your own instance

The examples below use PowerShell. Run them from a reviewed checkout of **`round2/dev`**.
Use your own globally unique app names. The `--app` flags below override the sample names
in the shared configs, so each developer can deploy without changing shared application code.

### 1. Install Fly CLI and sign in

Create a Fly.io account with billing enabled. Install the CLI and log in:

```powershell
Invoke-WebRequest https://fly.io/install.ps1 -UseBasicParsing | Invoke-Expression
fly auth login
```

Reopen PowerShell if the `fly` command is not found. Fly builds remotely by default, so
Docker does not need to run on your laptop for a cloud deployment.

### 2. Name and create both apps

Replace `yourname` before running these commands. Select your own Fly organisation if prompted.

```powershell
$MerchantApp = "bondlayer-yourname-merchant"
$AgentApp = "bondlayer-yourname-agent"
fly apps create $MerchantApp
fly apps create $AgentApp
```

### 3. Configure secrets on both apps

Both services call OpenAI. They also need the **same** service token so the agent can save
reports on the merchant. Generate that token once for this deployment and set it on both.
The following prompts for the OpenAI key without putting the literal key in your command history:

```powershell
$SecureKey = Read-Host "OpenAI API key" -AsSecureString
$OpenAIKey = [System.Net.NetworkCredential]::new("", $SecureKey).Password
$ServiceToken = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")

fly secrets set --app $MerchantApp --stage "OPENAI_API_KEY=$OpenAIKey" "BONDLAYER_SERVICE_TOKEN=$ServiceToken"
fly secrets set --app $AgentApp --stage "OPENAI_API_KEY=$OpenAIKey" "BONDLAYER_SERVICE_TOKEN=$ServiceToken"
Remove-Variable SecureKey, OpenAIKey, ServiceToken
```

Fly stores these secrets for subsequent deployments. Do not generate a replacement service
token for just one app. API keys and service tokens belong in Fly secrets, not TOML files.

Both configs set `BONDLAYER_AI_MODE=openai` and `BONDLAYER_TEST_DATA=0`. To select another
model, set the same `BONDLAYER_MODEL` on both apps.

### 4. Create the merchant volume once

```powershell
fly volumes create bondlayer_data --app $MerchantApp --region syd --size 1 -y
```

The configs use Sydney (`syd`). The volume must be in the merchant's region and its name
must match the `source` in `fly.merchant.toml`. Create it once, not on every redeploy.

### 5. Deploy the merchant, then the agent

```powershell
fly deploy --config fly.merchant.toml --app $MerchantApp --ha=false
fly deploy --config fly.agent.toml --app $AgentApp --ha=false --env "BONDLAYER_MERCHANT_URL=https://$MerchantApp.fly.dev"
```

`--ha=false` avoids a second initial machine. The merchant uses one attached volume and
one machine; this setup does not replicate its in-memory catalogue across machines.
Use the agent URL override on subsequent deployments too, so it continues to query your
own merchant rather than the sample app name in the shared config.

The CLI deploys the local checkout. A GitHub-based deployment builds pushed commits only:
include the application changes, new modules and deployment configuration in the release
commit before deploying from GitHub.

### 6. Verify and onboard

```powershell
Invoke-RestMethod "https://$MerchantApp.fly.dev/health"
Invoke-RestMethod "https://$AgentApp.fly.dev/merchant-health"
fly status --app $MerchantApp
fly status --app $AgentApp
```

Expect merchant `status: ok` and agent `reachable: true`. Then:

1. Open `https://<merchant-app>.fly.dev/console/onboarding/` and publish a catalogue.
2. Open **Settings → Test OpenAI connection** to verify a real API call.
3. Upload and review policies on **Benefit records**, then publish approved records.
4. Open `https://<agent-app>.fly.dev/` and ask for an uploaded product.
5. Check that the response has a saved request ID, then inspect the merchant's Request console.

The merchant's `/` is not the console; use `/console/`. These are public URLs. The shared
service token protects report ingestion, not the entire merchant console; production
merchant authentication is separate work.

## Updates and operations

Use the same deploy commands from step 5 after updating `round2/dev`. Both services should
be deployed from the same reviewed code revision. The volume survives image replacement.

```powershell
fly logs --app $MerchantApp
fly logs --app $AgentApp
fly volumes list --app $MerchantApp
```

Both configs keep one shared-CPU, 512 MB machine running continuously. No keep-alive pinger
is needed. Check current Fly pricing; there are two machines plus volume storage and any
OpenAI usage. Scaling to zero stops compute, while volume storage can still incur charges:

```powershell
fly scale count 0 --app $AgentApp
fly scale count 0 --app $MerchantApp
```

Do not destroy the merchant app/volume if you want to keep its uploaded data.

| Symptom | Check |
|---|---|
| Agent cannot reach merchant | `BONDLAYER_MERCHANT_URL`, merchant health and both apps' logs |
| Ranking works but history is missing | Both apps need the same `BONDLAYER_SERVICE_TOKEN`; inspect `history_error` |
| Merchant rejects report ingestion as unconfigured | Set its Fly service-token secret; deployed ingestion fails closed |
| OpenAI features fail | Set `OPENAI_API_KEY` on both apps; check model access, quota and Settings connection test |
| Uploads disappear after redeploy | Confirm the merchant volume mount and `BONDLAYER_UPLOADS_DIR=/data/uploads` |
| Old UI after a local source edit | Rebuild `bondlayer/app`; Fly's Docker build does this automatically |
| Build cannot install dependencies or fetch build-time fonts | Check builder internet access and retry the build |

## Test the deployment topology locally

With Docker Desktop running, build the exact Fly images and exercise two containers with
separate filesystems. The check uses an isolated volume, uploads its own catalogue, makes
a real HTTP shopping request in explicit rules mode, verifies history/insights, replaces
the merchant container and checks persistence. It makes no paid OpenAI calls.

```powershell
docker build -f Dockerfile.merchant -t bondlayer-merchant:unified-check .
docker build -f Dockerfile.agent -t bondlayer-agent:unified-check .
.\.venv\Scripts\python.exe scripts/check_deployment.py
```

The check removes only its own temporary containers, network and volume. The images remain
available for another run. For a separate paid OpenAI integration check, run
`.\.venv\Scripts\python.exe scripts/check_live_openai.py` with a configured API key.
