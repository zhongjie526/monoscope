"""LLM client for natural language → Cypher generation."""

import asyncio
import anthropic
from app.config import settings

# Neo4j graph schema for prompt context
GRAPH_SCHEMA = """
Node Labels & Properties:
- (:Wallet {address, first_seen, last_seen, risk_score, labels, tx_count, total_sent, total_received, balance, nonce})
- (:Transaction {hash, block_number, timestamp, value, gas_price, gas_used, method_id, status})
- (:Block {number, timestamp, tx_count})
- (:Contract {address})
- (:Token {address})

Relationships:
- (Wallet)-[:SENT]->(Transaction)       — wallet sent this tx
- (Transaction)-[:TO]->(Wallet)         — tx recipient
- (Wallet)-[r:TRANSACTED]->(Wallet)     — summary edge: {tx_count, total_value, first_tx, last_tx}
- (Transaction)-[:IN_BLOCK]->(Block)    — tx belongs to block

Notes:
- All values are in MON (native token, 18 decimals stored as float).
- Timestamps are Unix epoch seconds.
- TRANSACTED is a pre-aggregated summary edge for fast analytics.
- risk_score is 0.0–1.0 (0 = clean, 1 = very suspicious).
- The database name is 'monad' (already set in session).
"""

SYSTEM_PROMPT = f"""You are a Cypher query expert for a Monad blockchain graph database (Neo4j).

Given a natural language question about blockchain data, generate a single valid Cypher READ query.

{GRAPH_SCHEMA}

Rules:
1. Output ONLY the Cypher query — no explanation, no markdown, no backticks.
2. Always use LIMIT (max 50) to avoid huge result sets.
3. Use RETURN with descriptive aliases.
4. For wallet lookups, match case-insensitively: toLower(w.address) = toLower($addr)
5. Use the TRANSACTED summary edge for questions about wallet relationships and flows.
6. Use Transaction nodes for detailed tx-level queries.
7. If the question cannot be answered from the schema, output exactly: UNSUPPORTED
8. Never generate write queries (CREATE, MERGE, DELETE, SET, REMOVE).
"""


def _get_client() -> anthropic.Anthropic | None:
    """Create Anthropic client if Azure credentials are configured."""
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        return None
    # The endpoint ends with /openai/v1 but we need /anthropic/
    base_url = settings.azure_openai_endpoint.rstrip("/")
    if base_url.endswith("/openai/v1"):
        base_url = base_url.rsplit("/openai/v1", 1)[0] + "/anthropic/"
    elif not base_url.endswith("/anthropic/"):
        base_url += "/anthropic/"
    return anthropic.Anthropic(
        base_url=base_url,
        api_key=settings.azure_openai_api_key,
    )


_client = None


def get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is None:
        _client = _get_client()
    return _client


async def generate_cypher(question: str) -> str | None:
    """Use Claude to generate a Cypher query from a natural language question.

    Returns the Cypher string, 'UNSUPPORTED' if the question can't be answered,
    or None if LLM is not configured.
    """
    client = get_client()
    if client is None:
        return None

    def _call():
        msg = client.messages.create(
            model=settings.azure_openai_model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        return msg.content[0].text.strip()

    return await asyncio.to_thread(_call)


async def summarize_results(question: str, cypher: str, data: list[dict]) -> str:
    """Use Claude to summarize query results in natural language."""
    client = get_client()
    if client is None:
        return f"Found {len(data)} results."

    # Truncate data for prompt
    sample = data[:20]
    data_str = str(sample)
    if len(data_str) > 3000:
        data_str = data_str[:3000] + "... (truncated)"

    def _call():
        msg = client.messages.create(
            model=settings.azure_openai_model,
            max_tokens=300,
            system="You are a blockchain analyst. Summarize the query results concisely in 1-3 sentences. Be specific with numbers and addresses (show full addresses). If the data is empty, say so clearly.",
            messages=[
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nCypher query used:\n{cypher}\n\nResults:\n{data_str}",
                }
            ],
        )
        return msg.content[0].text.strip()

    return await asyncio.to_thread(_call)
