"""Natural language search endpoint — ask questions about Monad data.

Uses Claude (Azure) to generate Cypher queries from natural language.
Falls back to pre-built templates for common questions.
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from app.database import db
from app.llm import generate_cypher, summarize_results, get_client

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchQuery(BaseModel):
    question: str


class SearchResult(BaseModel):
    answer: str
    data: list[dict] | None = None
    query_used: str | None = None  # show the Cypher for transparency
    source: str = "template"  # "template" | "ai"


# Pre-built query templates for common questions (fast path, no LLM cost)
# IMPORTANT: only use properties that actually exist in the DB:
#   Wallet: address, first_seen, last_seen
#   Transaction: hash, block_number, timestamp, method, value
#   Relationships: SENT (Wallet→Transaction), TO (Transaction→Wallet)
QUERY_TEMPLATES = {
    "top_wallets": {
        "pattern": ["top wallets", "biggest wallets", "most active", "whale",
                     "largest wallets", "most sent", "sent the most",
                     "most transactions"],
        "cypher": """
            MATCH (w:Wallet)-[:SENT]->(tx:Transaction)
            WITH w, COUNT(tx) AS tx_count, SUM(tx.value) AS total_value
            ORDER BY total_value DESC
            LIMIT 20
            RETURN w.address AS address, tx_count, total_value
        """,
        "description": "Top wallets by total value sent",
    },
    "recent_large": {
        "pattern": ["large transfer", "big transaction", "whale movement",
                     "large transaction", "big transfer"],
        "cypher": """
            MATCH (from_w:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(to_w:Wallet)
            WHERE tx.value > 10000
            RETURN from_w.address AS from_addr, to_w.address AS to_addr,
                   tx.value AS value, tx.hash AS hash, tx.timestamp AS timestamp
            ORDER BY tx.value DESC
            LIMIT 20
        """,
        "description": "Recent large transfers (>10,000 MON)",
    },
    "suspicious": {
        "pattern": ["suspicious", "fraud", "scam", "risky", "danger",
                     "risk score", "risk_score", "highest risk",
                     "suspicious activity"],
        "cypher": """
            MATCH (w:Wallet)-[:SENT]->(tx:Transaction)
            WITH w, COUNT(tx) AS tx_count, SUM(tx.value) AS total_value
            WHERE tx_count > 50
            ORDER BY tx_count DESC
            LIMIT 20
            RETURN w.address AS address, tx_count, total_value
        """,
        "description": "Most suspicious wallets — unusually high transaction counts",
    },
    "new_wallets": {
        "pattern": ["new wallet", "new wallets", "new address", "recently created",
                     "newest", "latest wallet"],
        "cypher": """
            MATCH (w:Wallet)
            WHERE w.first_seen IS NOT NULL
            RETURN w.address AS address, w.first_seen AS first_seen
            ORDER BY w.first_seen DESC
            LIMIT 20
        """,
        "description": "Most recently seen wallets",
    },
    "stats": {
        "pattern": ["stats", "statistics", "overview", "how many", "total",
                     "give me the stats", "count"],
        "cypher": """
            MATCH (w:Wallet)
            WITH COUNT(w) AS wallet_count
            MATCH (tx:Transaction)
            WITH wallet_count, COUNT(tx) AS tx_count,
                 MIN(tx.timestamp) AS first_tx, MAX(tx.timestamp) AS last_tx
            RETURN wallet_count, tx_count, first_tx, last_tx
        """,
        "description": "Overall Monoscope statistics",
    },
    "connected": {
        "pattern": ["connected", "transacted with each other", "bidirectional",
                     "mutual", "both sent"],
        "cypher": """
            MATCH (a:Wallet)-[:SENT]->(tx1:Transaction)-[:TO]->(b:Wallet),
                  (b)-[:SENT]->(tx2:Transaction)-[:TO]->(a)
            WITH a, b, COUNT(DISTINCT tx1) AS a_to_b, COUNT(DISTINCT tx2) AS b_to_a
            WHERE a.address < b.address
            RETURN a.address AS wallet_a, b.address AS wallet_b,
                   a_to_b, b_to_a, a_to_b + b_to_a AS total_txs
            ORDER BY total_txs DESC
            LIMIT 20
        """,
        "description": "Wallets with bidirectional transactions (sent to each other)",
    },
    "most_connected": {
        "pattern": ["most connected", "most interactions", "hub"],
        "cypher": """
            MATCH (w:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(other:Wallet)
            WITH w, COUNT(DISTINCT other) AS unique_recipients
            ORDER BY unique_recipients DESC
            LIMIT 20
            RETURN w.address AS address, unique_recipients
        """,
        "description": "Most connected wallets by unique recipients",
    },
}


def match_template(question: str) -> dict | None:
    """Simple keyword matching to find the right query template."""
    question_lower = question.lower()
    for key, template in QUERY_TEMPLATES.items():
        for pattern in template["pattern"]:
            if pattern in question_lower:
                return template
    return None


@router.post("/", response_model=SearchResult)
async def search(query: SearchQuery):
    """Ask a natural language question about Monad blockchain data.

    1. Try keyword match against pre-built templates (fast, free).
    2. If no match, use Claude to generate Cypher from the question.
    3. Execute the Cypher and summarize results with Claude.
    """
    # Fast path: template match
    template = match_template(query.question)
    if template:
        result = await db.aquery(template["cypher"])
        return SearchResult(
            answer=template["description"],
            data=result,
            query_used=template["cypher"].strip(),
            source="template",
        )

    # AI path: generate Cypher with Claude
    if get_client() is None:
        return SearchResult(
            answer="AI search is not configured. Try asking about: "
            "top wallets, large transfers, suspicious activity, new wallets, or stats.",
            data=None,
            source="template",
        )

    try:
        cypher = await generate_cypher(query.question)

        if cypher is None or cypher == "UNSUPPORTED":
            return SearchResult(
                answer="I can't answer that question from the blockchain data. "
                "Try asking about wallets, transactions, transfers, or on-chain activity.",
                data=None,
                source="ai",
            )

        # Safety: reject any write queries
        cypher_upper = cypher.upper()
        if any(kw in cypher_upper for kw in ["CREATE", "MERGE", "DELETE", "SET ", "REMOVE", "DROP"]):
            logger.warning(f"LLM generated write query, rejecting: {cypher}")
            return SearchResult(
                answer="I generated a query that would modify data, which isn't allowed. "
                "Please rephrase as a read-only question.",
                data=None,
                source="ai",
            )

        # Execute the generated Cypher
        try:
            result = await db.aquery(cypher)
        except Exception as e:
            logger.error(f"Generated Cypher failed: {cypher} — {e}")
            return SearchResult(
                answer="My query had a syntax error. Let me know what you're looking for "
                "and I'll try differently.",
                data=None,
                query_used=cypher,
                source="ai",
            )

        # Summarize results with Claude
        answer = await summarize_results(query.question, cypher, result)

        return SearchResult(
            answer=answer,
            data=result,
            query_used=cypher,
            source="ai",
        )

    except Exception as e:
        logger.error(f"AI search error: {e}")
        return SearchResult(
            answer="AI search encountered an error. Try a simpler question or ask about: "
            "top wallets, large transfers, suspicious activity, new wallets, or stats.",
            data=None,
            source="ai",
        )
