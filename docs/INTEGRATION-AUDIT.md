# Integration audit — 13 September 2026

## Result

The active merchant and buyer-agent paths now use real uploaded data and server-side OpenAI
calls. Catalogue-only onboarding, policy review/publication, model-backed assistance,
comparison, benefit verification and local request history are connected. Historical
synthetic data and rule-based explanations require an explicit offline/test mode.

## Connections checked and repaired

| User action | Connected implementation |
|---|---|
| Validate and publish a catalogue | `onboard.py` → adapter → atomic merchant storage → live catalogue |
| Ask BondLayer | Console → `POST /onboard/ask/{merchant}` → OpenAI, using the current report and checked diagnostic citations |
| Understand a shopping request | Buyer agent → `interpreter/openai.py` → structured constraints → deterministic matching |
| Upload policy text/PDF | Benefit records page → `POST /onboard/policies/{merchant}` → actual OpenAI extraction |
| Review extracted facts | Real draft records, source passages, editable facts/conditions and merchant-entered ceilings |
| Approve and publish benefits | Merchant approval → ES256 signature → persistent records/public keys → UCP catalogue extension |
| Verify and value a benefit | Public key from the merchant profile → signature/issuer/scope checks → shopper-entered value caps |
| Merchant-side intent proposals | Live decoder plus the merchant's actual catalogue and verified records |
| Confirm an offer | Checkout re-verifies the cited published records and includes the honoured envelopes |
| Inspect request history | Actual buyer-agent run → authenticated HTTP submission → merchant storage → Request console; no invented control run |
| Edit merchant settings | Profile update persists; signing identity changes are rejected while records are published |
| Check OpenAI configuration | Settings shows configuration separately from a real connection test and completion ID |

Additional fixes:

- Merchant domains discovered from profiles now reach **both** valuation and constraint
  resolution. The original fixed demo-domain map silently excluded new merchants' benefits.
- Product codes are scoped by merchant during resolution; identical local SKUs in different
  stores no longer overwrite each other.
- Live hard requirements filter the ranking rather than merely annotating an unsuitable
  product. A resolver failure does not quietly bypass these checks.
- The model selects real SKU/category identifiers and numbered source passages using a
  constrained schema. The server supplies verbatim source text and preserves it in the terms.
- Failed extraction does not overwrite the prior draft set. Unapproved claims are not published.
- Catalogue replacement preserves published benefits and prevents accidental signing-identity changes.
- SQLite connections close after each transaction, fixing Windows file locks on policy data.
- Both services load the same root-first configuration before resolving the uploads directory.
- Live shopper values default to zero, and demo membership/trade-in eligibility is not assumed.
- Model errors are shown explicitly. Templates are limited to `BONDLAYER_AI_MODE=rules`.
- The static console export was rebuilt, including the live AI/policy controls.

## Live API evidence

Real requests completed against OpenAI using the configured key and `gpt-4o-mini`. The check
used an isolated temporary merchant and a test policy, not existing customer documents.

| Operation | Actual OpenAI completion ID |
|---|---|
| Merchant assistance | `chatcmpl-ENVJRy8sWka9tegUJVJ1zkYV4AcHk` |
| Policy extraction | `chatcmpl-ENVJnk1VtqnSRCwFP5F6WEq8577L0` |
| Shopper intent | `chatcmpl-ENVJoZdm9rk4HgiHDVK3fzVLN7708` |
| Comparison explanation | `chatcmpl-ENVKB9OQ0hIdOAnV81ChiHaywamv9` |

The uploaded test laptop had a $999 shelf price. A real extracted 60-day returns record was
reviewed, given a $40 merchant ceiling and signed. With an explicitly supplied $40 shopper
value, the agent verified and credited $40, cited the record to answer the returns requirement,
and received a checkout confirmation honouring that same record. The saved request report
was readable from the console API. Restarting the app restored and verified the published
record and merchant key again. No payment was processed.

To repeat this paid API check after launcher setup:

```powershell
.\.venv\Scripts\python.exe scripts/check_live_openai.py
```

On macOS/Linux use `.venv/bin/python scripts/check_live_openai.py`. The script makes real
API requests and creates temporary test data; its assertions do not stub OpenAI responses.
Model output can vary, and invalid output is rejected rather than silently repaired with
prepared answers.

## Automated verification

- Merchant suite: **314 passed**.
- Buyer-agent suite: **23 passed**.
- Console TypeScript check, ESLint and production static build: **passed**.
- Buyer-agent inline JavaScript syntax check: **passed**.
- Static-export regression checks confirm the shipped UI references the live endpoints.
- Automated regression tests use explicit offline mode or provider transport doubles, so
  running tests does not accidentally spend a developer's API quota.

Coverage includes real signature generation/verification, restart persistence, cross-store
SKU collisions, hard-filter enforcement, unsupported evidence rejection, visible provider
errors, draft preservation, and live-request report persistence. Validation was API-level
end-to-end plus frontend build checks; full browser automation was not run.

## Remaining product boundaries

- Checkout confirms the offer and its records. Payment processing, stock reservation and
  fulfilment/order management are not implemented.
- Live membership/account linking and external trade-in eligibility verification are not
  implemented; the live agent does not assume those conditions hold.
- External marketplace deployment/discovery, production authentication and protocol
  certification remain separate integration work.
- The policy page currently manages one combined document/draft set per merchant. Publishing
  replaces the live benefit set with the approved drafts.
- The existing deterministic resolver and bundler support their implemented product vocabulary
  and recipes; an OpenAI decode does not make every possible requirement executable.
- Request history now uses authenticated HTTP ingestion on the merchant. The two processes
  no longer require a shared uploads directory; Fly persists reports on the merchant volume.

## Unified local/Fly follow-up

Deployment configuration from `round2-deploy` is integrated into `round2/dev`. The images
install dependencies from the current project metadata, and the merchant image builds the
console from source. OpenAI credentials are configured on both Fly apps. A separate shared
service token authenticates `POST /internal/requests`.

Validation of this follow-up: **357 merchant tests and 37 buyer-agent tests passed**. Both
Docker images built, and `scripts/check_deployment.py` passed with two separate containers,
authenticated report submission, merchant insights, and catalogue/history persistence after
replacing the merchant container. This was a local Docker check, not a deployment to a Fly
account. See [the deployment guide](deploy-fly.md) for both run modes.

These boundaries are visible behaviour, not simulated success responses.
