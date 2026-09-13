<#
BondLayer -- one command from a clean clone to the running demo (Windows).

  .\run.ps1              set up, then start the merchant server (:8000) and,
                         if buyer-agent is present, the buyer-agent
                         stand-in (:8001) and its Vite UI (:5173). Ctrl-C stops
                         everything this script started.
  .\run.ps1 -Check       set up and run the bondlayer test suite, start nothing
  .\run.ps1 -Setup       set up only (venv + installs), start nothing
  .\run.ps1 -NoAgent     merchant server only
  .\run.ps1 -NoUi        skip the Vite dev server
  .\run.ps1 -Restart     stop the BondLayer servers already on :8000/:8001
                         (run_server.py, src.agent.main only), then start fresh

Idempotent: re-running reuses .venv, re-installs are no-ops, and a port that
is already serving is reported and left alone -- it keeps the code it was
started with, so use -Restart after pulling. No network at runtime.

Env: PYTHON (default: python), BONDLAYER_PORT (8000), AGENT_PORT (8001), UI_PORT (5173).
If scripts are blocked: powershell -ExecutionPolicy Bypass -File .\run.ps1
#>
param(
  [switch]$Check,
  [switch]$Setup,
  [switch]$NoAgent,
  [switch]$NoUi,
  [switch]$Restart
)
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$Venv = Join-Path $Root ".venv"
$MerchantPort = if ($env:BONDLAYER_PORT) { [int]$env:BONDLAYER_PORT } else { 8000 }
$AgentPort = if ($env:AGENT_PORT) { [int]$env:AGENT_PORT } else { 8001 }
$UiPort = if ($env:UI_PORT) { [int]$env:UI_PORT } else { 5173 }
$ChatApp = Join-Path $Root "buyer-agent"
$LogDir = Join-Path $Root ".run"
$StartAgent = -not $NoAgent
$StartUi = -not $NoUi

function Say($msg) { Write-Host ""; Write-Host "== $msg" }

# ---------------------------------------------------------------- python ----
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
  Write-Error "$Python not found. Install Python 3.12+ or set `$env:PYTHON"
}
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
  Write-Error "bondlayer needs Python 3.12+; $Python is $(& $Python --version 2>&1)"
}

# ------------------------------------------------------------------ venv ----
Say "virtualenv: $Venv"
$VPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VPy)) {
  & $Python -m venv $Venv
  Write-Host "   created with $(& $VPy --version)"
} else {
  Write-Host "   reusing $(& $VPy --version)"
}

# --------------------------------------------------------------- install ----
Say "installing bondlayer (editable, with dev extras)"
& $VPy -m pip install -q --disable-pip-version-check -e "$Root\bondlayer[dev]"
if ($LASTEXITCODE -ne 0) { Write-Error "pip install of bondlayer failed" }

if (Test-Path (Join-Path $ChatApp "requirements.txt")) {
  Say "installing buyer-agent requirements"
  Push-Location $ChatApp
  try {
    & $VPy -m pip install -q --disable-pip-version-check -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Write-Error "pip install of chat-app requirements failed" }
  } finally { Pop-Location }
} else {
  Write-Host "   buyer-agent/requirements.txt not present -- merchant server only"
  $StartAgent = $false
  $StartUi = $false
}

if ($Setup) { Say "setup complete. Start with: .\run.ps1"; exit 0 }

if ($Check) {
  Say "pytest (bondlayer/)"
  Push-Location (Join-Path $Root "bondlayer")
  try { & $VPy -m pytest -q; $rc = $LASTEXITCODE } finally { Pop-Location }
  if ($rc -ne 0) { exit $rc }
  Say "check complete"
  exit 0
}

