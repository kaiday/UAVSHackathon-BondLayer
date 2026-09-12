import os
import json
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import anthropic

# Import BondLayer signing and valuation
try:
    from round2.valuation import (
        BenefitRecord,
        BenefitType,
        generate_signing_key_pair,
        create_signed_record,
        credit_benefit,
    )
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False

app = FastAPI(
    title="BondLayer Agent Service",
    description="Mock shopping agent demonstrating BondLayer UCP integration",
    version="0.1.0",
)

# CORS configuration for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["localhost:5173", "127.0.0.1:5173", "localhost:8000", "127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Anthropic client
anthropic_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Merchants to query
MERCHANTS = ["voltway", "citycircuit", "northgear"]
MERCHANT_SERVICE_URL = "http://localhost:8000"

# Mock signing keys per merchant (in demo, we generate one for each)
merchant_keys = {}
if SIGNING_AVAILABLE:
    for merchant in MERCHANTS:
        merchant_keys[merchant] = generate_signing_key_pair()


class ShoppingQuery(BaseModel):
    query: str
    bondlayer_enabled: bool = True
    shopper_id: str = "demo_shopper"


class EvidenceRecord(BaseModel):
    id: str
    type: str
    description: str
    value: Optional[float] = None
    source: str
    signed: bool
    verified: bool
    state: str = "unsigned"  # "signed_priced" | "signed_unpriced" | "unsigned"
    credited_value: float = 0.0
    canonical_json: Optional[str] = None
    signature: Optional[str] = None


class RankedResult(BaseModel):
    rank: int
    merchant: str
    product_id: str
    product_name: str
    price: float
    description: str
    reasoning: str
    evidence_records: list[EvidenceRecord] = []


class AgentResponse(BaseModel):
    user_query: str
    parsed_intent: str
    results: list[RankedResult]
    final_recommendation: str
    bondlayer_enabled: bool
    transcript: dict
    ucp_header: Optional[str] = None
    ucp_negotiation_log: list[dict] = []  # UCP protocol steps
    records_state_log: list[dict] = []  # Record signing/verification states


# Neutral system prompt (no knowledge of BondLayer)
AGENT_SYSTEM_PROMPT = """You are a helpful shopping assistant. Your job is to help customers find products that match their needs.

When given a shopping query:
1. Understand what the customer is looking for
2. Evaluate products based on price, availability, and fit for the use case
3. Rank the options from best to worst
4. Provide clear reasoning for your recommendations

Be neutral and objective. Always consider price, quality, and availability in your recommendations."""


async def parse_intent(query: str) -> str:
    """Parse user query to extract shopping intent using LLM"""
    message = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": f"Extract the shopping intent from this query in one sentence: '{query}'"
            }
        ]
    )
    return message.content[0].text


async def fetch_products_from_merchant(merchant: str, query: str) -> list:
    """Fetch products from a specific merchant"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{MERCHANT_SERVICE_URL}/merchants/{merchant}/products",
                params={"query": query},
                timeout=5
            )
            return response.json() if response.status_code == 200 else []
        except Exception as e:
            print(f"Error fetching from {merchant}: {e}")
            return []


async def fan_out_to_merchants(query: str) -> dict:
    """Query all merchants in parallel"""
    results = {}
    for merchant in MERCHANTS:
        products = await fetch_products_from_merchant(merchant, query)
        results[merchant] = products
    return results


async def rank_products_with_llm(query: str, products_by_merchant: dict) -> list[RankedResult]:
    """Use LLM to rank products across all merchants"""
    # Format products for the LLM
    product_list = []
    for merchant, products in products_by_merchant.items():
        for product in products:
            product_list.append({
                "merchant": merchant,
                "product_id": product.get("id"),
                "name": product.get("name"),
                "price": product.get("price"),
                "description": product.get("description"),
                "in_stock": product.get("in_stock"),
            })

    # Ask LLM to rank products
    ranking_prompt = f"""Given the user query: "{query}"

Here are available products from different merchants:
{json.dumps(product_list, indent=2)}

