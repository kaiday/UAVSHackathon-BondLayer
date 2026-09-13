# Issue #18 Implementation Summary

## Issue: P5 — React UI: chat pane, switch with pinned comparison, evidence timeline

**Status**: ✅ COMPLETE  
**Commit**: `4ee15bc` + `5bd39b2` (implementation + docs)  
**Branch**: `feat/bach`

## Scope Delivered

### 1. Chat Pane ✓
- **Single-shot, stateless design**: Each message is an independent shopping request
- React form component with textarea input
- Quick query buttons for fast testing
- Loading state with spinner
- No session/conversation history (as specified)

### 2. The Switch ✓
- **BondLayer on/off toggle**: Checkbox in chat pane
- **Re-runs same query** with new setting
- **Pinned comparison**: 
  - "Pin This Run" button captures current response
  - "📌 Pinned Run / ⚡ Current Run" toggle flips between them
  - Shows which run is being viewed (with BondLayer on/off status)

### 3. Evidence Timeline ✓
- **Three visually distinct record states**:
  1. **✓ Signed & Priced** (green, top):
     - Voltway: 10% loyalty discount
     - NorthGear: 2-year warranty ($50)
     - Shown as credited value
  2. **📋 Signed & Unpriced** (yellow, middle):
     - CityCircuit: 30-day money-back guarantee
     - Shown as $0 but valuable/verified
  3. **⚠ Unsigned** (orange, bottom):
     - Unverified claims (e.g., "$50 agent bonus")
     - Shown claimed value → credited as $0
- Summary with counts per state
- Color-coded icons in results view

### 4. Model Transcript Panel ✓
- Expandable/collapsible section
- Shows:
  - System prompt (neutral, no BondLayer knowledge)
  - User query
  - Parsed intent (Claude)
  - Processing steps (intent parse, fan-out, ranking)
  - Model completion (recommendation text)
  - Model info (claude-3-5-sonnet-20241022)

## Components Created

### Frontend (React/TypeScript)
```
src/ui/src/
├── App.tsx (main: layout, state, comparison logic)
├── App.css (ProductHunt theme: 850+ lines)
└── components/
    ├── ChatPane.tsx (query input, toggle, quick buttons)
    ├── ResultsView.tsx (ranked products with evidence badges)
    ├── EvidenceTimeline.tsx (three-state record grouping)
    └── TranscriptPanel.tsx (system prompt & completion)
```

### Backend (Python/FastAPI)
```
src/agent/
└── main.py (enhanced with:
    - EvidenceRecord model
    - RankedResult with evidence_records
    - add_evidence_records() function
    - Full AgentResponse with transcript
    - Mock signing (placeholder: all records marked signed=true))
```

## Architecture

### Data Model
```python
class EvidenceRecord:
    id: str
    type: str  # "loyalty_benefit", "return_policy", "warranty", etc.
    description: str
    value: Optional[float]  # e.g., 2.99 for discount, None for policy
    source: str  # e.g., "Voltway membership program"
    signed: bool  # True if part of BondLayer
    verified: bool  # True if signature valid (placeholder)

class RankedResult:
    rank: int
    merchant: str
    product_id: str
    product_name: str
    price: float
    description: str
    reasoning: str  # LLM explanation
    evidence_records: list[EvidenceRecord]  # NEW

class AgentResponse:
    user_query: str
    parsed_intent: str
    results: list[RankedResult]
    final_recommendation: str
    bondlayer_enabled: bool
    transcript: dict  # NEW: system_prompt, completion, etc.
    ucp_header: Optional[str]
```

### API Contract
**POST `/query`**
```json
Request:
{
  "query": "USB-C charger",
  "bondlayer_enabled": true
}

Response:
{
  "user_query": "USB-C charger",
  "parsed_intent": "Find affordable USB-C power adapters",
  "results": [
    {
      "rank": 1,
      "merchant": "northgear",
      "product_name": "USB-C Charger 65W",
      "price": 27.99,
      "evidence_records": [
        {
          "id": "warranty_northgear_extended",
          "type": "warranty",
          "description": "2-year extended warranty included",
          "value": 50.0,
          "source": "NorthGear warranty program",
          "signed": true,
          "verified": true
        }
      ],
      "reasoning": "..."
    }
    // ... more results
  ],
  "final_recommendation": "I recommend the USB-C Charger 65W from northgear...",
  "bondlayer_enabled": true,
  "transcript": {
    "system_prompt": "You are a helpful shopping assistant...",
    "user_query": "USB-C charger",
    "parsed_intent": "Find affordable USB-C power adapters",
    "completion": "I recommend...",
    "model": "claude-3-5-sonnet-20241022"
  }
}
```

