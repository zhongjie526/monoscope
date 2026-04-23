# Monoscope (formerly Monad Watchdog) — Progress Report

## Date: 2026-04-20

---

## ✅ What Was Built

### 1. React Frontend (`frontend/`)

**Tech stack:** Vite + React 19 + TypeScript + react-force-graph-2d + lucide-react

**Pages built:**

| Page | Route | Description |
|------|-------|-------------|
| **Overview** | `/` | Dashboard with stats (244 wallets, 651 txs), quick search bar, and top 10 fraud alerts sorted by severity |
| **Wallet Lookup** | `/wallet/:address` | Full wallet dashboard — summary stats, risk score with color-coded badge, transaction history table, labels, first/last seen timestamps |
| **Fraud Alerts** | `/fraud` | All three detection patterns with filter tabs, severity badges, expandable evidence details |
| **Graph Explorer** | `/graph` | Interactive force-directed graph visualization. Click nodes to explore. Auto-resizing container. |
| **AI Search** | `/search` | Natural language search with example query buttons, Cypher query transparency, tabular results |

**UI features:**
- Dark theme (crypto/security aesthetic)
- Sidebar navigation with Neo4j connection status indicator
- Responsive design (sidebar collapses on mobile)
- Monospace font for addresses, click-to-navigate on any address
- Risk score badges: color-coded (green/yellow/orange/red) with percentage bar
- Google Fonts: Inter + JetBrains Mono

**Architecture:**
- `src/services/api.ts` — typed API client for all backend endpoints
- `src/hooks/useApi.ts` — generic data-fetching hook with loading/error states
- `src/types/index.ts` — TypeScript interfaces matching FastAPI response models
- `src/components/` — reusable: Layout, AddressLink, RiskBadge, SeverityBadge, Loading, ErrorBox
- Vite proxy configured to forward `/api/*` and `/health` to `localhost:8000`

### 2. Backend Fixes

**Issue found:** The 651 existing transactions had no `TRANSACTED` summary edges, even though the indexer code creates them. This meant all three fraud detection endpoints returned empty arrays.

**Fix:** Ran a backfill query to create 192 TRANSACTED summary edges from existing SENT→Transaction→TO paths:

```cypher
MATCH (from:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(to:Wallet)
WITH from, to, count(tx) AS tx_count, sum(tx.value) AS total_value,
     min(tx.timestamp) AS first_seen, max(tx.timestamp) AS last_seen
MERGE (from)-[agg:TRANSACTED]->(to)
SET agg.tx_count = tx_count, agg.total_value = total_value,
    agg.first_seen = first_seen, agg.last_seen = last_seen
```

**Result:** All fraud endpoints now return real detections:
- **Wash trading:** Multiple bidirectional flow pairs detected (0xa697... ⇄ several wallets)
- **Sybil clusters:** 1 cluster — 0xa697... fanning out to 8 wallets
- **High velocity:** 4+ bot-like wallets (up to 13,000 txs/hr)

### 3. Git Repository

Initialized at `~/dev/monad-watchdog/` with initial commit containing all backend + frontend code.

---

## 📊 Current Data State

| Metric | Value |
|--------|-------|
| Wallets indexed | 244 |
| Transactions indexed | 651 |
| TRANSACTED edges | 192 |
| Fraud alerts (wash) | 4+ |
| Fraud alerts (sybil) | 1 |
| Fraud alerts (velocity) | 4+ |

---

## 🚀 How to Run

```bash
# Backend (already running)
cd backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev
# → http://localhost:5173

# Indexer (already running)
cd backend && python -m indexer.run --batch 50
```

---

## 🔮 Next Steps

- [ ] Push to GitHub remote
- [ ] Add LLM-powered Cypher generation (replace keyword matching in search)
- [ ] Add time-based charts (tx volume over time)
- [ ] Token transfer tracking (ERC-20 events)
- [ ] Wallet labeling/tagging UI
- [ ] Export fraud reports as PDF
- [ ] Real-time WebSocket updates from indexer
- [ ] Production deployment (Docker compose)