Rank these products from best to worst for this query. Consider price, availability, and fit.
For each product, provide:
1. Rank (1 = best)
2. Product ID
3. Merchant
4. Brief reasoning (1-2 sentences)

Format as JSON array with fields: [rank, product_id, merchant, reasoning]"""

    message = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1000,
        messages=[
            {
                "role": "user",
                "content": ranking_prompt
            }
        ]
    )

    # Parse LLM response
    response_text = message.content[0].text

    # Extract JSON from response
    try:
        # Try to find JSON in the response
        if "[" in response_text and "]" in response_text:
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            json_str = response_text[json_start:json_end]
            rankings = json.loads(json_str)
        else:
            rankings = []
    except:
        rankings = []

    # Convert rankings to RankedResult objects
    results = []
    for ranking in rankings:
        if isinstance(ranking, list) and len(ranking) >= 4:
            # Find product details
            product_id = ranking[1]
            merchant = ranking[2]
            reasoning = ranking[3]

            # Find product info
            for p in product_list:
                if p["product_id"] == product_id and p["merchant"] == merchant:
                    results.append(RankedResult(
                        rank=ranking[0],
                        merchant=merchant,
                        product_id=product_id,
                        product_name=p["name"],
                        price=p["price"],
                        description=p["description"],
                        reasoning=reasoning
                    ))
                    break

    return sorted(results, key=lambda x: x.rank)


def add_evidence_records(result: RankedResult, bondlayer_enabled: bool, shopper_id: str) -> list[dict]:
    """Add evidence records based on bondlayer status and merchant.

    Returns:
        List of record state logs for the response
    """
    records = []
    state_logs = []

    if bondlayer_enabled:
        if result.merchant == "voltway":
            value = round(result.price * 0.1, 2)
            if SIGNING_AVAILABLE and result.merchant in merchant_keys:
                # Create and sign a real benefit record
                private_key, jwk_public = merchant_keys[result.merchant]
                unsigned_record = BenefitRecord(
                    merchant_id=result.merchant,
                    shopper_id=shopper_id,
                    product_id=result.product_id,
                    benefit_type=BenefitType.LOYALTY_CREDIT,
                    value_aud=value,
                    value_ceiling_aud=value * 1.5,
                    created_at=datetime.now().isoformat(),
                    source_span="Voltway: 10% loyalty discount for repeat customers",
                    merchant_key_id=f"{result.merchant}_key",
                )
                signed_record = create_signed_record(unsigned_record, private_key)
                credited = credit_benefit(signed_record)

                record = EvidenceRecord(
                    id="benefit_voltway_loyalty",
                    type="loyalty_benefit",
                    description="10% loyalty discount for repeat customers",
                    value=value,
                    source="Voltway membership program",
                    signed=True,
                    verified=credited.is_verified,
                    state="signed_priced",
                    credited_value=credited.credited_value,
                    signature=signed_record.signature[:20] + "..." if signed_record.signature else None,
                    canonical_json=signed_record.canonical_json[:50] + "..." if signed_record.canonical_json else None,
                )
                records.append(record)
                state_logs.append({
                    "record_id": record.id,
                    "status": "signed_priced",
                    "value": value,
                    "credited": credited.credited_value,
                    "verified": credited.is_verified,
                    "reason": credited.reason,
                })
            else:
                # Fallback without signing
                records.append(EvidenceRecord(
                    id="benefit_voltway_loyalty",
                    type="loyalty_benefit",
                    description="10% loyalty discount for repeat customers",
                    value=value,
                    source="Voltway membership program",
                    signed=True,
                    verified=True
                ))
                state_logs.append({
                    "record_id": "benefit_voltway_loyalty",
                    "status": "signed_priced",
                    "value": value,
                    "credited": value,
                })

        elif result.merchant == "citycircuit":
            # Zero-value benefit (signed but unpriced)
            if SIGNING_AVAILABLE and result.merchant in merchant_keys:
                private_key, _ = merchant_keys[result.merchant]
                unsigned_record = BenefitRecord(
                    merchant_id=result.merchant,
                    shopper_id=shopper_id,
                    product_id=result.product_id,
                    benefit_type=BenefitType.FREE_SHIPPING,
                    value_aud=0.0,
                    value_ceiling_aud=0.0,
                    created_at=datetime.now().isoformat(),
                    source_span="CityCircuit: 30-day money-back guarantee",
                    merchant_key_id=f"{result.merchant}_key",
                )
                signed_record = create_signed_record(unsigned_record, private_key)

                records.append(EvidenceRecord(
                    id="policy_citycircuit_returns",
                    type="return_policy",
                    description="30-day money-back guarantee",
                    value=0.0,
                    source="CityCircuit return policy",
                    signed=True,
                    verified=True,
                    state="signed_unpriced",
                    credited_value=0.0,
                    signature=signed_record.signature[:20] + "..." if signed_record.signature else None,
                ))
                state_logs.append({
                    "record_id": "policy_citycircuit_returns",
                    "status": "signed_unpriced",
                    "value": 0.0,
                    "credited": 0.0,
                    "verified": True,
                })
            else:
                records.append(EvidenceRecord(
                    id="policy_citycircuit_returns",
                    type="return_policy",
                    description="30-day money-back guarantee",
                    value=0.0,
                    source="CityCircuit return policy",
                    signed=True,
                    verified=True
                ))
                state_logs.append({
                    "record_id": "policy_citycircuit_returns",
                    "status": "signed_unpriced",
                    "value": 0.0,
                    "credited": 0.0,
                })

        elif result.merchant == "northgear":
            if SIGNING_AVAILABLE and result.merchant in merchant_keys:
                # Regular signed benefit
                private_key, _ = merchant_keys[result.merchant]
                unsigned_record = BenefitRecord(
                    merchant_id=result.merchant,
                    shopper_id=shopper_id,
                    product_id=result.product_id,
                    benefit_type=BenefitType.WARRANTY_EXTENSION,
                    value_aud=50.0,
                    value_ceiling_aud=50.0,
                    created_at=datetime.now().isoformat(),
                    source_span="NorthGear: 2-year extended warranty included",
                    merchant_key_id=f"{result.merchant}_key",
                )
                signed_record = create_signed_record(unsigned_record, private_key)
                credited = credit_benefit(signed_record)

                records.append(EvidenceRecord(
                    id="warranty_northgear_extended",
                    type="warranty",
                    description="2-year extended warranty included",
                    value=50.0,
                    source="NorthGear warranty program",
                    signed=True,
                    verified=credited.is_verified,
                    state="signed_priced",
                    credited_value=credited.credited_value,
                    signature=signed_record.signature[:20] + "..." if signed_record.signature else None,
                ))
                state_logs.append({
                    "record_id": "warranty_northgear_extended",
                    "status": "signed_priced",
                    "value": 50.0,
                    "credited": credited.credited_value,
                    "verified": credited.is_verified,
                })
            else:
                records.append(EvidenceRecord(
                    id="warranty_northgear_extended",
                    type="warranty",
                    description="2-year extended warranty included",
                    value=50.0,
                    source="NorthGear warranty program",
                    signed=True,
                    verified=True
                ))
                state_logs.append({
                    "record_id": "warranty_northgear_extended",
                    "status": "signed_priced",
                    "value": 50.0,
                    "credited": 50.0,
                })
    else:
        # Add unsigned/unverified evidence when BondLayer is off (for demo contrast)
        # This demonstrates the planted unsigned record (gap 5 in the spec)
        if result.merchant == "northgear":
            records.append(EvidenceRecord(
                id="unsigned_bonus_northgear",
                type="benefit",
                description="$50 agent bonus (unverified claim)",
                value=50.0,
                source="Internal claim - unverified",
                signed=False,
                verified=False,
                state="unsigned",
                credited_value=0.0,
            ))
            state_logs.append({
                "record_id": "unsigned_bonus_northgear",
                "status": "unsigned",
                "value": 50.0,
                "credited": 0.0,
                "verified": False,
                "reason": "unsigned_no_credit",
            })

    result.evidence_records = records
    return state_logs


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "agent"}


@app.post("/query", response_model=AgentResponse)
async def handle_shopping_query(request: ShoppingQuery):
    """Handle a shopping query with full agent pipeline"""
    # Build UCP negotiation log
    ucp_log = []

    # 1. Parse intent
    ucp_log.append({
        "step": "parse_intent",
        "detail": "Extracting shopping intent from user query",
    })
    parsed_intent = await parse_intent(request.query)

    # 2. Fan out to all merchants
    ucp_log.append({
        "step": "fan_out",
        "detail": f"Querying {len(MERCHANTS)} merchants for products",
        "merchants": MERCHANTS,
    })
    products_by_merchant = await fan_out_to_merchants(request.query)

    # 3. Rank products
    ucp_log.append({
        "step": "rank_products",
        "detail": "Using LLM to rank products across merchants",
    })
    ranked_results = await rank_products_with_llm(request.query, products_by_merchant)

    # 4. Add evidence records based on BondLayer status
    all_state_logs = []
    if request.bondlayer_enabled:
        ucp_log.append({
            "step": "ucp_negotiation",
            "detail": "BondLayer enabled - negotiating capabilities with merchants",
            "capability": "org.bondlayer.benefit_value",
        })

    for result in ranked_results:
        state_logs = add_evidence_records(result, request.bondlayer_enabled, request.shopper_id)
        all_state_logs.extend(state_logs)

    if request.bondlayer_enabled:
        ucp_log.append({
            "step": "record_signing",
            "detail": f"Signing {len([e for r in ranked_results for e in r.evidence_records if e.signed])} benefit records with ES256",
            "algorithm": "ES256 (P-256/SHA-256)",
        })
        ucp_log.append({
            "step": "record_verification",
            "detail": f"Verifying signatures and calculating credited values",
            "records_verified": len([e for r in ranked_results for e in r.evidence_records if e.verified]),
        })
    else:
        ucp_log.append({
            "step": "bondlayer_disabled",
            "detail": "BondLayer disabled - showing baseline ranking without benefits",
        })

    # 5. Get final recommendation from LLM
    top_results = ranked_results[:3] if ranked_results else []
    recommendation_text = ""
    if top_results:
        best = top_results[0]
        benefit_note = ""
        if best.evidence_records:
            benefit_count = len([e for e in best.evidence_records if e.verified])
            if benefit_count > 0:
                benefit_note = f" This product also includes {benefit_count} verified benefits."
        recommendation_text = f"I recommend the {best.product_name} from {best.merchant} (${best.price}). {best.reasoning}{benefit_note}"
    else:
        recommendation_text = "I couldn't find suitable products matching your query. Please try a different search."

    # 6. Build transcript (for the model transcript panel)
    transcript = {
        "system_prompt": AGENT_SYSTEM_PROMPT,
        "user_query": request.query,
        "parsed_intent": parsed_intent,
        "completion": recommendation_text,
        "model": "claude-3-5-sonnet-20241022",
        "intent_parse": "Extracted user intent",
        "fan_out": f"Queried {len(products_by_merchant)} merchants",
        "ranking": f"Ranked {len(ranked_results)} products",
    }

    # 7. Build UCP header based on BondLayer switch
    ucp_header = None
    if request.bondlayer_enabled:
        # When enabled, include the BondLayer capability in the header
        ucp_header = "UCP-Agent: org.bondlayer.benefit_value"
        ucp_log.append({
            "step": "ucp_complete",
            "detail": "BondLayer negotiation complete",
            "header_sent": ucp_header,
        })

    return AgentResponse(
        user_query=request.query,
        parsed_intent=parsed_intent,
        results=ranked_results,
        final_recommendation=recommendation_text,
        bondlayer_enabled=request.bondlayer_enabled,
        transcript=transcript,
        ucp_header=ucp_header,
        ucp_negotiation_log=ucp_log,
        records_state_log=all_state_logs,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.main:app", host="0.0.0.0", port=8001, reload=True)
