from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="BondLayer Merchant Service",
    description="Merchant dashboard and onboarding service",
    version="0.1.0",
)

# CORS configuration for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["localhost:5173", "127.0.0.1:5173", "localhost:8001", "127.0.0.1:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Product(BaseModel):
    id: str
    name: str
    price: float
    description: str
    merchant: str
    in_stock: bool


# Mock product database per merchant
MERCHANT_PRODUCTS = {
    "voltway": [
        {"id": "v1", "name": "USB-C Charger 65W", "price": 29.99, "description": "Fast charging USB-C power adapter", "merchant": "voltway", "in_stock": True},
        {"id": "v2", "name": "Laptop Stand", "price": 34.99, "description": "Adjustable aluminum laptop stand", "merchant": "voltway", "in_stock": True},
        {"id": "v3", "name": "Wireless Mouse", "price": 19.99, "description": "Bluetooth wireless mouse with 2.4GHz", "merchant": "voltway", "in_stock": False},
    ],
    "citycircuit": [
        {"id": "c1", "name": "USB-C Charger 65W", "price": 24.99, "description": "Budget USB-C power adapter", "merchant": "citycircuit", "in_stock": True},
        {"id": "c2", "name": "Desk Organizer", "price": 12.99, "description": "Multi-compartment desk organizer", "merchant": "citycircuit", "in_stock": True},
        {"id": "c3", "name": "HDMI Cable 2m", "price": 8.99, "description": "High-speed HDMI 2.1 cable", "merchant": "citycircuit", "in_stock": True},
    ],
    "northgear": [
        {"id": "n1", "name": "USB-C Charger 65W", "price": 27.99, "description": "Premium USB-C charger with GaN tech", "merchant": "northgear", "in_stock": True},
        {"id": "n2", "name": "Phone Mount", "price": 15.99, "description": "Universal phone mount for car/desk", "merchant": "northgear", "in_stock": True},
        {"id": "n3", "name": "USB Hub 7-port", "price": 39.99, "description": "USB 3.0 hub with power delivery", "merchant": "northgear", "in_stock": True},
    ],
}


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "merchant"}


@app.get("/merchants/{merchant}/products", response_model=list[Product])
async def get_merchant_products(merchant: str, query: Optional[str] = Query(None)):
    """Get products from a specific merchant, optionally filtered by search query"""
    products = MERCHANT_PRODUCTS.get(merchant, [])

    if query:
        query_lower = query.lower()
        products = [p for p in products if query_lower in p["name"].lower() or query_lower in p["description"].lower()]

    return [Product(**p) for p in products]


@app.post("/merchants/{merchant}/quote")
async def get_merchant_quote(merchant: str, product_id: str, quantity: int = 1):
    """Get a quote for a product from a merchant"""
    products = MERCHANT_PRODUCTS.get(merchant, [])
    product = next((p for p in products if p["id"] == product_id), None)

    if not product:
        return {"error": "Product not found", "status": 404}

    total_price = product["price"] * quantity
    return {
        "merchant": merchant,
        "product_id": product_id,
        "product_name": product["name"],
        "unit_price": product["price"],
        "quantity": quantity,
        "total_price": total_price,
        "in_stock": product["in_stock"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("merchant.main:app", host="0.0.0.0", port=8000, reload=True)
