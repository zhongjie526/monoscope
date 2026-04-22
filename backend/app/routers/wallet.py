"""Wallet lookup and analytics endpoints.

Falls back to live Monad RPC when wallet is not in our indexed data.
All HTTP and DB calls are async-safe (non-blocking event loop).
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.database import db
from app.background_index import index_transactions_background, enrich_wallet_background

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level async client — reused across requests (connection pooling)
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


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
    source: str = "indexed"  # "indexed", "rpc", or "not_indexed"
    staking: list[StakingInfo] = []  # staking positions on Monad


class TransactionRecord(BaseModel):
    hash: str
    block_number: int
    timestamp: int
    from_addr: str
    to_addr: str
    value: float
    method: str | None = None


# ── Wallet summary Cypher (shared by get_wallet and scan_wallet) ────────

_WALLET_SUMMARY_CYPHER = """
MATCH (w:Wallet {address: $address})
CALL {
    WITH w
    OPTIONAL MATCH (w)-[:SENT]->(tx_out:Transaction)-[:TO]->(other_out:Wallet)
    RETURN count(tx_out) AS sent_count,
           coalesce(sum(tx_out.value), 0.0) AS total_sent
}
CALL {
    WITH w
    OPTIONAL MATCH (sender:Wallet)-[:SENT]->(tx_in:Transaction)-[:TO]->(w)
    RETURN count(tx_in) AS recv_count,
           coalesce(sum(tx_in.value), 0.0) AS total_received
}
CALL {
    WITH w
    OPTIONAL MATCH (w)-[:SENT]->(:Transaction)-[:TO]->(out:Wallet)
    WITH w, collect(DISTINCT out.address) AS outs
    OPTIONAL MATCH (inc:Wallet)-[:SENT]->(:Transaction)-[:TO]->(w)
    WITH outs, collect(DISTINCT inc.address) AS ins
    UNWIND (outs + ins) AS addr
    RETURN count(DISTINCT addr) AS unique_interactions
}
CALL {
    WITH w
    OPTIONAL MATCH (w)-[:SENT]->(tx1:Transaction)
    RETURN min(tx1.timestamp) AS out_min, max(tx1.timestamp) AS out_max
}
CALL {
    WITH w
    OPTIONAL MATCH (:Wallet)-[:SENT]->(tx2:Transaction)-[:TO]->(w)
    RETURN min(tx2.timestamp) AS in_min, max(tx2.timestamp) AS in_max
}
WITH w, sent_count, total_sent, recv_count, total_received, unique_interactions,
     coalesce(CASE WHEN out_min IS NOT NULL AND in_min IS NOT NULL
                   THEN CASE WHEN out_min < in_min THEN out_min ELSE in_min END
                   WHEN out_min IS NOT NULL THEN out_min ELSE in_min END, null) AS first_seen,
     coalesce(CASE WHEN out_max IS NOT NULL AND in_max IS NOT NULL
                   THEN CASE WHEN out_max > in_max THEN out_max ELSE in_max END
                   WHEN out_max IS NOT NULL THEN out_max ELSE in_max END, null) AS last_seen
RETURN w.address AS address,
       w.balance AS balance,
       w.staked AS staked,
       w.staking_rewards AS staking_rewards,
       w.risk_score AS risk_score,
       w.labels AS labels,
       first_seen, last_seen,
       sent_count, total_sent, recv_count, total_received,
       unique_interactions
