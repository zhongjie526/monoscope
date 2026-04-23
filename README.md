# 🔬 Monoscope

**On-chain intelligence for Monad.**

Paste any wallet address. Get instant fraud analysis, transaction history, risk scoring, and interactive graph visualization. No sign-up. No demo call. No paywall.

> Other platforms make you talk to sales. Monoscope lets you investigate.

## What it does

- **Wallet Intelligence** — Transaction history, balance, staking positions, activity summary, and risk scoring for any Monad address
- **Fraud Detection** — Graph-based analysis detects wash trading rings, sybil clusters, and high-velocity bot activity
- **Graph Explorer** — Interactive force-directed graph visualization of wallet relationships and fund flows (Neo4j Bloom-inspired)
- **AI Search** — Ask questions about the blockchain in plain English *(coming soon)*
- **Embeddable API** — Add fraud screening to your Monad dApp with a single API call

## Why Monoscope?

| | Enterprise platforms (Chainalysis, Elliptic) | Monoscope |
|---|---|---|
| **Access** | "Book a demo" → sales call → NDA → POC → contract | Paste an address, get results |
| **Pricing** | $50K–500K+/yr | Free |
| **Monad support** | Generic multi-chain | Purpose-built |
| **Graph exploration** | Internal only | Public, interactive |
| **Target** | Banks, exchanges, law enforcement | Everyone |

## Tech Stack

- **Frontend:** React 19 + TypeScript + Vite (dark theme)
- **Backend:** Python 3.11 + FastAPI + Uvicorn
- **Graph DB:** Neo4j (fraud patterns, wallet relationships, Cypher queries)
- **Indexer:** Monad RPC → Neo4j block-by-block pipeline
- **Data enrichment:** Monadscan (Etherscan V2) API for full transaction histories

## Architecture

```
Monad RPC (Chain ID 143)
    ↓ blocks + transactions
Neo4j Graph DB
    ↓ Cypher queries
FastAPI Backend ← Monadscan API (tx enrichment)
    ↓ REST API
React Frontend (localhost:5173)
```

## Quick Start

```bash
# Prerequisites: Python 3.11+, Node.js 18+, Neo4j running on localhost:7687

# Clone and start
git clone https://github.com/zhongjie526/monoscope.git
cd monoscope

# Start everything
./start.sh

# Or manually:
# Backend:  cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
# Frontend: cd frontend && npm install && npm run dev
# Indexer:  cd backend && python -m indexer.run
```

Open [http://localhost:5173](http://localhost:5173) — paste an address and go.

## API

API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

Key endpoints:
- `GET /api/wallet/{address}` — Wallet summary + risk score
- `GET /api/wallet/{address}/transactions` — Transaction list
- `GET /api/wallet/{address}/graph` — Graph data (nodes + edges)
- `POST /api/wallet/{address}/scan` — Index a wallet's full history
- `GET /api/fraud/wash-trading` — Wash trading detection
- `GET /api/fraud/sybil-clusters` — Sybil cluster detection
- `GET /api/fraud/risk/{address}` — Per-wallet risk score
- `GET /api/status` — System stats + indexer status

## Monad Network

- **Chain ID:** 143
- **RPC:** https://rpc.monad.xyz
- **Explorer:** https://monadscan.com
- **Currency:** MON

## Roadmap

- [x] Wallet lookup + transaction history
- [x] Neo4j graph-powered fraud detection (wash trading, sybil, velocity)
- [x] Interactive graph explorer
- [x] Wallet risk scoring
- [x] Staking data (validator positions + rewards)
- [x] Monadscan API integration + auto-indexing
- [x] Favourites + wallet cache
- [ ] LLM-powered natural language queries (AI Search)
- [ ] Community wallet labels + reporting
- [ ] Embeddable risk API for dApps
- [ ] Airdrop farming / sybil detection for token launches
- [ ] Deploy to production (Hetzner + Vercel)

## License

MIT
