# BondLayer Demo Chat App

Phase P0 scaffolding: core services, React UI shell, and seed data.

## Architecture

Two FastAPI services + React UI:
- **Merchant Service** `:8000` — merchant dashboard (stub)
- **Agent Service** `:8001` — mock shopping agent (stub)
- **UI** `:5173` — React + Vite, ProductHunt-style theme

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- pip, npm/yarn

### One-Command Launch

**Linux/macOS:**
```bash
./launch.sh
```

**Windows (PowerShell):**
```powershell
.\launch.ps1
```

Both will:
1. Install Python dependencies
2. Install Node dependencies
3. Start merchant service (:8000)
4. Start agent service (:8001)
5. Start Vite dev server (:5173)

Open `http://localhost:5173` — you should see health checks for both services.

### Manual Start

**Terminal 1 — Merchant service:**
```bash
pip install -r requirements.txt
python -m src.merchant.main
```

**Terminal 2 — Agent service:**
```bash
pip install -r requirements.txt
python -m src.agent.main
```

**Terminal 3 — UI:**
```bash
cd src/ui
npm install
npm run dev
```

## File Structure

```
chat-app/
├── pyproject.toml              # Python package config
├── requirements.txt            # Python deps
├── src/
│   ├── __init__.py
│   ├── merchant/
│   │   ├── __init__.py
│   │   └── main.py            # Merchant service (FastAPI, :8000)
│   ├── agent/
│   │   ├── __init__.py
│   │   └── main.py            # Agent service (FastAPI, :8001)
│   └── ui/
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx         # Shell UI
│           ├── App.css         # ProductHunt theme tokens
│           └── index.css
├── data/
│   ├── electronics.csv         # SKU seed data
│   ├── voltway_policy.txt
│   ├── citycircuit_policy.txt
│   ├── northgear_policy.txt
│   └── manifests.json          # Merchant configs
├── tests/
│   └── __init__.py
└── .gitignore
```

## Next Steps (Phase P1+)

- D4: Dashboard GUI routes (CSV upload, policy/promotions management)
- B5: Mock shopping agent with neutral system prompt
- B6: BondLayer on/off switch
- H2: RAG over policy + catalog for suggestions
- Integration: UCP protocol, record signing, loyalty layer

## Development

All services support hot-reload in development:
- Python: `uvicorn` with `--reload`
- React: Vite HMR

## Deployment Notes

**P0 only covers scaffolding.** No real data flow, no routing beyond `/health`.

See `round2/overview-progress.md` and `round2/system-architecture.md` for full context.