"""


# ── RPC helpers (async) ─────────────────────────────────────────────────

async def _rpc_call(method: str, params: list) -> dict | None:
    """Async JSON-RPC call to Monad."""
    try:
        client = _get_client()
        resp = await client.post(
            settings.monad_rpc_url,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
        )
        data = resp.json()
        return data.get("result")
    except Exception:
        return None


async def _rpc_batch(calls: list[tuple[str, list]]) -> list[dict | None]:
    """Batch multiple JSON-RPC calls into a single HTTP request."""
    if not calls:
        return []
    batch = [
        {"jsonrpc": "2.0", "method": method, "params": params, "id": i}
        for i, (method, params) in enumerate(calls)
    ]
    try:
        client = _get_client()
        resp = await client.post(settings.monad_rpc_url, json=batch, timeout=15)
        results = resp.json()
        results.sort(key=lambda r: r["id"])
        return [r.get("result") for r in results]
    except Exception:
        return [None] * len(calls)


async def _get_balance(address: str) -> float | None:
    result = await _rpc_call("eth_getBalance", [address, "latest"])
    if result:
        return int(result, 16) / 1e18
    return None


async def _get_tx_count(address: str) -> int:
    result = await _rpc_call("eth_getTransactionCount", [address, "latest"])
    if result:
        return int(result, 16)
    return 0


STAKING_CONTRACT = "0x0000000000000000000000000000000000001000"
GET_DELEGATOR_SELECTOR = "0x573c1ce0"
GET_DELEGATIONS_SELECTOR = "0x4fd66050"


async def _get_staking_info(address: str) -> list[dict]:
    """Query Monad staking precompile for delegation info.

    Uses a single batched RPC call for all 20 validators instead of
    20 sequential calls (~10x faster).
    """
    addr_padded = address.lower().replace("0x", "").zfill(40)
    addr_hex = "000000000000000000000000" + addr_padded

    # Build batch: 20 eth_call requests for validators 1-20
    calls: list[tuple[str, list]] = []
    for val_id in range(1, 21):
        val_hex = hex(val_id)[2:].zfill(64)
        data = GET_DELEGATOR_SELECTOR + val_hex + addr_hex
        calls.append(("eth_call", [{"to": STAKING_CONTRACT, "data": data}, "latest"]))

    results = await _rpc_batch(calls)

    stakes = []
    for val_id, result in enumerate(results, start=1):
        if not result or result == "0x" or len(result) < 130:
            continue

        hex_data = result[2:]
        chunks = [hex_data[i:i + 64] for i in range(0, len(hex_data), 64)]
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


async def _get_txs_from_monadscan(address: str, limit: int = 50) -> list[dict] | None:
    """Fetch transaction history from Monadscan (Etherscan V2 API)."""
    if not settings.monadscan_api_key:
        return None

    try:
        client = _get_client()
        resp = await client.get(
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


async def _get_recent_txs(address: str, limit: int = 50) -> list[dict]:
    """Get transactions for an address.

    Priority:
    1. Monadscan API (full history, fast)
    2. RPC binary search fallback (outbound only, slower)
    """
    address = address.lower()

    # Try Monadscan first
    monadscan_txs = await _get_txs_from_monadscan(address, limit)
    if monadscan_txs is not None:
        return monadscan_txs

    # Fallback: binary search for outbound txs via nonce
    txs: list[dict] = []
    seen_hashes: set[str] = set()

    latest_hex = await _rpc_call("eth_blockNumber", [])
    if not latest_hex:
        return []

    nonce_count = await _get_tx_count(address)
    if nonce_count > 0 and nonce_count <= 20:
        latest_block = int(latest_hex, 16)
        for target_n in range(1, nonce_count + 1):
            block_num = await _binary_search_nonce_block(address, 0, latest_block, target_nonce=target_n)
            if block_num is None:
                continue
            block = await _rpc_call("eth_getBlockByNumber", [hex(block_num), True])
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


async def _find_staking_txs(address: str) -> list[dict]:
    """Find staking delegation transactions for a wallet."""
    address = address.lower()
    addr_padded = "0x000000000000000000000000" + address.replace("0x", "")
    delegation_topic = "0xe4d4df1e1827dd28252fd5c3cd7ebccd3da6e0aa31f74c828f3c8542af49d840"

    latest_hex = await _rpc_call("eth_blockNumber", [])
    if not latest_hex:
        return []

    latest = int(latest_hex, 16)
    txs = []

    found_range = None
    search_start = max(latest - 100, 0)

    step = 100
    while search_start >= 0 and step <= 200_000_000:
        from_block = max(search_start - step, 0)
        to_block = min(from_block + 99, latest)

        result = await _rpc_call("eth_getLogs", [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": STAKING_CONTRACT,
            "topics": [delegation_topic, None, addr_padded],
        }])

        if result and isinstance(result, list) and len(result) > 0:
            found_range = (from_block, to_block)
            break

        search_start -= step
        step *= 2

    if not found_range:
        tx_block = await _binary_search_nonce_block(address, 0, latest)
        if tx_block is not None:
            block = await _rpc_call("eth_getBlockByNumber", [hex(tx_block), True])
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

    result = await _rpc_call("eth_getLogs", [{
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
        tx = await _rpc_call("eth_getTransactionByHash", [tx_hash])
        if not tx:
            continue
        block_ts_hex = log.get("blockTimestamp")
        if block_ts_hex:
            timestamp = int(block_ts_hex, 16)
        else:
            block = await _rpc_call("eth_getBlockByNumber", [log["blockNumber"], False])
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


async def _binary_search_nonce_block(
    address: str, low: int, high: int, target_nonce: int = 1
) -> int | None:
    """Binary search to find the block where an address's nonce changed."""
    result = await _rpc_call("eth_getTransactionCount", [address, hex(high)])
    if not result or int(result, 16) < target_nonce:
        return None

    found_low = False
    for candidate in [
        low, 1, 1_000_000, 10_000_000, 50_000_000,
        60_000_000, 64_000_000, 66_000_000, 66_100_000,
    ]:
        if candidate > high:
            continue
        result = await _rpc_call("eth_getTransactionCount", [address, hex(candidate)])
        if result is not None:
            if int(result, 16) >= target_nonce:
                return candidate
            low = candidate
            found_low = True
            break
    if not found_low:
        return None

    while low < high:
        mid = (low + high) // 2
        result = await _rpc_call("eth_getTransactionCount", [address, hex(mid)])
        if not result:
            return None
        nonce_at_mid = int(result, 16)
        if nonce_at_mid >= target_nonce:
            high = mid
        else:
            low = mid + 1

    return low


