"""Background indexing of transactions fetched from Monadscan.

When a wallet is looked up via RPC fallback, we get its tx history from
Monadscan. This module ingests those transactions into Neo4j in the
background so subsequent graph queries work without the API.
"""

import logging
import threading

from app.database import db

logger = logging.getLogger(__name__)


def index_transactions_background(txs: list[dict]):
    """Fire-and-forget: index a list of Monadscan transactions into Neo4j.

    Each tx dict has: hash, block_number, timestamp, from_addr, to_addr, value, method.
    Uses MERGE to avoid duplicates — safe to call repeatedly.
    """
    if not txs:
        return
    thread = threading.Thread(target=_index_transactions, args=(txs,), daemon=True)
    thread.start()


def _index_transactions(txs: list[dict]):
    """Actual indexing logic — runs in background thread."""
    try:
        # Batch all txs in one Cypher call using UNWIND
        db.write(
            """
            UNWIND $transfers AS t

            MERGE (from:Wallet {address: t.from_addr})
            ON CREATE SET from.first_seen = t.timestamp
            SET from.last_seen = CASE
                WHEN from.last_seen IS NULL OR from.last_seen < t.timestamp
                THEN t.timestamp ELSE from.last_seen END

            MERGE (to:Wallet {address: t.to_addr})
            ON CREATE SET to.first_seen = t.timestamp
            SET to.last_seen = CASE
                WHEN to.last_seen IS NULL OR to.last_seen < t.timestamp
                THEN t.timestamp ELSE to.last_seen END

            MERGE (tx:Transaction {hash: t.tx_hash})
            ON CREATE SET tx.value = t.value,
                          tx.block_number = t.block_number,
                          tx.timestamp = t.timestamp,
                          tx.method = t.method,
                          tx.source = 'monadscan',
                          tx._new = true
            ON MATCH SET tx._new = false

            MERGE (from)-[:SENT]->(tx)
            MERGE (tx)-[:TO]->(to)

            // Only update TRANSACTED summary for genuinely new transactions
            WITH from, to, tx, t
            WHERE tx._new = true
            MERGE (from)-[agg:TRANSACTED]->(to)
            ON CREATE SET agg.tx_count = 1,
                          agg.total_value = t.value,
                          agg.first_seen = t.timestamp,
                          agg.last_seen = t.timestamp
            ON MATCH SET agg.tx_count = agg.tx_count + 1,
                         agg.total_value = agg.total_value + t.value,
                         agg.last_seen = CASE
                             WHEN agg.last_seen < t.timestamp
                             THEN t.timestamp ELSE agg.last_seen END
            """,
            {
                "transfers": [
                    {
                        "from_addr": tx["from_addr"],
                        "to_addr": tx["to_addr"] or tx["from_addr"],
                        "tx_hash": tx["hash"],
                        "value": tx["value"],
                        "block_number": tx["block_number"],
                        "timestamp": tx["timestamp"],
                        "method": tx.get("method"),
                    }
                    for tx in txs
                ],
            },
        )
        logger.info(f"Background indexed {len(txs)} transactions into Neo4j")
    except Exception as e:
        logger.warning(f"Background indexing failed: {e}")
