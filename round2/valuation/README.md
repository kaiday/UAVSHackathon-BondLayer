# BondLayer Valuation & Signing Module

Core cryptographic and valuation systems for BondLayer benefit records.

## Architecture

### B1: Trust Invariants (tests/test_invariants.py)

Three critical invariants verified by automated tests:

1. **Tampered records fail verification** — An ES256 signature becomes invalid if any field is modified
2. **Unsigned records credit zero** — Only signed, verified records can contribute to shopping cost
3. **Ceiling caps credit** — `value_ceiling_aud` defense against claiming excessive values (e.g., $10k warranty)

### B2: Canonical JSON Serialization (canonical.py)

Deterministic JSON encoding for signing:
- Sorted keys, no whitespace, UTF-8
- Enables identical signatures across implementations
- Round-trip test ensures data integrity

### B3: ES256 Signing (signing.py)

ECDSA signatures using P-256 curve and SHA-256 hash:
- Per-record, detached signatures (not transport-level)
- Keys published in JWK format under `/.well-known/ucp`
- Permits long-term evidence: agents cache and re-verify records post-checkout

### Effective Cost Calculation (effective_cost.py)

Ranks products after applying verified benefits:
```
effective_cost = max(0, base_price - sum(credited_values))
credited = min(value_aud, value_ceiling_aud) if verified else 0
```

## Data Types (types.py)

```python
class BenefitRecord:
    merchant_id: str
    shopper_id: str
    product_id: str
    benefit_type: BenefitType  # DISCOUNT, WARRANTY, LOYALTY_CREDIT, etc.
    value_aud: float           # Claimed value
    value_ceiling_aud: float   # Maximum credit (attack defense)
    created_at: str            # ISO timestamp
    source_span: str           # Human-readable citation
    merchant_key_id: str       # Key used for signature
    signature: Optional[str]   # Base64url-encoded ES256 signature
    canonical_json: Optional[str]  # Signed payload

class CreditedBenefit:
    benefit_record: BenefitRecord
    credited_value: float      # Actual credit applied (≤ ceiling)
    is_verified: bool          # Signature valid + ceiling applied
    reason: str                # "verified_credited" | "unsigned_no_credit" | etc.
```

## Usage Examples

### Signing a Benefit

```python
from valuation import BenefitRecord, BenefitType, generate_signing_key_pair, create_signed_record

# Generate merchant signing key (once)
private_key, jwk_public = generate_signing_key_pair()

# Create unsigned record
record = BenefitRecord(
    merchant_id="voltway",
    shopper_id="shopper_123",
    product_id="laptop",
    benefit_type=BenefitType.LOYALTY_CREDIT,
    value_aud=50.0,
    value_ceiling_aud=100.0,
    created_at="2026-09-12T12:00:00",
    source_span="Loyalty customers: 50 AUD credit",
    merchant_key_id="voltway_2026_key_1",
)

# Sign it
signed_record = create_signed_record(record, private_key)
# Now has: signature, canonical_json fields populated
```

### Verifying & Crediting

```python
from valuation import credit_benefit, VerificationKey

# Reconstruct public key from JWK
verification_key = VerificationKey(
    kid="voltway_2026_key_1",
    kty="EC",
    crv="P-256",
    x=jwk_public["x"],
    y=jwk_public["y"],
)

# Evaluate credit
credited = credit_benefit(signed_record, verification_key)
print(f"Credited: ${credited.credited_value}, Verified: {credited.is_verified}")
```

### Calculating Effective Cost

```python
from valuation import calculate_effective_cost

base_price = 999.99
benefits = [signed_record1, signed_record2, unsigned_planted]
verification_keys = {"voltway_2026_key_1": verification_key}

effective_cost, details = calculate_effective_cost(base_price, benefits, verification_keys)
print(f"Effective price: ${effective_cost}")
for credited_benefit in details:
    print(f"  {credited_benefit.benefit_record.source_span}: ${credited_benefit.credited_value}")
```

## Record States (B7-B9)

Demo surfaces three distinct states to users:

### 1. Signed + Priced
- Signature valid, value > 0
- Credited and ranked impact
- Example: "Loyalty: $50 credit" ✓ cited, ✓ credited

### 2. Signed + Unpriced
- Signature valid, value = 0
- Display as evidence but zero cost impact
- Example: "Free returns" ✓ cited, $0 credited

### 3. Unsigned (Planted)
- No signature or signature fails
- Displayed in log, never credited
- Example: "Planted: $50 bonus" ✗ cited, $0 credited (defense against greenwashing)

## Test Coverage

All 9 tests in `tests/test_invariants.py` pass:

```
PASSED TestCanonicalJSON::test_round_trip
PASSED TestCanonicalJSON::test_deterministic_output
PASSED TestES256Signing::test_sign_and_verify
PASSED TestES256Signing::test_tampered_record_fails_verify         ← Invariant 1
PASSED TestES256Signing::test_unsigned_record_credits_zero          ← Invariant 2
PASSED TestES256Signing::test_ceiling_caps_credit                   ← Invariant 3
PASSED TestRecordStates::test_signed_priced_record
PASSED TestRecordStates::test_signed_unpriced_record
PASSED TestRecordStates::test_unsigned_record_displayed_never_cited
```

## References

- ES256 spec: `ucp.dev/2026-04-08/specification/signatures/`
- Key format: RFC 7517 (JWK)
- Stage 1 spec: `docs/stage1-agent-ready-catalog.md` (§9 signing)
- FPT evaluation: `@round1/fpt.md` (section: Semantic Matching & Intent Decoding)

## Scope & Gaps

**Implemented:**
- ES256 signing and verification
- Canonical JSON serialization
- Trust invariants (3/3)
- Record state tracking
- Effective cost ranking

**Placeholders (for demo):**
- 🔲 Key distribution server (uses in-memory mocks)
- 🔲 Revocation/expiry checks
- 🔲 Integration with DAO layer

**Not in scope (deliberate):**
- Real payment processing
- Production key management
- Negotiation/counter-offer protocol (gap 8)
