# Monad Watchdog 🐕

AI-powered fraud detection and wallet analytics for the Monad blockchain.

## What it does

- **Wallet Lookup** — Paste any Monad address, see transaction history, token flows, and risk score
- **Fraud Detection** — Graph-based analysis to detect wash trading, sybil clusters, rug pulls, and suspicious patterns
- **Natural Language Queries** — Ask questions like "Show me the most suspicious wallets this week"
- **Graph Visualization** — See fund flows and wallet relationships as interactive graphs

## Tech Stack

- **Backend:** Python 3.11 + FastAPI + Uvicorn
- **Graph DB:** Neo4j (fraud pattern analysis, wallet relationships)
- **Indexer:** Monad RPC → Neo4j pipeline
- **AI:** LLM integration for natural language queries
- **Frontend:** React (TBD)

## Architecture

```
Monad RPC (public)
    ↓ (indexer polls blocks)
Neo4j Graph DB
    ↓ (Cypher queries)
FastAPI Backend
    ↓ (REST API + LLM layer)
React Frontend
```

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt

# 2. Make sure Neo4j is running (localhost:7687)

# 3. Start the API server
uvicorn app.main:app --reload --port 8000

# 4. Start the indexer (separate terminal)
python -m indexer.run

# 5. Open http://localhost:8000/docs for API docs
```

## Monad Network Info

- Chain ID: 143
- RPC: https://rpc.monad.xyz (25 rps)
- Explorer: https://monadscan.com
- Currency: MON

## Project Status

🚧 Under development
