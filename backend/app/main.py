"""Monoscope — On-chain intelligence for Monad."""

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import db
from app.routers import wallet, fraud, fraud_advanced, search

INDEXER_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "indexer_state.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    db.connect()
    print("✅ Neo4j connected")
    yield
    db.close()
    print("🛑 Neo4j disconnected")


app = FastAPI(
    title="Monoscope",
    description="On-chain intelligence for Monad",
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
app.include_router(fraud_advanced.router, prefix="/api/fraud", tags=["Advanced Fraud Detection"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])


@app.get("/")
async def root():
    return {
        "name": "Monoscope 🔬",
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


@app.get("/api/status")
async def status():
    """Overall system status: indexer range, wallet/tx counts."""
    # Indexer state
    indexer = {"start_block": None, "last_block": None, "start_time": None, "last_time": None}
    try:
        if INDEXER_STATE_FILE.exists():
            state = json.loads(INDEXER_STATE_FILE.read_text())
            indexer["last_block"] = state.get("last_block")
            indexer["start_block"] = state.get("start_block")
    except Exception:
        pass

    # Get block timestamps + counts from Neo4j
    try:
        result = await db.aquery("""
            MATCH (b:Block)
            WITH MIN(b.number) AS min_block, MAX(b.number) AS max_block,
                 MIN(b.timestamp) AS first_time, MAX(b.timestamp) AS last_time
            MATCH (w:Wallet)
            WITH min_block, max_block, first_time, last_time, COUNT(w) AS wallet_count
            MATCH (tx:Transaction)
            RETURN min_block, max_block, first_time, last_time,
                   wallet_count, COUNT(tx) AS tx_count
        """)
        if result:
            row = result[0]
            indexer["start_block"] = indexer.get("start_block") or row.get("min_block")
            indexer["last_block"] = indexer.get("last_block") or row.get("max_block")
            indexer["start_time"] = row.get("first_time")
            indexer["last_time"] = row.get("last_time")
            return {
                "indexer": indexer,
                "wallet_count": row.get("wallet_count", 0),
                "tx_count": row.get("tx_count", 0),
            }
    except Exception:
        pass

    return {"indexer": indexer, "wallet_count": 0, "tx_count": 0}
