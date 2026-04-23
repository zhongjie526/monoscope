"""Natural language search endpoint — ask questions about Monad data."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.database import db

router = APIRouter()


class SearchQuery(BaseModel):
    question: str


class SearchResult(BaseModel):
    answer: str
    data: list[dict] | None = None
    query_used: str | None = None  # show the Cypher for transparency


# Pre-built query templates for common questions
QUERY_TEMPLATES = {
    "top_wallets": {
        "pattern": ["top wallets", "biggest wallets", "most active", "whale"],
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
        "pattern": ["large transfer", "big transaction", "whale movement"],
        "cypher": """
            MATCH (from:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(to:Wallet)
            WHERE tx.value > 10000
            RETURN from.address AS from_addr, to.address AS to_addr,
                   tx.value AS value, tx.hash AS hash, tx.timestamp AS timestamp
            ORDER BY tx.value DESC
            LIMIT 20
        """,
        "description": "Recent large transfers (>10,000 MON)",
    },
    "suspicious": {
        "pattern": ["suspicious", "fraud", "scam", "risky", "danger"],
        "cypher": """
            MATCH (w:Wallet)
            WHERE w.risk_score > 0.5
            RETURN w.address AS address, w.risk_score AS risk_score,
                   w.labels AS labels
            ORDER BY w.risk_score DESC
            LIMIT 20
        """,
        "description": "Wallets with highest risk scores",
    },
    "new_wallets": {
        "pattern": ["new wallet", "new address", "recently created"],
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
        "pattern": ["stats", "statistics", "overview", "how many", "total"],
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

    Currently uses keyword matching against pre-built queries.
    Will be upgraded to LLM-powered Cypher generation in a future version.
    """
    template = match_template(query.question)

    if not template:
        return SearchResult(
            answer="I don't understand that question yet. Try asking about: "
            "top wallets, large transfers, suspicious activity, new wallets, or stats.",
            data=None,
        )

    result = await db.aquery(template["cypher"])

    return SearchResult(
        answer=template["description"],
        data=result,
        query_used=template["cypher"].strip(),
    )
