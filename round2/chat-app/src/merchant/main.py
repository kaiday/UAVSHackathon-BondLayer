from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="BondLayer Merchant Service",
    description="Merchant dashboard and onboarding service",
    version="0.1.0",
)

# CORS configuration for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["localhost:5173", "127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "merchant"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("merchant.main:app", host="0.0.0.0", port=8000, reload=True)