## UI Features

### Two-Column Responsive Layout
- **Left Panel** (350px, fixed):
  - Chat input form
  - BondLayer toggle
  - Quick query buttons
  - Service health status
- **Right Panel** (scrollable):
  - Comparison control (pin/unpin)
  - Results view
  - Evidence timeline
  - Transcript (expandable)

### Visual Styling
- ProductHunt-inspired color scheme
- Gradient header with logo
- Card-based results with merchant color coding
- State indicators (✓ green, 📋 yellow, ⚠ orange)
- Smooth transitions and hover effects
- Mobile-responsive (stacked layout on <768px)

## Blockers Left as Placeholders

As per instructions, these are marked as TODO/blocked but have working mocks:

1. **Real Cryptographic Signing**:
   - PLACEHOLDER: All records marked `signed: true`
   - TODO: Implement ES256 (ECDSA P-256/SHA-256) signing
   - TODO: Canonical JSON serialization before signing

2. **Real Signature Verification**:
   - PLACEHOLDER: Verified based on `bondlayer_enabled` flag
   - TODO: Actual signature validation
   - TODO: Trust chain verification

3. **UCP Protocol Details**:
   - PLACEHOLDER: Simple `ucp_header` string
   - TODO: Full UCP negotiation protocol
   - TODO: Capability advertisement

4. **Valuation Engine**:
   - PLACEHOLDER: Hardcoded values per merchant
   - TODO: `effective_cost()` calculation
   - TODO: Credit ceiling enforcement (`min(ceiling, value)`)

5. **Loyalty Layer**:
   - PLACEHOLDER: No actual identity verification
   - TODO: UCP-based identity fetching
   - TODO: Consent-gated enrollment

## Success Criteria (Issue #18)

✅ Chat pane works end-to-end  
✅ Type a query → get ranked answer with justification  
✅ Switch toggles BondLayer on/off  
✅ Can pin previous run and flip between them  
✅ Evidence timeline shows three record states visually distinct  
✅ Model transcript panel shows prompt and completion  
✅ Done when: "The full demo runs end to end in the browser"  

## Running the Demo

```bash
cd round2/chat-app

# Terminal 1: Merchant Service
python -m src.merchant.main

# Terminal 2: Agent Service
export ANTHROPIC_API_KEY=sk-...
python -m src.agent.main

# Terminal 3: UI
cd src/ui
npm install
npm run dev

# Open http://localhost:5173
```

### Test Scenario
1. Enter: "USB-C charger fast charging"
2. BondLayer ON: See NorthGear ranked higher with warranty benefit
3. Pin this run
4. Toggle BondLayer OFF
5. Same query re-runs: different ranking (no warranty)
6. Use toggle to compare: pin (BondLayer ON) vs current (BondLayer OFF)
7. View evidence timeline: signed+priced vs unsigned claims
8. Expand transcript: see system prompt and agent thinking

## Files Modified

```
round2/
├── chat-app/
│   ├── src/agent/main.py (enhanced)
│   └── src/ui/src/
│       ├── App.tsx (rewritten)
│       ├── App.css (expanded: 850+ lines)
│       └── components/ (new)
│           ├── ChatPane.tsx
│           ├── ResultsView.tsx
│           ├── EvidenceTimeline.tsx
│           └── TranscriptPanel.tsx
├── P5-IMPLEMENTATION.md (new: architecture guide)
└── (other existing files unchanged)
```

## Known Limitations

- Records are not actually signed (signed: true is mock)
- No real database persistence (in-memory)
- Anthropic API required (set `ANTHROPIC_API_KEY`)
- No real UCP protocol negotiation
- Comparison is ephemeral (new query resets)

## Design Philosophy

Per Issue #18 notes:
- **Visual polish is lower priority than logic**: Minimal but functional UI ✓
- **Stateless**: No conversation history, each query independent ✓
- **Neutral agent**: System prompt has no BondLayer knowledge ✓
- **Comparison as feature**: Pin mechanism shows before/after clearly ✓
- **Evidence for trust**: Three states with visual distinction ✓

---

**Total Implementation**: ~1,900 lines (backend + frontend)  
**Components**: 4 React components + enhanced agent service  
**Commits**: 2 commits (implementation + docs)  
**Ready for**: Stage P6+ (signing, valuation, loyalty layer)