# ── Endpoints ───────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    start_ts: int | None = None  # Unix timestamp
    end_ts: int | None = None


async def _timestamp_to_block(ts: int) -> int | None:
    """Convert a Unix timestamp to a block number via Monadscan API."""
    try:
        client = _get_client()
        resp = await client.get(
            settings.monadscan_api_url,
            params={
                "chainid": settings.monadscan_chain_id,
                "module": "block",
                "action": "getblocknobytime",
                "timestamp": ts,
                "closest": "before",
                "apikey": settings.monadscan_api_key,
            },
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("message") == "OK":
            return int(data["result"])
    except Exception:
        pass
    return None


async def _get_txs_from_monadscan_range(
    address: str, start_block: int = 0, end_block: int = 99999999, max_pages: int = 5,
) -> list[dict]:
    """Fetch transactions from Monadscan with block range and pagination."""
    if not settings.monadscan_api_key:
        return []
    client = _get_client()
    all_txs = []
    page = 1
    while page <= max_pages:
        try:
            resp = await client.get(
                settings.monadscan_api_url,
                params={
                    "chainid": settings.monadscan_chain_id,
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": start_block,
                    "endblock": end_block,
                    "page": page,
                    "offset": 1000,
                    "sort": "asc",
                    "apikey": settings.monadscan_api_key,
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != "1" or not data.get("result"):
                break
            for r in data["result"]:
                value_wei = int(r.get("value", "0"))
                input_data = r.get("input", "0x")
                all_txs.append({
                    "hash": r["hash"],
                    "block_number": int(r["blockNumber"]),
                    "timestamp": int(r["timeStamp"]),
                    "from_addr": r["from"].lower(),
                    "to_addr": (r.get("to") or "").lower(),
                    "value": value_wei / 1e18,
                    "method": input_data[:10] if len(input_data) >= 10 else None,
                })
            if len(data["result"]) < 1000:
                break  # Last page
            page += 1
        except Exception:
            break
    return all_txs


@router.post("/{address}/scan")
async def scan_wallet(address: str, body: ScanRequest | None = None):
    """Re-scan a wallet: fetch transactions from Monadscan and index into Neo4j.

    Optionally accepts start_ts/end_ts (Unix timestamps) to scan a specific period.
    Returns updated wallet summary after indexing.
    """
    address = address.lower()
    body = body or ScanRequest()

    # Convert timestamps to block numbers if provided
    start_block = 0
    end_block = 99999999
    if body.start_ts:
        b = await _timestamp_to_block(body.start_ts)
        if b is not None:
            start_block = b
    if body.end_ts:
        b = await _timestamp_to_block(body.end_ts)
        if b is not None:
            end_block = b

    # Fetch with pagination (up to 5000 txs)
    txs = await _get_txs_from_monadscan_range(address, start_block, end_block, max_pages=5)
    indexed_count = 0
    if txs:
        from app.background_index import _index_transactions
        await asyncio.to_thread(_index_transactions, txs)
        indexed_count = len(txs)

    # Re-fetch wallet summary (now from Neo4j with fresh data)
    balance = await _get_balance(address)
    staking = await _get_staking_info(address)

    # Re-query the newly indexed data using shared Cypher
    result = await asyncio.to_thread(db.query, _WALLET_SUMMARY_CYPHER, {"address": address})

    if result and result[0].get("address"):
        r = result[0]
        summary = WalletSummary(
            address=address,
            balance=balance or 0.0,
            tx_count=(r["sent_count"] or 0) + (r["recv_count"] or 0),
            total_sent=r["total_sent"] or 0.0,
            total_received=r["total_received"] or 0.0,
            unique_interactions=r["unique_interactions"] or 0,
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            source="indexed",
            staking=[StakingInfo(**s) for s in staking],
        )
        enrich_wallet_background(address, summary.model_dump())
        return {"indexed": indexed_count, "wallet": summary}

    return {"indexed": indexed_count, "wallet": None}


@router.post("/batch-stats")
async def batch_wallet_stats(addresses: list[str]):
    """Get cached wallet stats from Neo4j for multiple addresses.

    Returns only data already stored on nodes — no RPC calls.
    Fast enough for favourites lists.
    """
    addrs = [a.lower() for a in addresses[:50]]  # cap at 50
    result = await asyncio.to_thread(
        db.query,
        """
        UNWIND $addrs AS addr
        OPTIONAL MATCH (w:Wallet {address: addr})
        RETURN addr AS address,
               w.balance AS balance,
               w.tx_count AS tx_count,
               w.total_sent AS total_sent,
               w.total_received AS total_received,
               w.staked AS staked,
               w.staking_rewards AS staking_rewards,
               w.labels AS labels,
               w.stats_updated AS stats_updated
        """,
        {"addrs": addrs},
    )
    return [
        {
            "address": r["address"],
            "balance": r.get("balance"),
            "tx_count": r.get("tx_count"),
            "total_sent": r.get("total_sent"),
            "total_received": r.get("total_received"),
            "staked": r.get("staked"),
            "staking_rewards": r.get("staking_rewards"),
            "labels": r.get("labels") or [],
            "has_data": r.get("balance") is not None,
        }
        for r in result
    ]


@router.get("/{address}", response_model=WalletSummary)
async def get_wallet(address: str):
    """Look up a wallet — checks indexed data first, falls back to live RPC."""
    address = address.lower()

    # Try indexed data first — single query includes cached balance/staking
    result = await asyncio.to_thread(db.query, _WALLET_SUMMARY_CYPHER, {"address": address})

    if result and result[0].get("address"):
        r = result[0]
        # Build staking list from cached data
        staking_list = []
        if r.get("staked") and r["staked"] > 0:
            staking_list = [{"validator_id": 0, "staked": r["staked"], "rewards": r.get("staking_rewards") or 0.0}]
        return WalletSummary(
            address=r["address"],
            balance=r.get("balance"),
            tx_count=(r["sent_count"] or 0) + (r["recv_count"] or 0),
            total_sent=r["total_sent"] or 0.0,
            total_received=r["total_received"] or 0.0,
            unique_interactions=r["unique_interactions"] or 0,
            first_seen=r["first_seen"],
            last_seen=r["last_seen"],
            risk_score=r["risk_score"],
            labels=r["labels"] or [],
            source="indexed",
            staking=[StakingInfo(**s) for s in staking_list],
        )

    # No indexed data — return empty shell, user can Scan to populate
    return WalletSummary(
        address=address,
        balance=None,
        tx_count=0,
        source="not_indexed",
        labels=["not indexed"],
    )


@router.get("/{address}/transactions", response_model=list[TransactionRecord])
async def get_wallet_transactions(address: str, limit: int = 50):
    """Get recent transactions — indexed data first, RPC fallback."""
    address = address.lower()

    # Try indexed data
    result = await asyncio.to_thread(
        db.query,
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

    # Pre-built queries for each valid depth to avoid string interpolation in Cypher
    _GRAPH_QUERIES = {
        2: "MATCH path = (start:Wallet {address: $address})-[:SENT|TO*1..2]-(end:Wallet) WHERE start <> end WITH path LIMIT $limit UNWIND relationships(path) AS r WITH DISTINCT r WHERE type(r) = 'TO' WITH startNode(r) AS tx, endNode(r) AS to_wallet MATCH (from_wallet:Wallet)-[:SENT]->(tx) RETURN DISTINCT from_wallet.address AS from_addr, to_wallet.address AS to_addr, tx.hash AS tx_hash, tx.value AS value, tx.timestamp AS timestamp",
        4: "MATCH path = (start:Wallet {address: $address})-[:SENT|TO*1..4]-(end:Wallet) WHERE start <> end WITH path LIMIT $limit UNWIND relationships(path) AS r WITH DISTINCT r WHERE type(r) = 'TO' WITH startNode(r) AS tx, endNode(r) AS to_wallet MATCH (from_wallet:Wallet)-[:SENT]->(tx) RETURN DISTINCT from_wallet.address AS from_addr, to_wallet.address AS to_addr, tx.hash AS tx_hash, tx.value AS value, tx.timestamp AS timestamp",
        6: "MATCH path = (start:Wallet {address: $address})-[:SENT|TO*1..6]-(end:Wallet) WHERE start <> end WITH path LIMIT $limit UNWIND relationships(path) AS r WITH DISTINCT r WHERE type(r) = 'TO' WITH startNode(r) AS tx, endNode(r) AS to_wallet MATCH (from_wallet:Wallet)-[:SENT]->(tx) RETURN DISTINCT from_wallet.address AS from_addr, to_wallet.address AS to_addr, tx.hash AS tx_hash, tx.value AS value, tx.timestamp AS timestamp",
        8: "MATCH path = (start:Wallet {address: $address})-[:SENT|TO*1..8]-(end:Wallet) WHERE start <> end WITH path LIMIT $limit UNWIND relationships(path) AS r WITH DISTINCT r WHERE type(r) = 'TO' WITH startNode(r) AS tx, endNode(r) AS to_wallet MATCH (from_wallet:Wallet)-[:SENT]->(tx) RETURN DISTINCT from_wallet.address AS from_addr, to_wallet.address AS to_addr, tx.hash AS tx_hash, tx.value AS value, tx.timestamp AS timestamp",
    }
    cypher = _GRAPH_QUERIES.get(rel_depth, _GRAPH_QUERIES[4])

    result = await asyncio.to_thread(
        db.query,
        cypher,
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

    # Enrich nodes with wallet stats from Neo4j
    if nodes:
        addrs = list(nodes.keys())
        stats = await asyncio.to_thread(
            db.query,
            """
            UNWIND $addrs AS addr
            MATCH (w:Wallet {address: addr})
            RETURN w.address AS address,
                   w.balance AS balance,
                   w.tx_count AS tx_count,
                   w.total_sent AS total_sent,
                   w.total_received AS total_received,
                   w.staked AS staked,
                   w.staking_rewards AS staking_rewards
            """,
            {"addrs": addrs},
        )
        for s in stats:
            addr = s["address"]
            if addr in nodes:
                nodes[addr].update({
                    k: v for k, v in {
                        "balance": s.get("balance"),
                        "tx_count": s.get("tx_count"),
                        "total_sent": s.get("total_sent"),
                        "total_received": s.get("total_received"),
                        "staked": s.get("staked"),
                        "staking_rewards": s.get("staking_rewards"),
                    }.items() if v is not None
                })

    # If no graph data indexed, build graph from Monadscan tx data
    if not nodes:
        monadscan_txs = await _get_txs_from_monadscan(address, limit=50)
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
