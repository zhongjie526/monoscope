# Monoscope — Monad Foundation Ecosystem Grant Application

## Project Name
**Monoscope** — Graph-Powered Fraud Detection & On-Chain Intelligence for Monad

## One-Liner
The first Monad-native, free, self-serve fraud detection platform — using graph analysis to protect the ecosystem from wash trading, sybil attacks, and suspicious fund flows.

---

## Project Description

Monoscope is a purpose-built on-chain intelligence tool for the Monad blockchain. It uses a Neo4j graph database to model wallet relationships and transaction flows, enabling real-time detection of fraud patterns that traditional block explorers miss.

Unlike enterprise fraud tools (Chainalysis, Elliptic, TRM Labs) that require demos, sales calls, and 5-figure contracts, Monoscope is **free and instantly accessible** — no sign-up, no paywall, no "book a demo" wall. The product IS the landing page.

### What It Does

**8 Fraud Detection Patterns:**
1. **Wash Trading** — Bidirectional fund flows between wallet pairs
2. **Sybil Clusters** — Single funder distributing to many wallets (fan-out)
3. **High Velocity** — Bot-like transaction frequency
4. **Fund Cycling** — Rapid receive→forward relay (money laundering pattern)
5. **Bridge Wallets** — Intermediaries connecting otherwise separate wallet clusters
6. **Rapid Cash-Out** — Large inflows drained quickly
7. **Sybil Expansion** — 2-hop accomplice detection from known sybil clusters
8. **Shared Target Analysis** — Wallets receiving from unusually many unique senders

**AI-Powered Search:**
- Natural language queries about on-chain data ("Who are the most connected wallets?")
- LLM generates Cypher graph queries, executes against Neo4j, summarizes results
- Common queries hit pre-built templates for instant response

**Interactive Graph Explorer:**
- Force-directed visualization of wallet connection graphs
- Click any fraud alert → "Investigate" button → graph view of that fraud pattern
- Node inspection, expansion, right-click actions

**Wallet Intelligence:**
- Per-wallet summary: balance, transaction count, total sent/received
- Staking position detection (Monad staking precompile queries)
- Risk scoring based on multiple behavioral signals

### Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  React/Vite  │────▶│  FastAPI      │────▶│  Neo4j   │
│  Frontend    │     │  Backend      │     │  Graph   │
│  (TypeScript)│     │  (Python)     │     │  Database │
└─────────────┘     └──────┬───────┘     └──────────┘
                           │
                    ┌──────▼───────┐
                    │  Monad RPC   │
                    │  (indexer +  │
                    │   live query)│
                    └──────────────┘
