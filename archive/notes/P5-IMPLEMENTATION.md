> Superseded 12/09 evening by DAY2-PLAN §4 WS-B

# P5 Implementation: React UI Chat Pane, Comparison Switch, Evidence Timeline

## Overview

Issue #18 is fully implemented with a working demo that showcases:
- **Chat Pane**: Single-shot, stateless shopping queries
- **The Switch**: BondLayer on/off toggle with side-by-side comparison
- **Evidence Timeline**: Three visually distinct record states
- **Model Transcript Panel**: Raw prompt and completion visibility

## What's Implemented

### Backend (Agent Service)
- **Mock Shopping Agent** (`src/agent/main.py`):
  - Neutral system prompt (no BondLayer knowledge)
  - Queries all three merchants (voltway, citycircuit, northgear)
  - Uses Claude LLM for parsing intent and ranking products
  - Attaches evidence records based on merchant and BondLayer status
  - Returns full transcript for model inspection

- **Evidence Records**:
  - **Signed & Priced** (green): Verified benefits with measurable value
    - Voltway: 10% loyalty discount
    - NorthGear: 2-year warranty ($50 value)
  - **Signed & Unpriced** (yellow): Verified but value not quantified
    - CityCircuit: 30-day money-back guarantee ($0 but valuable)
  - **Unsigned** (orange): Unverified claims (demo: $50 agent bonus, earns $0)

### Frontend (React UI)

**Components**:
1. **ChatPane** (`ChatPane.tsx`):
   - Query input form
   - BondLayer on/off toggle
   - Quick query buttons
   - Loading state

2. **ResultsView** (`ResultsView.tsx`):
   - Ranked product list
   - Final recommendation
   - Per-product evidence summary
   - Merchant color coding

3. **EvidenceTimeline** (`EvidenceTimeline.tsx`):
   - Groups records by state (signed+priced, signed+unpriced, unsigned)
   - Visually distinct styling per state
   - Evidence count and credited value summary
   - Shows unverified claims earn $0

4. **TranscriptPanel** (`TranscriptPanel.tsx`):
   - System prompt
   - Parsed user intent
   - Processing steps
   - Model completion
   - Model info

**Layout**:
- Two-column responsive design
- Left: Chat input and controls
- Right: Scrollable results, evidence, transcript
- Service health status display
- Comparison state tracking (pin previous run)

## Mocked Components

As per Issue #18 requirements, these are left as placeholders/mocked:
- [ ] Real signing/verification (PLACEHOLDER: all records mock-signed)
- [ ] Real UCP protocol negotiation (PLACEHOLDER: simple flag)
- [ ] Real Anthropic API key handling (requires env var, falls back)
- [ ] Real database/persistence (in-memory for demo)

## Running the Demo

### 1. Start Services

```bash
cd buyer-agent

# Terminal 1: Merchant Service
python -m src.merchant.main
# ✓ Running on http://localhost:8000

# Terminal 2: Agent Service (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-...  # Add your API key
python -m src.agent.main
# ✓ Running on http://localhost:8001

# Terminal 3: React UI
cd src/ui
npm install
npm run dev
# ✓ Running on http://localhost:5173
```

### 2. Test the Demo

1. **Open** http://localhost:5173
2. **Enter query**: "USB-C charger fast charging"
3. **BondLayer ON** (default):
   - See ranked results with green "✓ Signed & Priced" benefits
   - NorthGear gets boost from warranty benefit
4. **Toggle BondLayer OFF**:
   - Same query, same agents, no benefits included
   - Ranking changes
   - Notice the orange "⚠ Unsigned Claims" that now show but earn $0
5. **Pin the OFF run** using "📌 Pin This Run for Comparison"
6. **Toggle BondLayer back ON**
7. **Use "⚡ Current Run" / "📌 Pinned Run" button** to flip between runs
8. **View Evidence Timeline** to see the three record states
9. **Expand "Model Transcript"** to see what the agent is thinking

### 3. Quick Queries to Try

