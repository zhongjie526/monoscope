"""Monad Watchdog — FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import db
from app.routers import wallet, fraud, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    db.connect()
    print("✅ Neo4j connected")
    yield
    db.close()
    print("🛑 Neo4j disconnected")


app = FastAPI(
    title="Monad Watchdog",
    description="AI-powered fraud detection and wallet analytics for Monad",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wallet.router, prefix="/api/wallet", tags=["Wallet"])
app.include_router(fraud.router, prefix="/api/fraud", tags=["Fraud Detection"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])


@app.get("/")
async def root():
    return {
        "name": "Monad Watchdog 🐕",
        "version": "0.1.0",
        "chain": "Monad Mainnet (143)",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    try:
        result = await db.aquery("RETURN 1 AS ok")
        neo4j_ok = len(result) > 0
    except Exception:
        neo4j_ok = False
    return {"status": "ok" if neo4j_ok else "degraded", "neo4j": neo4j_ok}
