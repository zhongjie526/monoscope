"""Wallet lookup and analytics endpoints.

Falls back to live Monad RPC when wallet is not in our indexed data.
"""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.database import db
from app.background_index import index_transactions_background

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


def _get_txs_from_monadscan(address: str, limit: int = 50) -> list[dict] | None:
    """Fetch transaction history from Monadscan (Etherscan V2 API).

    Returns list of tx dicts, or None if API is unavailable.
    """
    if not settings.monadscan_api_key:
        return None

    try:
        resp = httpx.get(
            settings.monadscan_api_url,
            params={
                "chainid": settings.monadscan_chain_id,
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": limit,
                "sort": "desc",
                "apikey": settings.monadscan_api_key,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("result"):
            return None

        txs = []
        for r in data["result"]:
            value_wei = int(r.get("value", "0"))
            input_data = r.get("input", "0x")
            txs.append({
                "hash": r["hash"],
                "block_number": int(r["blockNumber"]),
                "timestamp": int(r["timeStamp"]),
                "from_addr": r["from"].lower(),
                "to_addr": (r.get("to") or "").lower(),
                "value": value_wei / 1e18,
                "method": input_data[:10] if len(input_data) >= 10 else None,
            })
        return txs
    except Exception:
        return None


def _get_recent_txs(address: str, limit: int = 50) -> list[dict]:
    """Get transactions for an address.

    Priority:
    1. Monadscan API (full history, fast)
    2. RPC binary search fallback (outbound only, slower)
    """
    address = address.lower()

    # Try Monadscan first
    monadscan_txs = _get_txs_from_monadscan(address, limit)
    if monadscan_txs is not None:
        return monadscan_txs

    # Fallback: binary search for outbound txs via nonce
    txs: list[dict] = []
    seen_hashes: set[str] = set()

    latest_hex = _rpc_call("eth_blockNumber", [])
    nonce_count = _get_tx_count(address)
    if nonce_count > 0 and nonce_count <= 20:
        latest_block = int(latest_hex, 16) if latest_hex else 0
        for target_n in range(1, nonce_count + 1):
            block_num = _binary_search_nonce_block(address, 0, latest_block, target_nonce=target_n)
            if block_num is None:
                continue
            block = _rpc_call("eth_getBlockByNumber", [hex(block_num), True])
            if not block:
                continue
            timestamp = int(block["timestamp"], 16)
            for tx_data in block.get("transactions", []):
                if isinstance(tx_data, str):
                    continue
                if (tx_data.get("from") or "").lower() == address:
                    tx_nonce = int(tx_data.get("nonce", "0x0"), 16)
                    if tx_nonce == target_n - 1:
                        tx_hash = tx_data["hash"]
                        if tx_hash not in seen_hashes:
                            seen_hashes.add(tx_hash)
                            value_wei = int(tx_data.get("value", "0x0"), 16)
                            input_data = tx_data.get("input", "0x")
                            txs.append({
                                "hash": tx_hash,
                                "block_number": block_num,
                                "timestamp": timestamp,
                                "from_addr": address,
                                "to_addr": (tx_data.get("to") or "").lower(),
                                "value": value_wei / 1e18,
                                "method": input_data[:10] if len(input_data) >= 10 else None,
                            })
                        break

    txs.sort(key=lambda t: t["block_number"], reverse=True)
    return txs[:limit]


def _find_staking_txs(address: str) -> list[dict]:
    """Find staking delegation transactions for a wallet.

    Approach: if the wallet has staking positions, we know they interacted
    with the staking contract. Use eth_getLogs with narrow binary-search
    to find the delegation events without scanning millions of blocks.
    """
    address = address.lower()
    addr_padded = "0x000000000000000000000000" + address.replace("0x", "")
    delegation_topic = "0xe4d4df1e1827dd28252fd5c3cd7ebccd3da6e0aa31f74c828f3c8542af49d840"

    latest_hex = _rpc_call("eth_blockNumber", [])
    if not latest_hex:
        return []

    latest = int(latest_hex, 16)
    txs = []

    # Binary search: find which 100-block window contains the delegation event.
    # Start by checking progressively larger ranges from the end,
    # then narrow down. Most staking txs happened in the last few million blocks.
    # Try recent first, then expand backwards in exponential jumps.
    found_range = None
    search_start = max(latest - 100, 0)

    # Exponential backoff search: 100, 200, 400, 800... blocks from tip
    step = 100
    while search_start >= 0 and step <= 200_000_000:
        from_block = max(search_start - step, 0)
        to_block = min(from_block + 99, latest)  # 100-block window

        result = _rpc_call("eth_getLogs", [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": STAKING_CONTRACT,
            "topics": [delegation_topic, None, addr_padded],
        }])

        if result and isinstance(result, list) and len(result) > 0:
            found_range = (from_block, to_block)
            break

        # Jump backwards exponentially
        search_start -= step
        step *= 2

    # If exponential search didn't find it, try a smarter approach:
    # The nonce is low, so the tx is probably early in the wallet's life.
    # Use eth_getTransactionCount at different blocks to binary-search
    # for the block where nonce went from 0->1.
    if not found_range:
        tx_block = _binary_search_nonce_block(address, 0, latest)
        if tx_block is not None:
            # Found the block, now get the tx from it
            block = _rpc_call("eth_getBlockByNumber", [hex(tx_block), True])
            if block:
                timestamp = int(block["timestamp"], 16)
                for tx in block.get("transactions", []):
                    if isinstance(tx, str):
                        continue
                    if (tx.get("from") or "").lower() == address:
                        value_wei = int(tx.get("value", "0x0"), 16)
                        input_data = tx.get("input", "0x")
                        txs.append({
                            "hash": tx["hash"],
                            "block_number": tx_block,
                            "timestamp": timestamp,
                            "from_addr": address,
                            "to_addr": (tx.get("to") or "").lower(),
                            "value": value_wei / 1e18,
                            "method": input_data[:10] if len(input_data) >= 10 else None,
                        })
            return txs

    if not found_range:
        return []

    # We found events in a 100-block window — extract tx details
    result = _rpc_call("eth_getLogs", [{
        "fromBlock": hex(found_range[0]),
        "toBlock": hex(found_range[1]),
        "address": STAKING_CONTRACT,
        "topics": [delegation_topic, None, addr_padded],
    }])

    if not result or not isinstance(result, list):
        return []

    for log in result:
        tx_hash = log.get("transactionHash")
        if not tx_hash:
            continue
        tx = _rpc_call("eth_getTransactionByHash", [tx_hash])
        if not tx:
            continue
        block_ts_hex = log.get("blockTimestamp")
        if block_ts_hex:
            timestamp = int(block_ts_hex, 16)
        else:
            block = _rpc_call("eth_getBlockByNumber", [log["blockNumber"], False])
            timestamp = int(block["timestamp"], 16) if block else 0

        value_wei = int(tx.get("value", "0x0"), 16)
        input_data = tx.get("input", "0x")
        txs.append({
            "hash": tx_hash,
            "block_number": int(log["blockNumber"], 16),
            "timestamp": timestamp,
            "from_addr": (tx.get("from") or "").lower(),
            "to_addr": (tx.get("to") or "").lower(),
            "value": value_wei / 1e18,
            "method": input_data[:10] if len(input_data) >= 10 else None,
        })

    return txs


def _binary_search_nonce_block(
    address: str, low: int, high: int, target_nonce: int = 1
) -> int | None:
    """Binary search to find the block where an address's nonce changed to target_nonce.

    Returns the block number where the nonce first equals target_nonce, or None.
    Requires ~log2(block_range) RPC calls (~27 calls for 100M blocks).
    """
    # First check current nonce is at least target_nonce
    result = _rpc_call("eth_getTransactionCount", [address, hex(high)])
    if not result or int(result, 16) < target_nonce:
        return None

    # Find a valid low block where nonce is 0.
    # Monad mainnet genesis is around block 66M, so probe to find a valid start.
    found_low = False
    for candidate in [
        low, 1, 1_000_000, 10_000_000, 50_000_000,
        60_000_000, 64_000_000, 66_000_000, 66_100_000,
    ]:
        if candidate > high:
            continue
        result = _rpc_call("eth_getTransactionCount", [address, hex(candidate)])
        if result is not None:
            if int(result, 16) >= target_nonce:
                return candidate  # Already had the nonce at this early block
            low = candidate
            found_low = True
            break
    if not found_low:
        return None  # Couldn't find a valid starting block

    # Binary search
    while low < high:
        mid = (low + high) // 2
        result = _rpc_call("eth_getTransactionCount", [address, hex(mid)])
        if not result:
            return None
        nonce_at_mid = int(result, 16)
        if nonce_at_mid >= target_nonce:
            high = mid
        else:
            low = mid + 1

    return low


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

    # Fallback: Monadscan / RPC
    rpc_txs = _get_recent_txs(address, limit=min(limit, 50))

    # Auto-index discovered transactions into Neo4j in background
    if rpc_txs:
        index_transactions_background(rpc_txs)

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

    # If no graph data indexed, build graph from Monadscan tx data
    if not nodes:
        monadscan_txs = _get_txs_from_monadscan(address, limit=50)
        if monadscan_txs:
            nodes[address] = {"address": address}
            for tx in monadscan_txs:
                from_addr = tx["from_addr"]
                to_addr = tx["to_addr"]
                if from_addr not in nodes:
                    nodes[from_addr] = {"address": from_addr}
                if to_addr and to_addr not in nodes:
                    nodes[to_addr] = {"address": to_addr}
                edges.append({
                    "from": from_addr,
                    "to": to_addr or from_addr,
                    "tx_hash": tx["hash"],
                    "value": tx["value"],
                    "timestamp": tx["timestamp"],
                })
        else:
            nodes[address] = {"address": address}

    return {"nodes": list(nodes.values()), "edges": edges}