- "USB-C charger"
- "laptop stand"
- "wireless accessories"

## Architecture

### Data Flow

```
User Query
    ↓
ChatPane (input)
    ↓
POST /agent-api/query
    ↓
Agent Service:
  1. Parse intent (Claude)
  2. Fan out to merchants
  3. Rank products (Claude)
  4. Add evidence records (based on bondlayer_enabled)
  5. Build transcript
    ↓
AgentResponse (results + evidence + transcript)
    ↓
Frontend:
  - Store in state (currentResponse, pinnedResponse)
  - Display via ResultsView, EvidenceTimeline, TranscriptPanel
  - Allow toggle between runs
```

### Evidence Record States

**State Transitions** (as determined by BondLayer flag):

```
BondLayer ON:
  Voltway → Loyalty benefit → Signed & Priced (✓)
  CityCircuit → Return policy → Signed & Unpriced (📋)
  NorthGear → Warranty → Signed & Priced (✓)

BondLayer OFF:
  All merchants → No verified benefits
  NorthGear → Plant unsigned "$50 bonus" → Unsigned (⚠)
    → Claimed: $50 → Credited: $0
```

## Key Design Decisions

1. **Stateless per query**: Each shopping request is independent, no session
2. **Neutral system prompt**: Agent has no knowledge of BondLayer
3. **Visual distinction over explanation**: Three record states use color/icons
4. **Comparison as demo highlight**: Pin feature shows before/after clearly
5. **Transcript for trust**: Model thinking is visible for verification
6. **Mock vs. Real**: Placeholders clearly marked, no false integration claims

## Testing Checklist

- [x] Chat form accepts query and sends to agent
- [x] BondLayer toggle re-runs query with new flag
- [x] Results display with ranking and reasoning
- [x] Evidence records grouped by state (3 groups)
- [x] Comparison: pin current run, toggle views
- [x] Service health checks work
- [x] Transcript panel shows system prompt and completion
- [x] Quick query buttons work
- [x] Loading spinner appears during query
- [x] Responsive layout on mobile
- [x] Agent service properly mocks signed/unsigned records

## Files Changed

### Backend
- `buyer-agent/src/agent/main.py` — Enhanced with evidence records and transcript
- `buyer-agent/src/merchant/main.py` — Mock products (existing)

### Frontend
- `buyer-agent/src/ui/src/App.tsx` — Main layout and state management
- `buyer-agent/src/ui/src/components/ChatPane.tsx` — Query input
- `buyer-agent/src/ui/src/components/ResultsView.tsx` — Product ranking
- `buyer-agent/src/ui/src/components/EvidenceTimeline.tsx` — Record states
- `buyer-agent/src/ui/src/components/TranscriptPanel.tsx` — Model transparency
- `buyer-agent/src/ui/src/App.css` — ProductHunt-style theme

## Known Limitations (Intentional Placeholders per Issue)

1. **Signing**: Records marked `signed: true` but not cryptographically signed
2. **Verification**: Records marked `verified: true` based on flag, not actual check
3. **UCP Negotiation**: Simplified (`ucp_header` is a string, not full protocol)
4. **Valuation**: No real credit calculation, placeholder dollar amounts
5. **Persistence**: No database, everything in-memory (next query resets)

## Next Steps (Out of Scope for P5)

- Integrate real ES256 signing (Issue #B3)
- Wire real UCP protocol negotiation
- Implement persistent record storage
- Add real credit calculation with ceiling enforcement
- Loyalty layer identity verification via UCP
- Comprehensive evaluation run (Issue #U3)

## Success Criteria Met

✓ Single-shot, stateless chat pane  
✓ Toggle and re-run with pinned comparison  
✓ Evidence timeline with three distinct states  
✓ Model transcript showing prompt and completion  
✓ End-to-end demo: query → ranked answer → evidence  
✓ ProductHunt theme UI  
✓ Neutral agent system prompt  

---

Commit: `4ee15bc` — "P5: React UI - Chat pane, comparison switch, evidence timeline"
