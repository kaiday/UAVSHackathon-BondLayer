> Superseded 12/09 evening by DAY2-PLAN §4 WS-B

# BondLayer Demo Implementation Summary

## Project Overview

BondLayer is a middleware layer for B2AI (Business-to-AI) shopping that sits between AI shopping agents and merchants. It provides:

1. **UCP Compliance**: Merchants speak a standard agent-readable protocol
2. **Ranking Signals**: Loyalty benefits, policies, and perks that help merchants win rankings
3. **Trust**: Cryptographically signed records prove all claims

This document summarizes the end-to-end implementation of the demo chat app (Issues #18, #15, #13, and related).

## What's Built

### Phase P5: React UI - Chat Pane, Comparison, Evidence Timeline
**Commit**: `4ee15bc` + `5bd39b2` (implementation + docs)

Delivered:
- ✓ Single-shot stateless chat interface
- ✓ BondLayer on/off toggle
- ✓ Pin previous run and flip between them (side-by-side comparison)
- ✓ Evidence timeline with three record states
- ✓ Model transcript panel showing prompt and completion
- ✓ Two-column responsive layout with ProductHunt theme
- ✓ Service health status display

**Files**:
```
src/ui/src/
├── App.tsx (main layout, state management)
├── App.css (850+ lines theme)
├── components/
│   ├── ChatPane.tsx (query input, toggle, quick buttons)
│   ├── ResultsView.tsx (ranked products)
│   ├── EvidenceTimeline.tsx (record states - initial mock)
│   └── TranscriptPanel.tsx (system prompt & completion)
```

### Phase P6: Trust and Loyalty Integration
**Commit**: `ba35b6a` (UI integration) + `ef2f161` (docs)

Enhanced:
- ✓ Real ES256 cryptographic signing per record
- ✓ Ceiling enforcement: `credit = min(value_aud, value_ceiling_aud)`
- ✓ Three visually distinct record states with real data from backend
- ✓ Credited values calculated by backend (not mock)
- ✓ UCP negotiation log showing protocol steps
- ✓ Record signing log with verification status per record
- ✓ Signature display (transparency)

**Files**:
```
Components Enhanced:
├── EvidenceTimeline.tsx (uses real state, shows credited_value, expandable log)
├── UCPLog.tsx (NEW - UCP negotiation visualization)
└── App.tsx (passes negotiation log)

Backend Already Complete:
└── src/agent/main.py (signing, valuation, UCP logging)
```

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     React UI (P5, P6)                        │
│  Chat Pane | Results | Evidence Timeline | UCP Log | Transcript
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                 Agent Service (FastAPI)                      │
│  • Parse intent (LLM)                                        │
│  • Fan-out to merchants                                      │
│  • Rank products (LLM)                                       │
│  • Sign BenefitRecords (ES256)                               │
│  • Calculate credited values (ceiling enforcement)           │
│  • Build UCP log & record state log                          │
└─────────────────────────────────────────────────────────────┘
         ↕                                    ↕
    ┌─────────────┐            ┌──────────────────────────┐
    │   Merchant  │            │ Valuation Module         │
    │  Products   │            │ • Signing (ES256)        │
    │  (Mock)     │            │ • Canonical JSON         │
    └─────────────┘            │ • Credit calculation     │
                               │ • Verification          │
                               └──────────────────────────┘
```

### Data Flow

```
User Query: "USB-C charger"
  ↓
BondLayer Toggle: ON
  ↓
POST /query → Agent Service
  ├─ Parse Intent: "Find fast-charging USB-C adapter"
  ├─ Fan Out: Query voltway, citycircuit, northgear
  ├─ Rank: LLM ranks by price, availability, fit
  ├─ Add Benefits (BondLayer ON):
  │  ├─ Voltway: Create BenefitRecord(value=2.99, ceiling=4.49)
  │  ├─ Sign: ES256 with voltway's private key
  │  ├─ Credit: min(2.99, 4.49) = 2.99 ✓
  │  ├─ State: "signed_priced"
  │  ├─ CityCircuit: value=0 (policy), signed_unpriced
  │  └─ NorthGear: value=50 (warranty), signed_priced
  ├─ Build UCP Log: [negotiate → sign → verify → complete]
  ├─ Build Record Log: [{status: signed_priced, credited: 2.99, verified: true}, ...]
  ↓
AgentResponse:
  ├─ results[3 products]
  │  └─ evidence_records[benefits with state, credited_value, signature]
  ├─ ucp_negotiation_log[7 steps]
  ├─ records_state_log[3 records with credit details]
  └─ transcript: system_prompt + completion
  ↓
React UI:
  ├─ Results: Show ranked products
  ├─ Evidence Timeline:
  │  ├─ ✓ Signed & Priced (green): 2 records, $52.99 total
  │  ├─ 📋 Signed & Unpriced (yellow): 1 record, $0 value
  │  └─ ⚠ Unsigned (orange): 0 records
  ├─ UCPLog: Show all negotiation steps with icons
  └─ Record Log (expandable): Per-record signing status
```

## The Three Record States

### State 1: ✓ Signed & Priced (Green)
- **Signed**: Has valid ES256 signature
- **Priced**: value_aud > 0 and value_ceiling_aud > 0
- **Credited**: min(value_aud, value_ceiling_aud)
- **Example**: Voltway 10% loyalty ($2.99 on $29.99)
  - Display: "+$2.99 credited" with signature prefix

### State 2: 📋 Signed & Unpriced (Yellow)
- **Signed**: Has valid ES256 signature
- **Unpriced**: value_aud == 0 (qualitative benefit)
- **Credited**: $0 (but visibly verified)
- **Example**: CityCircuit 30-day guarantee
  - Display: "Credited: $0" with "verified" badge

### State 3: ⚠ Unsigned (Orange)
- **Unsigned**: No signature (or invalid)
- **Claimed Value**: Shown but with warning
- **Credited**: Always $0
- **Example**: "$50 agent bonus" (when BondLayer OFF)
  - Display: "Claimed: $50 → Credited: $0"

## Trust Invariants

The implementation enforces three critical security properties:

### Invariant 1: Tampered Records Fail Verification
```python
signed_record = create_signed_record(record, key)
tampered = BenefitRecord(..., signature="FAKE", canonical_json=...)
verify_benefit_record(tampered, key) # → False
```
**Demonstrated**: UI shows "verified: false" for tampered signatures

### Invariant 2: Unsigned Records Credit Zero
```python
unsigned = BenefitRecord(..., signature=None)
credit_benefit(unsigned) # → CreditedBenefit(..., credited_value=0.0)
```
**Demonstrated**: Unsigned records show "Credited: $0" with orange warning

### Invariant 3: Ceiling Caps Credit (Attack Defense)
```python
# Merchant claims $10,000 warranty with $100 ceiling
attack_record = BenefitRecord(value_aud=10000, value_ceiling_aud=100)
signed = create_signed_record(attack_record, key)
credit_benefit(signed) # → CreditedBenefit(..., credited_value=100.0)
```
**Demonstrated**: Even signed records respect ceiling in calculation

## Running the Demo

### Prerequisites
- Python 3.10+ with pip
- Node.js 18+ with npm
- OpenAI API key (for LLM ranking) or fallback to price-based ranking

### Setup
```bash
cd round2/chat-app

# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies
cd src/ui && npm install && cd ../..
```

### Launch (Terminal 1, 2, 3)
```bash
# Terminal 1: Merchant Service
python -m src.merchant.main
# ✓ Running on http://localhost:8000

# Terminal 2: Agent Service
export OPENAI_API_KEY=sk-...  # Add your key or leave unset
python -m src.agent.main
# ✓ Running on http://localhost:8001

# Terminal 3: React UI
cd src/ui && npm run dev
# ✓ http://localhost:5173
```

### Demo Scenario
1. **Open** http://localhost:5173
2. **Enter query**: "USB-C charger fast charging"
3. **BondLayer ON** (default):
   - See 3 ranked products
   - Evidence: ✓ Signed benefits, 📋 Free shipping, etc.
   - Total credited: ~$53
4. **Pin this run**
5. **Toggle BondLayer OFF**:
   - Re-runs same query
   - Different ranking (no benefits)
   - Evidence: Only unsigned "$50 bonus" → $0 credited
6. **Toggle back to pinned (BondLayer ON)**:
   - See the difference side-by-side
   - Benefits are credited, ranking changes
7. **Expand Evidence Timeline**:
   - See three states with colors
   - Click "Record Signing Log" to see details
8. **View UCP Log**:
   - Timeline showing negotiation steps
   - Icons for each phase (negotiate → sign → verify)

## Key Files

### Frontend
| File | Purpose | Status |
|------|---------|--------|
| `src/ui/src/App.tsx` | Main layout, state management | ✓ P5 |
| `src/ui/src/App.css` | ProductHunt theme (1000+ lines) | ✓ P5 + P6 |
| `src/ui/src/components/ChatPane.tsx` | Query input, toggle | ✓ P5 |
| `src/ui/src/components/ResultsView.tsx` | Ranked products | ✓ P5 |
| `src/ui/src/components/EvidenceTimeline.tsx` | Record states | ✓ P5 + **P6 Enhanced** |
| `src/ui/src/components/TranscriptPanel.tsx` | Prompt + completion | ✓ P5 |
| `src/ui/src/components/UCPLog.tsx` | Negotiation timeline | ✓ **P6 New** |

### Backend
| File | Purpose | Status |
|------|---------|--------|
| `src/agent/main.py` | Agent service with signing + valuation | ✓ **Complete** |
| `src/merchant/main.py` | Mock merchant products | ✓ Existing |
| `../valuation/signing.py` | ES256 signing | ✓ (used by agent) |
| `../valuation/canonical.py` | Canonical JSON | ✓ (used by signing) |
| `../valuation/effective_cost.py` | Credit calculation | ✓ (used by agent) |
| `../tests/test_invariants.py` | Trust invariant tests | ✓ Comprehensive |

## Commits (P5 + P6)

```
ef2f161 docs: P6 trust and loyalty integration guide
ba35b6a P6: Integrate signing and valuation layer into chat UI
71fb2c6 demo: Working example of Issue #13 - signing and valuation
5bd39b2 docs: P5 implementation guide and architecture
4ee15bc P5: React UI - Chat pane, comparison switch, evidence timeline
```

## Features by Issue

| Issue | Feature | Status |
|-------|---------|--------|
| #18 | P5: React UI (chat, switch, evidence) | ✓ Complete |
| #15 | Agent pipeline (parse, rank, recommend) | ✓ Complete |
| #13 | Trust layer (signing, valuation) | ✓ Complete |
| #11 | Demo chat app (parent issue) | ✓ In progress |

## Limitations (Intentional for Demo)

1. **Keys are mock** (not persisted to `/.well-known/ucp`)
2. **UCP negotiation is simplified** (flag-based, not full protocol)
3. **Identity verification is mocked** (no real UCP user lookup)
4. **Records aren't persisted** (in-memory, new query resets)
5. **No checkout integration** (settlement would be real in production)

## What's Demonstrated

✅ **End-to-end UCP integration** showing how an agent queries merchants  
✅ **Cryptographic trust** with ES256 signatures and verification  
✅ **Loyalty layer** showing how benefits influence ranking  
✅ **Before/after comparison** with BondLayer ON and OFF  
✅ **Transparency** with audit logs (UCP + record signing)  
✅ **Attack defense** with ceiling enforcement  
✅ **Three record states** visually distinct and calculated correctly  

## Judges' View

The demo makes the value proposition immediate:
1. Enter a query
2. See results with and without loyalty benefits
3. Observe the ranking difference
4. Inspect the signed records (transparency)
5. Understand how unsigned claims are ignored

**Same product, same code, different ranking when benefits are verified.** That's the BondLayer story.

---

## References

- **Problem Statement**: `@round1/fpt.md`
- **Hackathon Rules**: `Hackathon Rulebook 2026 Final (EN).md`
- **Stage 1 Spec**: `round2/docs/stage1-agent-ready-catalog.md`
- **Architecture**: `round2/system-architecture.md`
- **Progress**: `round2/overview-progress.md`
- **Tests**: `round2/tests/test_invariants.py` (all three invariants verified)

---

**Deployment Ready**: The demo runs locally with no external dependencies beyond OpenAI API. It can be deployed as-is for presentation/evaluation, with real signing layer active.

**Total Lines**: ~2,500 backend + ~1,500 frontend = **4,000+ lines of code**  
**Test Coverage**: All three trust invariants tested  
**Documentation**: 1,500+ lines of implementation guides
