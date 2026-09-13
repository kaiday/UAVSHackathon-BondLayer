> Superseded 12/09 evening by DAY2-PLAN §4 WS-B

# P6: Trust and Loyalty Integration

**Status**: ✅ COMPLETE  
**Commit**: `ba35b6a` — "P6: Integrate signing and valuation layer into chat UI"  
**Branch**: `feat/bach`

## Overview

P6 integrates the **signing and valuation layer** (built in Phase 5) into the chat app UI, so records are actually cryptographically signed and credited values are calculated with ceiling enforcement. This phase demonstrates:

1. **Real Cryptographic Signing**: ES256 (P-256/SHA-256) per-record signatures
2. **Ceiling Enforcement**: Credit = min(value_aud, value_ceiling_aud)
3. **Three Record States**: Visually distinct unsigned/signed_unpriced/signed_priced
4. **UCP Integration**: Negotiation log showing signing and verification steps
5. **Trust Invariants**: The three core security properties that prevent attacks

## What P6 Changes

### Backend (Agent Service)
Already implemented (see P5 and earlier commits):
- ✓ Generates ES256 key pairs per merchant
- ✓ Creates BenefitRecord objects with benefit metadata
- ✓ Signs records using canonical JSON + ES256
- ✓ Calculates credited values with ceiling enforcement
- ✓ Tracks record state (signed_priced, signed_unpriced, unsigned)
- ✓ Returns UCP negotiation log showing protocol steps
- ✓ Returns record state log showing signing/verification per record

### Frontend (React UI) — NEW in P6
- **EvidenceTimeline**: Now groups records by **real state** from backend
- **Credited Values**: Display `credited_value` from backend, not just claimed value
- **UCPLog Component**: New component visualizing the negotiation steps
- **Record Log**: Expandable section showing signing status for each record
- **Signature Display**: Shows signature prefix and canonical JSON (for transparency)

## The Three Record States

All three states are now visually distinct and calculated with real signing:

### 1. ✓ Signed & Priced (Green)
- **Signed**: Has valid ES256 signature
- **Priced**: value_aud > 0
- **Credited**: min(value_aud, value_ceiling_aud)
- **Example**: Voltway 10% loyalty discount ($2.99 on $29.99 charger)
  - Signed: ✓ (ES256 verified)
  - Value: $2.99
  - Ceiling: $4.49
  - Credited: $2.99

### 2. 📋 Signed & Unpriced (Yellow)
- **Signed**: Has valid ES256 signature
- **Unpriced**: value_aud == 0
- **Credited**: $0 (but visibly verified and valuable)
- **Example**: CityCircuit 30-day money-back guarantee
  - Signed: ✓ (ES256 verified)
  - Value: $0 (unquantified benefit)
  - Ceiling: $0
  - Credited: $0
  - *Why?* Policy is qualitatively valuable but has no quantified monetary impact

### 3. ⚠ Unsigned (Orange)
- **Unsigned**: No signature
- **Never Credited**: Always $0 credit
- **Displayed**: But not cited/recommended
- **Example**: Planted "$50 agent bonus" (when BondLayer is OFF)
  - Signed: ✗ (no signature)
  - Claimed Value: $50
  - Credited: $0
  - *Why?* Unverified claims earn nothing; prevents merchant manipulation

## Trust Invariants Enforced

Per the FPT evaluation spec, three invariants must hold:

### Invariant 1: Tampered Record Fails Verify
```python
signed_record = create_signed_record(record, private_key)
tampered = copy(signed_record)
tampered.signature = "TAMPERED"
verify_benefit_record(tampered, key) → False ✓
```

### Invariant 2: Unsigned Record Credits Zero
```python
unsigned_record = BenefitRecord(..., signature=None)
credit_benefit(unsigned_record) → CreditedBenefit(..., credited_value=0.0) ✓
```

### Invariant 3: Ceiling Caps Credit (Attack Defense)
```python
# Attack: Merchant claims $10,000 warranty with $100 ceiling
attack_record = BenefitRecord(
  value_aud=10000.0,
  value_ceiling_aud=100.0
)
signed = create_signed_record(attack_record, key)
credited = credit_benefit(signed)
# Defense: Credited only $100, not $10,000 ✓
assert credited.credited_value == 100.0
```

## UI Components

### EvidenceTimeline (Updated)
```tsx
// Now uses real state from backend
const signedPriced = records.filter(r => r.state === 'signed_priced')
const signedUnpriced = records.filter(r => r.state === 'signed_unpriced')
const unsigned = records.filter(r => r.state === 'unsigned')

// Displays credited_value (not claimed value)
<span className="record-value">
  +${(record.credited_value || 0).toFixed(2)} credited
</span>

// Shows signature preview for transparency
{record.signature && <p className="record-sig">Signature: {record.signature}</p>}

// Expandable record log with verification status
<details className="record-log">
  <summary>Record Signing Log</summary>
  {records_state_log.map(log => (
    <div>{log.status}: ${log.credited} credited {log.verified && '(verified)'}</div>
  ))}
</details>
```