```

- **Frontend:** React 19 + Vite + TypeScript. Light theme (Stripe/Linear aesthetic). Graph viz via react-force-graph-2d.
- **Backend:** FastAPI (Python). Async Neo4j queries. Live Monad RPC fallback for non-indexed wallets.
- **Graph Database:** Neo4j with dual-layer model — Transaction nodes (detail) + TRANSACTED summary edges (fast analytics).
- **Indexer:** Batch indexer tailing the Monad chain (50 blocks/RPC call, UNWIND Cypher for bulk writes).
- **AI:** Claude (Azure) for natural language → Cypher generation.

---

## Why Monad Needs This

### The Problem
Monad's 10,000 TPS throughput creates an **explosion of on-chain activity**. This is great for users — but it also creates more surface area for:
- **Airdrop farming** with sybil accounts
- **Wash trading** to inflate token volumes
- **Flash loan attacks** and fund cycling
- **Scam tokens** distributed via coordinated wallets

Existing tools are either:
- **Too expensive** (Chainalysis, Elliptic — enterprise contracts)
- **Too generic** (Dune, Nansen — multi-chain, not fraud-specialized)
- **Too technical** (raw SQL/Cypher — not accessible to regular users)

### The Gap
Looking at Monad's [Analytics tooling page](https://docs.monad.xyz/tooling-and-infra/analytics), there are 14 analytics providers listed. **None of them are purpose-built fraud detection tools.** Blockaid does real-time detection but isn't a user-facing investigation platform. Bubblemaps visualizes but doesn't detect patterns algorithmically.

Monoscope fills this gap as the **first Monad-native fraud detection + investigation platform**.

---

## Competitive Positioning

| Feature | Monoscope | Chainalysis | Nansen | Dune | Bubblemaps |
|---------|-----------|-------------|--------|------|------------|
| Monad-native | ✅ | ❌ | ❌ | ❌ | ❌ |
| Free access | ✅ | ❌ ($$$) | ❌ ($) | ✅ | ✅ |
| No sign-up needed | ✅ | ❌ | ❌ | ❌ | ✅ |
| Graph-based fraud detection | ✅ | ✅ | ❌ | ❌ | Partial |
| AI-powered search | ✅ | ❌ | ❌ | ❌ | ❌ |
| Interactive investigation | ✅ | ✅ | ❌ | ❌ | ✅ |
| Open source | ✅ (planned) | ❌ | ❌ | ❌ | ❌ |
| 8 detection patterns | ✅ | ✅ | ❌ | ❌ | ❌ |

**Key differentiator:** Monoscope is the only tool that combines **free access + graph-based fraud detection + AI search + interactive investigation** in one platform, purpose-built for Monad.

---

## Team

**Frank Zhang** — Solo builder
- Background: Neo4j & graph database specialist
- Experience: FastAPI, Python, React/TypeScript, blockchain analytics
- Current: Building production graph applications (TPG Network API, DharmaMonk iOS app)
- GitHub: [zhongjie526](https://github.com/zhongjie526)
- Location: Singapore

---

## Current Status

**Monoscope is a working product, not a pitch deck.**

✅ Built & functional:
- Full React frontend (6 pages: Overview, Wallet Lookup, Favourites, Fraud Detection, Graph Explorer, AI Search)
- FastAPI backend with 15+ API endpoints
- Neo4j graph database with indexed Monad chain data
- 8 fraud detection algorithms returning real results
- AI-powered search (Claude / Azure)
- Interactive graph visualization
- Live Monad RPC integration for real-time wallet queries
- Monad staking position detection

🔜 Next steps:
- Deploy to production (Hetzner ARM VPS + Vercel)
- Open-source on GitHub
- Run indexer for deeper chain coverage
- PR to `monad-crypto/protocols` for ecosystem listing
- Community wallet labels & reporting system
- Embeddable risk API for dApps

---

## Grant Request

### Amount
**$10,000 – $15,000 USD** (or equivalent in MON)

### Use of Funds

| Item | Amount | Purpose |
|------|--------|---------|
| Infrastructure (12 months) | $3,000 | Hetzner ARM VPS (Neo4j + API), Vercel frontend |
| LLM API costs (12 months) | $2,000 | Azure Claude for AI Search feature |
| Full-chain indexing | $1,000 | Extended RPC access for historical chain data |
| Development time | $6,000 | Risk API for dApps, community labels, airdrop detection |
| Domain & branding | $500 | monoscope.xyz domain, design assets |
| **Total** | **$12,500** | |

### Milestones

| # | Milestone | Timeline | Deliverable |
|---|-----------|----------|-------------|
| 1 | Public launch | Week 1-2 | Live at monoscope.xyz, open-source repo |
| 2 | Deep indexing | Week 2-4 | Full mainnet history indexed |
| 3 | Risk API | Month 2 | Public API: `GET /api/risk/{address}` for dApps to query wallet risk |
| 4 | Community features | Month 3 | Wallet labels, community reporting, saved investigations |
| 5 | Airdrop farming detection | Month 4 | Sybil scoring for token launch teams |

---

## How Monoscope Benefits the Monad Ecosystem

1. **Trust & Safety** — Helps users avoid scams and identify suspicious wallets before interacting
2. **Ecosystem Credibility** — Having a dedicated fraud detection tool signals Monad takes security seriously
3. **Token Launch Protection** — dApp teams can use the risk API to filter sybil accounts from airdrops
4. **Developer Tooling** — Embeddable risk scores for any Monad dApp (DeFi, NFT, gaming)
5. **Community Intelligence** — Crowdsourced wallet labels create a shared knowledge base
6. **PR & Visibility** — "First blockchain with a free, native fraud detection platform" is a strong narrative

---

## Links

- **GitHub:** https://github.com/zhongjie526/monoscope
- **Live demo:** https://monoscope-seven.vercel.app
- **Tech stack:** FastAPI + Neo4j + React + Vite + TypeScript + Claude AI
- **Chain:** Monad Mainnet (Chain ID 143)

---

## Additional Context

Monoscope was built in <1 week from concept to working product. The fraud detection patterns are inspired by established graph analytics methodologies (Neo4j Graph Summit APAC 2023 fraud workshop, PaySim financial fraud research) adapted for blockchain-specific use cases.

The graph-based approach is fundamentally more powerful than traditional analytics for fraud detection because fraud is inherently a **relationship problem** — it's not about individual transactions but about **patterns of connections** between wallets. Neo4j's native graph storage makes these pattern queries orders of magnitude faster than relational databases.

We believe the best way to protect an ecosystem is to make the tools **free and accessible** to everyone — not locked behind enterprise contracts. Monoscope embodies this philosophy.

---

*Submitted by Frank Zhang — April 2026*
