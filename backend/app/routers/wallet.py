"""Wallet lookup and analytics endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db

router = APIRouter()


class WalletSummary(BaseModel):
    address: str
    tx_count: int = 0
    total_sent: float = 0.0
    total_received: float = 0.0
    unique_interactions: int = 0
    first_seen: int | None = None
    last_seen: int | None = None
    risk_score: float | None = None
    labels: list[str] = []


class TransactionRecord(BaseModel):
    hash: str
    block_number: int
    timestamp: int
    from_addr: str
    to_addr: str
    value: float
    method: str | None = None


@router.get("/{address}", response_model=WalletSummary)
async def get_wallet(address: str):
    """Look up a wallet by address — returns summary stats and risk score."""
    address = address.lower()

    result = db.query(
        """
        MATCH (w:Wallet {address: $address})
        OPTIONAL MATCH (w)-[:SENT]->(tx_out:Transaction)-[:TO]->(other_out:Wallet)
        OPTIONAL MATCH (other_in:Wallet)-[:SENT]->(tx_in:Transaction)-[:TO]->(w)
        RETURN w.address AS address,
               w.first_seen AS first_seen,
               w.last_seen AS last_seen,
               w.risk_score AS risk_score,
               w.labels AS labels,
               count(DISTINCT tx_out) AS sent_count,
               sum(DISTINCT tx_out.value) AS total_sent,
               count(DISTINCT tx_in) AS recv_count,
               sum(DISTINCT tx_in.value) AS total_received,
               count(DISTINCT other_out) AS unique_interactions
        """,
        {"address": address},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Wallet not found in indexed data")

    r = result[0]
    return WalletSummary(
        address=r["address"],
        tx_count=(r["sent_count"] or 0) + (r["recv_count"] or 0),
        total_sent=r["total_sent"] or 0.0,
        total_received=r["total_received"] or 0.0,
        unique_interactions=r["unique_interactions"] or 0,
        first_seen=r["first_seen"],
        last_seen=r["last_seen"],
        risk_score=r["risk_score"],
        labels=r["labels"] or [],
    )


@router.get("/{address}/transactions", response_model=list[TransactionRecord])
async def get_wallet_transactions(address: str, limit: int = 50):
    """Get recent transactions for a wallet."""
    address = address.lower()

    result = db.query(
        """
        MATCH (from:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(to:Wallet)
        WHERE from.address = $address OR to.address = $address
        RETURN tx.hash AS hash,
               tx.block_number AS block_number,
               tx.timestamp AS timestamp,
               from.address AS from_addr,
               to.address AS to_addr,
               tx.value AS value,
               tx.method AS method
        ORDER BY tx.block_number DESC
        LIMIT $limit
        """,
        {"address": address, "limit": limit},
    )

    return [TransactionRecord(**r) for r in result]


@router.get("/{address}/graph")
async def get_wallet_graph(address: str, depth: int = 2, limit: int = 100):
    """Get the transaction graph around a wallet (for visualization).

    Returns nodes and edges up to `depth` hops from the target wallet.
    Each hop = Wallet -> Transaction -> Wallet (so depth 2 = 4 rels).
    """
    address = address.lower()
    depth = min(depth, 4)  # cap to prevent explosion
    rel_depth = depth * 2  # each logical hop is SENT + TO

    result = db.query(
        """
        MATCH path = (start:Wallet {address: $address})
              -[:SENT|TO*1..%d]-(end:Wallet)
        WHERE start <> end
        WITH path
        LIMIT $limit
        UNWIND relationships(path) AS r
        WITH DISTINCT r
        WHERE type(r) = 'TO'  // only show completed transfers
        WITH startNode(r) AS tx, endNode(r) AS to_wallet
        MATCH (from_wallet:Wallet)-[:SENT]->(tx)
        RETURN DISTINCT
          from_wallet.address AS from_addr,
          to_wallet.address AS to_addr,
          tx.hash AS tx_hash,
          tx.value AS value,
          tx.timestamp AS timestamp
        """
        % rel_depth,
        {"address": address, "limit": limit},
    )

    # Build nodes + edges for frontend
    nodes = {}
    edges = []
    for r in result:
        for addr in [r["from_addr"], r["to_addr"]]:
            if addr not in nodes:
                nodes[addr] = {"address": addr}
        edges.append({
            "from": r["from_addr"],
            "to": r["to_addr"],
            "tx_hash": r["tx_hash"],
            "value": r["value"],
            "timestamp": r["timestamp"],
        })

    return {"nodes": list(nodes.values()), "edges": edges}