### UCPLog (New Component)
Visualizes the UCP negotiation steps:
```
🔍 parse_intent → Extracting shopping intent from user query
🌐 fan_out → Querying 3 merchants for products
📊 rank_products → Using LLM to rank products
🔗 ucp_negotiation → Negotiating capabilities (org.bondlayer.benefit_value)
✍️ record_signing → Signing 3 benefit records with ES256
✔️ record_verification → Verifying signatures and calculating credits
✅ ucp_complete → BondLayer negotiation complete
```

Each step shows details like:
- Capability negotiated
- Algorithm used (ES256)
- Merchants queried
- Number of records verified
- UCP header sent

## Data Flow (P6)

```
User Query
  ↓
Agent Service:
  1. Parse intent (LLM)
  2. Fan out to merchants
  3. Rank products (LLM)
  4. For each result:
     - Create BenefitRecord objects
     - Sign each with ES256
     - Calculate credited value (ceiling enforcement)
     - Track state and verification status
  5. Build UCP negotiation log
  6. Build record state log
  ↓
AgentResponse:
  - results[] with evidence_records[]
  - each record has: state, credited_value, signature, verified
  - ucp_negotiation_log[] (steps)
  - records_state_log[] (per-record signing/credit details)
  ↓
React UI:
  - EvidenceTimeline groups by state
  - Shows credited_value from backend
  - Expandable record log
  - UCPLog shows negotiation steps
```

## Testing Checklist

- [x] Signed+priced records show real credited values
- [x] Signed+unpriced records show $0 but visibly verified
- [x] Unsigned records show $0 and visibly unverified
- [x] Ceiling enforcement: $10k claim → $100 credit
- [x] Signature display: Signature prefix shown
- [x] Record log: Expandable list with state and credit per record
- [x] UCP log: Shows all negotiation steps
- [x] BondLayer ON: Records signed and credited
- [x] BondLayer OFF: Only unsigned claims shown (earning $0)
- [x] Comparison toggle: Can see difference between ON and OFF
- [x] Mobile responsive: All new components stack properly

## Files Changed

### Frontend
- `components/EvidenceTimeline.tsx` — Updated: Real state grouping, credited value display, record log
- `components/UCPLog.tsx` — New: UCP negotiation visualization
- `App.tsx` — Updated: Import UCPLog, pass negotiation log data
- `App.css` — Updated: Styles for record log, UCP log, signature display

### Backend (No changes needed - already integrated)
- `src/agent/main.py` — Already has full signing and valuation

## Key Design Decisions

1. **State-based Grouping**: Use `state` field from backend (not computed frontend)
   - Why? Ensures UI matches backend truth; prevents inconsistency

2. **Display Credited Value**: Show actual credit, not claimed value
   - Why? Emphasizes the trust boundary; unverified claims visibly earn $0

3. **Signature Snippets**: Show first 20 chars of base64 signature
   - Why? Proves signing happened without bloating UI with full 128-char sig

4. **Expandable Record Log**: Collapsible details section
   - Why? Shows full audit trail without cluttering main display

5. **UCP Log Visualization**: Timeline with icons and connector line
   - Why? Makes protocol visible; demonstrates complex negotiation

## Security Implications

This phase **proves the trust layer works**:
- ✓ Real cryptographic signing prevents tampering
- ✓ Ceiling enforcement prevents merchant inflation attacks
- ✓ Unsigned records visibly earn $0 (no false claims)
- ✓ Full audit trail (UCP log + record log) enables verification
- ✓ Canonical JSON ensures deterministic signing

The demo now **demonstrates the whole value proposition**:
1. Same query, same code path
2. BondLayer ON: Signed benefits are credited
3. BondLayer OFF: Only unsigned claims (earning $0)
4. Judges see: Before/after ranking, with transparent verification

## Known Limitations

- Real private key is mock (demo only)
- JWK export not to `/.well-known/ucp` (would need real server setup)
- No real UCP protocol negotiation (simplified flag-based)
- Records not persisted (in-memory demo)
- No real merchant identity verification

## What's Next

P7 would likely cover:
- [ ] Publish keys to `/.well-known/ucp` (real UCP compliance)
- [ ] Real identity verification via UCP
- [ ] Loyalty layer: Enrolment, eligibility gates at checkout
- [ ] Checkout integration: Settle credited values
- [ ] Multi-merchant negotiation (not just all-or-nothing toggle)
- [ ] Performance optimizations for real-world scale

## References

- **ES256 Spec**: RFC 6090 (Fundamentals of ECC) + RFC 7517 (JWK)
- **Stage 1 Spec**: `round2/docs/stage1-agent-ready-catalog.md` (§4, §10)
- **Canonical JSON**: `round2/valuation/canonical.py`
- **Signing**: `round2/valuation/signing.py`
- **Valuation**: `round2/valuation/effective_cost.py`
- **Tests**: `round2/tests/test_invariants.py`

---

**Summary**: P6 makes the signing and valuation layer visible and interactive in the demo. The three record states, credited values, and UCP negotiation log together demonstrate that BondLayer can securely extend merchants' ranking signals without requiring trust in the merchant's claims.

The judges see: Same product, same code, different ranking when benefits are verified. That's the whole pitch.
