import os
import json
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import anthropic

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


class ShoppingQuery(BaseModel):
    query: str
    bondlayer_enabled: bool = True


class EvidenceRecord(BaseModel):
    id: str
    type: str
    description: str
    value: Optional[float] = None
    source: str
    signed: bool
    verified: bool


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


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "agent"}


@app.post("/query", response_model=AgentResponse)
async def handle_shopping_query(request: ShoppingQuery):
    """Handle a shopping query with full agent pipeline"""
    # 1. Parse intent
    parsed_intent = await parse_intent(request.query)

    # 2. Fan out to all merchants
    products_by_merchant = await fan_out_to_merchants(request.query)

    # 3. Rank products
    ranked_results = await rank_products_with_llm(request.query, products_by_merchant)

    # 4. Get final recommendation from LLM
    top_results = ranked_results[:3] if ranked_results else []
    recommendation_text = ""
    if top_results:
        best = top_results[0]
        recommendation_text = f"I recommend the {best.product_name} from {best.merchant} (${best.price}). {best.reasoning}"
    else:
        recommendation_text = "I couldn't find suitable products matching your query. Please try a different search."

    # 5. Build UCP header based on BondLayer switch
    ucp_header = None
    if request.bondlayer_enabled:
        # When enabled, include the BondLayer capability in the header
        ucp_header = "UCP-Agent: org.bondlayer.benefit_value"

    return AgentResponse(
        user_query=request.query,
        parsed_intent=parsed_intent,
        results=ranked_results,
        final_recommendation=recommendation_text,
        bondlayer_enabled=request.bondlayer_enabled,
        transcript={
            "intent_parse": "Extracted user intent",
            "fan_out": f"Queried {len(products_by_merchant)} merchants",
            "ranking": f"Ranked {len(ranked_results)} products",
            "ucp_negotiation": "UCP header: " + (ucp_header or "none"),
        },
        ucp_header=ucp_header,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.main:app", host="0.0.0.0", port=8001, reload=True)