# --------------------------------------------------------------- helpers ----
function Port-Busy([int]$port) {
  try {
    $c = New-Object Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", $port); $c.Close(); return $true
  } catch { return $false }
}
function Wait-For([string]$url, [int]$tries = 40) {
  for ($i = 0; $i -lt $tries; $i++) {
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep -Milliseconds 250 }
  }
  return $false
}
# Stops only a BondLayer server on $port: the listening process must be running
# $marker. A venv python.exe on Windows relaunches the base interpreter, so the
# launcher parent is stopped too when it runs the same thing.
function Stop-Listener([int]$port, [string]$marker) {
  $conns = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
  foreach ($c in $conns) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
    if (-not $p) { continue }
    if ($p.CommandLine -notlike "*$marker*") {
      Write-Host "   :$port is held by another program (pid $($p.ProcessId)) -- not stopping it"
      continue
    }
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" -ErrorAction SilentlyContinue
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    if ($parent -and $parent.CommandLine -like "*$marker*") {
      Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "   stopped pid $($p.ProcessId) on :$port"
  }
  for ($i = 0; $i -lt 40 -and (Port-Busy $port); $i++) { Start-Sleep -Milliseconds 250 }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Procs = @()

if ($Restart) {
  Say "restart: stopping BondLayer servers on :$MerchantPort and :$AgentPort"
  Stop-Listener $MerchantPort "run_server.py"
  if ($StartAgent) { Stop-Listener $AgentPort "src.agent.main" }
}

# ------------------------------------------------------- merchant server ----
Say "merchant server (bondlayer\run_server.py) on :$MerchantPort"
if (Port-Busy $MerchantPort) {
  Write-Host "   :$MerchantPort already serving -- leaving it alone (.\run.ps1 -Restart loads new code)"
} else {
  $Procs += Start-Process -FilePath $VPy -ArgumentList @("run_server.py", "$MerchantPort") `
    -WorkingDirectory (Join-Path $Root "bondlayer") -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $LogDir "merchant.log") `
    -RedirectStandardError (Join-Path $LogDir "merchant.err.log")
  if (Wait-For "http://127.0.0.1:$MerchantPort/health") {
    Write-Host "   up (log: .run\merchant.log)"
  } else {
    Write-Host "   FAILED to start; see .run\merchant.err.log"
    $Procs | ForEach-Object { try { $_.Kill() } catch {} }
    exit 1
  }
}

# ------------------------------------------------------------- the agent ----
# Only the agent. buyer-agent\src\merchant is being removed: the merchant
# is bondlayer's server, and nothing else is started on :8000.
$AgentMain = Join-Path $ChatApp "src\agent\main.py"
if ($StartAgent -and (Test-Path $AgentMain)) {
  Say "shopping agent (buyer-agent: src.agent.main) on :$AgentPort"
  # The model decides the ranking, so a missing key is no longer a cosmetic
  # downgrade to a template sentence -- it is a 503 on every search. Say so
  # here rather than letting the page fail in front of an audience.
  $EnvFile = Join-Path $ChatApp ".env"
  $HasKey = $false
  if ($env:OPENAI_API_KEY -and -not $env:OPENAI_API_KEY.StartsWith("sk-your")) {
    $HasKey = $true
  } elseif (Test-Path $EnvFile) {
    if ((Get-Content $EnvFile -Raw) -match 'OPENAI_API_KEY\s*=\s*sk-(?!your)\S+') { $HasKey = $true }
  }
  if (-not $HasKey) {
    Write-Host "   WARNING: no OPENAI_API_KEY in the environment or buyer-agent\.env."
    Write-Host "            The model decides the ranking, so /query and /chat answer 503."
  }
  if (Port-Busy $AgentPort) {
    Write-Host "   :$AgentPort already serving -- leaving it alone (.\run.ps1 -Restart loads new code)"
  } else {
    # `python -m src.agent.main` hardcodes :8001 and --reload; running the same
    # app through uvicorn honours AGENT_PORT and leaves one process to stop.
    $env:BONDLAYER_MERCHANT_URL = "http://127.0.0.1:$MerchantPort"
    $Procs += Start-Process -FilePath $VPy `
      -ArgumentList @("-m", "uvicorn", "src.agent.main:app", "--host", "127.0.0.1", "--port", "$AgentPort") `
      -WorkingDirectory $ChatApp -PassThru -NoNewWindow `
      -RedirectStandardOutput (Join-Path $LogDir "agent.log") `
      -RedirectStandardError (Join-Path $LogDir "agent.err.log")
    if (Wait-For "http://127.0.0.1:$AgentPort/" 60) { Write-Host "   up (log: .run\agent.log)" }
    else { Write-Host "   did not answer on :$AgentPort yet; see .run\agent.err.log" }
  }
} elseif ($StartAgent) {
  Say "no buyer-agent\src\agent\main.py -- agent not started"
}

# ----------------------------------------------------------------- the UI ----
$UiDir = Join-Path $ChatApp "src\ui"
$UiStarted = $false
if ($StartAgent -and $StartUi -and (Test-Path (Join-Path $UiDir "package.json"))) {
  if (Get-Command npm -ErrorAction SilentlyContinue) {
    Say "chat UI (vite) on :$UiPort"
    if (Port-Busy $UiPort) {
      Write-Host "   :$UiPort already serving -- leaving it alone"; $UiStarted = $true
    } else {
      if (-not (Test-Path (Join-Path $UiDir "node_modules"))) {
        Write-Host "   npm install (first run only)"
        Push-Location $UiDir
        try { npm install --silent --no-fund --no-audit } finally { Pop-Location }
      }
      $Procs += Start-Process -FilePath "npm" -ArgumentList @("run", "dev", "--", "--port", "$UiPort") `
        -WorkingDirectory $UiDir -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $LogDir "ui.log") `
        -RedirectStandardError (Join-Path $LogDir "ui.err.log")
      $UiStarted = $true
      Write-Host "   starting (log: .run\ui.log)"
    }
  } else {
    Say "npm not found -- skipping the Vite UI; the agent's own page is on :$AgentPort"
  }
}

# ------------------------------------------------------------------ URLs ----
Say "ready"
Write-Host "   merchant health    http://127.0.0.1:$MerchantPort/health"
Write-Host "   add a merchant     http://127.0.0.1:$MerchantPort/console/onboarding/"
Write-Host "   merchant console   http://127.0.0.1:$MerchantPort/console/"
Write-Host "   onboarding API     http://127.0.0.1:$MerchantPort/onboard/merchants"
Write-Host "   API docs           http://127.0.0.1:$MerchantPort/docs"
if ($StartAgent -and (Test-Path $AgentMain)) { Write-Host "   buyer agent        http://127.0.0.1:$AgentPort/" }
if ($UiStarted) { Write-Host "   chat UI            http://127.0.0.1:$UiPort/" }
if (Port-Busy $MerchantPort) {
  try {
    $console = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$MerchantPort/console/" -TimeoutSec 2
    if ($console.StatusCode -ne 200) {
      Write-Host "   WARNING: /console/ did not return HTTP 200; run .\run.ps1 -Restart"
    }
  } catch {
    Write-Host "   WARNING: the process on :$MerchantPort does not serve /console/ -- it may be an older build; run .\run.ps1 -Restart"
  }
}
Write-Host ""
Write-Host "   Ctrl-C stops what this script started."

if ($Procs.Count -gt 0) {
  try { $Procs | Wait-Process }
  finally { $Procs | ForEach-Object { try { if (-not $_.HasExited) { $_.Kill() } } catch {} } }
} else {
  Write-Host "   (everything was already running; nothing to wait on)"
}
