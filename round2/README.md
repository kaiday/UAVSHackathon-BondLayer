# Round 2: BondLayer Demo Applications

## Architecture

Two applications over three data models (`Catalogs`, `Policy`, `Promotions`):

### 1. Dashboard — Merchant App
- **Owner:** Manh (`feat/nguyen-ucp-head`)
- **Scope:** Merchant UI for managing catalog, policy, and promotions
- **Key Features:**
  - Onboarding via CSV/txt upload
  - Intelligent suggestions on catalog and policy
  - Remediation logs
  - Readiness scoring (5 dimensions)
  - Analytics page (demo-only, labeled as such)

### 2. Demo Chat App — Integration Proof
- **Owner:** Bach (`feat/bach-records-signing`)
- **Scope:** Mock shopping agent demonstrating BondLayer effect
- **Key Features:**
  - Mock agent with neutral system prompt
  - BondLayer on/off switch
  - Detail logs: UCP negotiation, loyalty layer, policies applied
  - Record signing and verification
  - Loyalty layer with identity and consent

### 3. Dashboard Intelligence — RAG & DAO
- **Owner:** Hieu (`feat/hieu-interpreter`)
- **Scope:** Intent parsing, RAG over catalog/policy, data persistence
- **Key Features:**
  - Intent parser (R01, all 30 eval requests)
  - RAG-based improvement suggestions with source quotes
  - DAO layer for catalogs, policy, promotions
  - Policy → BenefitRecord draft generation with approval gate

## Folder Structure

```
round2/
├── README.md                          # This file
├── overview-progress.md               # Day 1 status (Revised 12/09 13:05 AEST)
├── system-architecture.md             # Architecture decisions (to be created)
├── types.py                           # Shared data models (from dev branch)
├── electronics.csv                    # 148 SKUs, 62 model keys
├── manifests.json                     # Merchant configs (voltway, citycircuit, northgear)
│
├── dashboard/                         # Manh's app
│   ├── __init__.py
│   ├── app.py                         # Main Flask/Django app
│   └── README.md
│
├── demo-chat-app/                     # Bach's app
│   ├── __init__.py
│   ├── app.py                         # Chat interface
│   ├── agent.py                       # Mock shopping agent
│   └── README.md
│
├── intelligence/                      # Hieu's RAG & DAO
│   ├── __init__.py
│   ├── interpreter.py                 # Intent parsing
│   ├── rag.py                         # RAG engine
│   ├── dao.py                         # Data access layer
│   └── README.md
│
├── adapters/                          # Shared adapters
│   ├── __init__.py
│   └── catalog.py                     # CSV → Sku normalization (landed 12:52)
│
├── ucp/                               # UCP Integration (Nguyen's head)
│   ├── __init__.py
│   ├── profile.py                     # UCP profile
│   ├── capabilities.py                # Capabilities negotiation
│   ├── server.py                      # UCP server endpoint
│   ├── onboard.py                     # Onboarding endpoints (landed 12:53)
│   └── README.md
│
├── interpreter/                       # Intent parsing (Hieu)
│   ├── __init__.py
│   ├── parser.py                      # Intent parse (landed 12:59)
│   └── resolver.py                    # Constraint resolver (stub)
│
├── valuation/                         # Cost calculation & verification
│   ├── __init__.py
│   ├── effective_cost.py              # Canonical cost calculation
│   ├── signing.py                     # ES256 signatures
│   └── invariants.py                  # Trust invariants
│
├── tests/                             # Test suite
│   ├── test_invariants.py             # Signing & valuation tests
│   ├── test_catalog.py                # Adapter tests (landed 12:52)
│   ├── test_ucp.py                    # UCP protocol tests (landed 12:52)
│   ├── test_interpreter.py            # Parser tests (landed 12:59)
│   └── test_rag.py                    # RAG engine tests
│
├── docs/                              # Documentation
│   ├── stage1-agent-ready-catalog.md  # Spec for signatures, keys (landed 12:32)
│   ├── GAPS.md                        # Known gaps
│   └── WORKPLAN.md                    # Team assignments
│
└── pyproject.toml                     # Python project config (landed 12:47)
```

## Status (as of 2026-09-12 13:05 AEST)

| Branch | Lines | Status | Owner |
|---|---|---|---|
| `feat/nguyen-ucp-head` | 1,443 | Dashboard core shipped | Nguyen |
| `feat/hieu-interpreter` | 346 | Intent parser shipped, needs merge | Hieu |
| `feat/bach-records-signing` | 0 | **Critical: No code yet** | Bach |
| `round2/dev` | — | **Integration head** | Team |

### Critical Next Steps
1. **H0:** Hieu merges `round2/dev` (missing `pyproject.toml`)
2. **B1:** Bach starts with `tests/test_invariants.py` (red → green)
3. **14:30:** Three architectural decisions due

## Key References
- Problem Statement: `@round1/fpt.md`
- Hackathon Rules: `Hackathon Rulebook 2026 Final (EN).md`
- Issue #11: Demo Chat App (this round)
- Issue #9: Overall architecture and decisions (parent)
