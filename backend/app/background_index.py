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
            ON CREATE SET from.first_seen = t.timestamp, from.last_seen = t.timestamp
            SET from.first_seen = CASE
                WHEN from.first_seen IS NULL OR from.first_seen > t.timestamp
                THEN t.timestamp ELSE from.first_seen END,
                from.last_seen = CASE
                WHEN from.last_seen IS NULL OR from.last_seen < t.timestamp
                THEN t.timestamp ELSE from.last_seen END

            MERGE (to:Wallet {address: t.to_addr})
            ON CREATE SET to.first_seen = t.timestamp, to.last_seen = t.timestamp
            SET to.first_seen = CASE
                WHEN to.first_seen IS NULL OR to.first_seen > t.timestamp
                THEN t.timestamp ELSE to.first_seen END,
                to.last_seen = CASE
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


def enrich_wallet_background(address: str, stats: dict):
    """Fire-and-forget: write wallet stats onto its Neo4j node.

    stats dict should have: balance, tx_count, total_sent, total_received,
    unique_interactions, first_seen, last_seen, staking (list).
    """
    thread = threading.Thread(
        target=_enrich_wallet, args=(address, stats), daemon=True
    )
    thread.start()


def _enrich_wallet(address: str, stats: dict):
    try:
        staked_total = sum(s.get("staked", 0) for s in stats.get("staking", []))
        rewards_total = sum(s.get("rewards", 0) for s in stats.get("staking", []))

        db.write(
            """
            MERGE (w:Wallet {address: $address})
            SET w.balance = $balance,
                w.tx_count = $tx_count,
                w.total_sent = $total_sent,
                w.total_received = $total_received,
                w.unique_interactions = $unique_interactions,
                w.staked = $staked,
                w.staking_rewards = $rewards,
                w.stats_updated = timestamp()
            """,
            {
                "address": address.lower(),
                "balance": stats.get("balance", 0),
                "tx_count": stats.get("tx_count", 0),
                "total_sent": stats.get("total_sent", 0),
                "total_received": stats.get("total_received", 0),
                "unique_interactions": stats.get("unique_interactions", 0),
                "staked": staked_total,
                "rewards": rewards_total,
            },
        )
        logger.info(f"Enriched wallet node {address[:10]}... with stats")
    except Exception as e:
        logger.warning(f"Wallet enrichment failed: {e}")
