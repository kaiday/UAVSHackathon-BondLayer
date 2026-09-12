> Superseded 12/09 evening by DAY2-PLAN §4 WS-B

# Issue #15: Agent Pipeline - Quick Start Guide

## Overview
This implements the P3 milestone: a full shopping agent pipeline with LLM-powered ranking, merchant fan-out, and a BondLayer switch.

## Features Implemented

✅ **LLM Client** - Live Claude API calls (temperature 0)
✅ **Neutral System Prompt** - Shopping agent without BondLayer knowledge  
✅ **Intent Parsing** - Extract user intent with LLM
✅ **HTTP Fan-Out** - Query all 3 merchants identically
✅ **Ranking** - LLM ranks products across merchants
✅ **BondLayer Switch** - Toggle UCP header negotiation
⏳ **Record Signing** - Placeholder (blocked on signing library)
⏳ **Loyalty Layer** - Mocked in transcript (blocked on UCP record format)

## Prerequisites

- Python 3.10+
- Node.js 18+
- `OPENAI_API_KEY` environment variable set

## Quick Start (3 Terminals)

**Terminal 1: Merchant Service**
```bash
cd round2/chat-app
pip install -r requirements.txt
python -m src.merchant.main
# Runs on http://localhost:8000
```

**Terminal 2: Agent Service**
```bash
cd round2/chat-app
export OPENAI_API_KEY=sk-...  # Set your OpenAI API key
python -m src.agent.main
# Runs on http://localhost:8001
```

**Terminal 3: Web UI**
```bash
cd round2/chat-app/src/ui
npm install
npm run dev
# Opens http://localhost:5173
```

## Testing the Pipeline

1. Open http://localhost:5173 in your browser
2. Verify both services show as healthy (green indicators)
3. Try a search: `"USB-C charger under $30"`
4. Watch the flow:
   - **Intent Parse**: Extracted shopping goal
   - **Fan-Out**: Queries voltway, citycircuit, northgear
   - **Ranking**: LLM ranks across merchants
   - **Results**: Shows top products with reasoning
5. Toggle the **BondLayer switch**:
   - **ON**: UCP header includes `org.bondlayer.benefit_value`
   - **OFF**: Header is none (extension pruned)

## Architecture

```
┌──────────────┐
│  React UI    │ (localhost:5173)
└──────┬───────┘
       │
       ├──────────────┐
       │              │
       v              v
┌──────────────┐  ┌──────────────┐
│ Agent Service│  │ Merchant Svc │ (localhost:8000)
│:8001         │  │ Returns:     │
│ - Intent     │  │ - Products   │
│ - LLM Rank   │  │ - Quotes     │
│ - UCP header │  └──────────────┘
└──────────────┘
   ↓
- Parse intent
- Fan-out to all merchants
- Rank results with LLM
- Generate UCP header
- Return ranked results
```

## Key Files

- **Agent** `round2/chat-app/src/agent/main.py` - LLM pipeline
- **Merchant** `round2/chat-app/src/merchant/main.py` - Mock product catalog
- **UI** `round2/chat-app/src/ui/src/App.tsx` - React interface

## API Endpoints

### Merchant Service (:8000)
- `GET /health` - Health check
- `GET /merchants/{merchant}/products?query=...` - Search products
- `POST /merchants/{merchant}/quote` - Get product quote

### Agent Service (:8001)
- `GET /health` - Health check
- `POST /query` - Process shopping query
  ```json
  {
    "query": "USB-C charger under $30",
    "bondlayer_enabled": true
  }
  ```

## Placeholders (Blocked)

1. **Record Signing**: Evidence records are mocked (waiting on ES256 implementation)
2. **Loyalty Layer**: Transcript shows placeholder data (blocked on UCP format)
3. **Full UCP Negotiation**: Basic header generation works; full protocol pending

## Next Steps

- [ ] Implement record signing (ES256) in `round2/valuation/signing.py`
- [ ] Connect loyalty layer data
- [ ] Full UCP protocol negotiation
- [ ] Persist signed records to database

## Debugging

**Services not responding?**
```bash
# Check merchant service
curl http://localhost:8000/health

# Check agent service  
curl http://localhost:8001/health
```

**LLM calls failing?**
- Verify `OPENAI_API_KEY` is set
- Check API key has quota
- Monitor OpenAI API usage at https://platform.openai.com/usage

**Products not showing?**
- Verify merchant service is running
- Check browser console for errors
- Try a simpler query term

## Metrics (Issue #15)

- **Done When**: "A typed query returns a ranked answer with prose justification, and flipping the switch visibly changes the output"
  - ✅ Ranked answers with reasoning
  - ✅ BondLayer switch changes UCP header
  - ✅ Visible effect on negotiation
