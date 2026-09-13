# BondLayer Demo - Windows Setup Guide

## Quick Start (2 Steps)

### Step 1: Set Up Environment File
```powershell
# Navigate to the chat-app directory
cd round2\chat-app

# Copy the example .env file
copy .env.example .env

# Edit .env and add your OpenAI API key
# Open .env in your text editor and replace:
#   OPENAI_API_KEY=sk-your-api-key-here
# With your actual key from https://platform.openai.com/api-keys
```

### Step 2: Run the Demo

**Option A: Command Prompt (Batch)**
```cmd
cd round2\chat-app
run-windows.bat
```

**Option B: PowerShell**
```powershell
cd round2\chat-app
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\run-windows.ps1
```

**Option C: Manual (3 Terminals)**

Terminal 1 - Merchant Service:
```powershell
cd round2\chat-app
python -m src.merchant.main
```

Terminal 2 - Agent Service:
```powershell
cd round2\chat-app
python -m src.agent.main
```

Terminal 3 - Web UI:
```powershell
cd round2\chat-app\src\ui
npm install
npm run dev
```

Then open: http://localhost:5173

---

## Setup Details

### 1. Get OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (starts with `sk-`)

### 2. Create .env File

```powershell
# From: round2\chat-app directory

# Option 1: Copy and edit
copy .env.example .env
# Then open .env in Notepad/VS Code and add your key

# Option 2: Create from scratch
echo OPENAI_API_KEY=sk-your-key-here > .env
```

**Don't forget:** Replace `sk-your-key-here` with your actual API key!

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

For Node dependencies (if running UI separately):
```powershell
cd src\ui
npm install
```

---

## .env File Format

Create `round2\chat-app\.env` with:

```
# OpenAI API Configuration
OPENAI_API_KEY=sk-your-actual-api-key-here
```

**Important:**
- ❌ Do NOT commit `.env` to git (it's in `.gitignore`)
- ✅ Keep it private - it contains your API key
- ✅ Each team member needs their own `.env` file

---

## Run Scripts Explained

### run-windows.bat (Command Prompt)
```batch
run-windows.bat
```
- Checks for `.env` file
- Installs dependencies automatically
- Opens 3 new windows for each service
- Launches browser automatically
- Simpler, faster startup

### run-windows.ps1 (PowerShell)
```powershell
.\run-windows.ps1
```
- Colored output
- Same functionality as batch
- Requires PowerShell execution policy
- More flexible scripting

### Manual Start (3 Terminals)
If scripts don't work:
1. Open 3 separate PowerShell/CMD windows
2. Run each command in its window
3. Watch output for errors

---

## Troubleshooting

### "Module not found: openai"
```powershell
pip install openai==1.3.0
pip install python-dotenv==1.0.0
```

### ".env file not found"
```powershell
copy .env.example .env
# Then edit .env with your API key
```

### "API key is invalid"
- Check your key starts with `sk-`
- Verify no extra spaces in .env
- Try generating a new key at https://platform.openai.com/api-keys

### Ports already in use
- Merchant (:8000): `netstat -ano | findstr :8000`
- Agent (:8001): `netstat -ano | findstr :8001`
- UI (:5173): `netstat -ano | findstr :5173`

Kill process:
```powershell
taskkill /PID <process-id> /F
```

### Browser won't open
Manually visit: http://localhost:5173

### Services not starting
Check the service windows for error messages. Common issues:
- Python not installed
- Node.js not installed for UI
- Ports already in use
- Missing dependencies

---

## Service URLs

Once running:
- **Merchant Service**: http://localhost:8000
  - Health: http://localhost:8000/health
  - API Docs: http://localhost:8000/docs
  
- **Agent Service**: http://localhost:8001
  - Health: http://localhost:8001/health
  - API Docs: http://localhost:8001/docs

- **Web UI**: http://localhost:5173
  - Shopping demo with BondLayer switch

---

## Testing the Demo

Once all services are running:

1. Open http://localhost:5173
2. Check service health indicators (should be green)
3. Type a query: `"USB-C charger under $30"`
4. Click Search
5. View ranked results
6. Toggle BondLayer switch to see UCP header change

---

## For PowerShell Execution Policy Error

If you get: `"run-windows.ps1 cannot be loaded because running scripts is disabled"`

Run this once:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run the script:
```powershell
.\run-windows.ps1
```

---

## Windows System Requirements

- Windows 10 or later
- Python 3.10+
- Node.js 18+ (for UI)
- 2GB RAM minimum
- Internet connection (for OpenAI API)

Check versions:
```powershell
python --version
node --version
npm --version
```

---

## Summary

```
1. Create round2\chat-app\.env with your OPENAI_API_KEY
2. Run: .\run-windows.bat  (or .\run-windows.ps1)
3. Wait for services to start
4. Browser opens automatically to http://localhost:5173
5. Test with query: "USB-C charger"
```

Done! 🎉
