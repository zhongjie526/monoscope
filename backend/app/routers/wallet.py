"""Wallet lookup and analytics endpoints.

Falls back to live Monad RPC when wallet is not in our indexed data.
"""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.database import db

router = APIRouter()


class StakingInfo(BaseModel):
    validator_id: int
    staked: float  # MON staked
    rewards: float  # unclaimed rewards in MON


class WalletSummary(BaseModel):
    address: str
    balance: float | None = None  # MON balance
    tx_count: int = 0
    total_sent: float = 0.0
    total_received: float = 0.0
    unique_interactions: int = 0
    first_seen: int | None = None
    last_seen: int | None = None
    risk_score: float | None = None
    labels: list[str] = []
    source: str = "indexed"  # "indexed" or "rpc" — tells frontend where data came from
    staking: list[StakingInfo] = []  # staking positions on Monad


class TransactionRecord(BaseModel):
    hash: str
    block_number: int
    timestamp: int
    from_addr: str
    to_addr: str
    value: float
    method: str | None = None


# ── RPC helpers ─────────────────────────────────────────────────────────

def _rpc_call(method: str, params: list) -> dict | None:
    """Quick JSON-RPC call to Monad."""
    try:
        resp = httpx.post(
            settings.monad_rpc_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            timeout=10,
        )
        data = resp.json()
        return data.get("result")
    except Exception:
        return None


def _get_balance(address: str) -> float | None:
    result = _rpc_call("eth_getBalance", [address, "latest"])
    if result:
        return int(result, 16) / 1e18
    return None


def _get_tx_count(address: str) -> int:
    result = _rpc_call("eth_getTransactionCount", [address, "latest"])
    if result:
        return int(result, 16)
    return 0


STAKING_CONTRACT = "0x0000000000000000000000000000000000001000"
GET_DELEGATOR_SELECTOR = "0x573c1ce0"
# getDelegations(address, uint64 startValidatorId) → returns up to 100 delegations
GET_DELEGATIONS_SELECTOR = "0x4fd66050"


def _get_staking_info(address: str) -> list[dict]:
    """Query Monad staking precompile for delegation info.

    Tries validators 1-20 (covers most cases). Returns list of active stakes.
    """
    stakes = []
    addr_padded = address.lower().replace("0x", "").zfill(40)

    # Try getDelegations first (returns paginated list)
    data = GET_DELEGATIONS_SELECTOR + "000000000000000000000000" + addr_padded + "0" * 64
    result = _rpc_call("eth_call", [{"to": STAKING_CONTRACT, "data": data}, "latest"])

    if result and result != "0x" and len(result) > 66:
        # Parse the response — it returns an array of (validatorId, stake) tuples
        # For now, fall back to individual validator queries
        pass

    # Fallback: check validators 1-20 individually
    for val_id in range(1, 21):
        val_hex = hex(val_id)[2:].zfill(64)
        addr_hex = "000000000000000000000000" + addr_padded
        data = GET_DELEGATOR_SELECTOR + val_hex + addr_hex

        result = _rpc_call("eth_call", [{"to": STAKING_CONTRACT, "data": data}, "latest"])
        if not result or result == "0x" or len(result) < 130:
            continue

        # Decode: chunk0 = staked amount, chunk2 = unclaimed rewards
        hex_data = result[2:]
        chunks = [hex_data[i:i+64] for i in range(0, len(hex_data), 64)]
        if len(chunks) < 3:
            continue

        staked_wei = int(chunks[0], 16)
        rewards_wei = int(chunks[2], 16)

        if staked_wei > 0:
            stakes.append({
                "validator_id": val_id,
                "staked": staked_wei / 1e18,
                "rewards": rewards_wei / 1e18,
            })

    return stakes


def _get_recent_txs(address: str, limit: int = 20) -> list[dict]:
    """Get recent transactions via block scanning (limited — best effort)."""
    # For MVP, we scan the last ~50 blocks for this address
    latest_hex = _rpc_call("eth_blockNumber", [])
    if not latest_hex:
        return []

    latest = int(latest_hex, 16)
    txs = []

    for block_num in range(latest, max(latest - 50, 0), -1):
        block = _rpc_call("eth_getBlockByNumber", [hex(block_num), True])
        if not block:
            continue
        timestamp = int(block["timestamp"], 16)
        for tx in block.get("transactions", []):
            if isinstance(tx, str):
                continue
            from_addr = (tx.get("from") or "").lower()
            to_addr = (tx.get("to") or "").lower()
            if from_addr == address or to_addr == address:
                value_wei = int(tx.get("value", "0x0"), 16)
                input_data = tx.get("input", "0x")
                txs.append({
                    "hash": tx["hash"],
                    "block_number": block_num,
                    "timestamp": timestamp,
                    "from_addr": from_addr,
                    "to_addr": to_addr,
                    "value": value_wei / 1e18,
                    "method": input_data[:10] if len(input_data) >= 10 else None,
                })
                if len(txs) >= limit:
                    return txs
    return txs


# ── Endpoints ───────────────────────────────────────────────────────────

@router.get("/{address}", response_model=WalletSummary)
async def get_wallet(address: str):
    """Look up a wallet — checks indexed data first, falls back to live RPC."""
    address = address.lower()

    # Try indexed data first
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

    if result and result[0].get("address"):
        r = result[0]
        balance = _get_balance(address)  # always fetch live balance
        staking = _get_staking_info(address)
        return WalletSummary(
            address=r["address"],
            balance=balance,
            tx_count=(r["sent_count"] or 0) + (r["recv_count"] or 0),
            total_sent=r["total_sent"] or 0.0,
            total_received=r["total_received"] or 0.0,
            unique_interactions=r["unique_interactions"] or 0,
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            risk_score=r["risk_score"],
            labels=r["labels"] or [],
            source="indexed",
            staking=[StakingInfo(**s) for s in staking],
        )

    # Fallback: live RPC lookup
    balance = _get_balance(address)
    if balance is None:
        # Address doesn't exist on chain at all
        return WalletSummary(
            address=address,
            balance=0.0,
            tx_count=0,
            source="rpc",
            labels=["unknown"],
        )

    nonce = _get_tx_count(address)
    staking = _get_staking_info(address)

    labels = ["not yet indexed"] if nonce > 0 else ["new wallet"]
    if staking:
        labels.append("staker")

    return WalletSummary(
        address=address,
        balance=balance,
        tx_count=nonce,
        source="rpc",
        labels=labels,
        staking=[StakingInfo(**s) for s in staking],
    )


@router.get("/{address}/transactions", response_model=list[TransactionRecord])
async def get_wallet_transactions(address: str, limit: int = 50):
    """Get recent transactions — indexed data first, RPC fallback."""
    address = address.lower()

    # Try indexed data
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

    if result:
        return [TransactionRecord(**r) for r in result]

    # Fallback: scan recent blocks via RPC
    rpc_txs = _get_recent_txs(address, limit=min(limit, 20))
    return [TransactionRecord(**tx) for tx in rpc_txs]


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

    # If no graph data indexed, return just the target node
    if not nodes:
        nodes[address] = {"address": address}

    return {"nodes": list(nodes.values()), "edges": edges}
