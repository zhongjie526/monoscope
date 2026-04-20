"""Monad Blockchain Indexer — polls blocks from RPC and writes to Neo4j.

Usage:
    cd backend
    python -m indexer.run [--start BLOCK_NUMBER] [--batch BATCH_SIZE]

The indexer tracks its last processed block in data/indexer_state.json
so it can resume after restart.
"""

import json
import time
import argparse
import signal
import sys
from pathlib import Path

import httpx

from app.config import settings
from app.database import db

STATE_FILE = Path(__file__).parent.parent.parent / "data" / "indexer_state.json"

# ERC-20 Transfer event topic
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

running = True


def signal_handler(sig, frame):
    global running
    print("\n🛑 Shutting down indexer...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ── RPC Helpers ─────────────────────────────────────────────────────────


def rpc_call(method: str, params: list, client: httpx.Client) -> dict:
    """Make a JSON-RPC call to Monad."""
    resp = client.post(
        settings.monad_rpc_url,
        json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(f"RPC error: {data['error']}")
    return data["result"]


def get_latest_block(client: httpx.Client) -> int:
    result = rpc_call("eth_blockNumber", [], client)
    return int(result, 16)


def get_block_with_txs(block_num: int, client: httpx.Client) -> dict:
    hex_num = hex(block_num)
    return rpc_call("eth_getBlockByNumber", [hex_num, True], client)


def get_blocks_batch(block_nums: list[int], client: httpx.Client) -> list[dict]:
    """Fetch multiple blocks in a single JSON-RPC batch call."""
    batch = [
        {"jsonrpc": "2.0", "method": "eth_getBlockByNumber", "params": [hex(n), True], "id": i}
        for i, n in enumerate(block_nums)
    ]
    resp = client.post(settings.monad_rpc_url, json=batch, timeout=30)
    resp.raise_for_status()
    results = resp.json()
    # Sort by id to maintain order
    results.sort(key=lambda r: r["id"])
    return [r["result"] for r in results if "result" in r]


def get_tx_receipt(tx_hash: str, client: httpx.Client) -> dict:
    return rpc_call("eth_getTransactionReceipt", [tx_hash], client)


# ── State Persistence ──────────────────────────────────────────────────


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_block": 0}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Neo4j Write Logic ──────────────────────────────────────────────────


def index_block(block: dict, client: httpx.Client):
    """Process a single block — batch all transactions into a single Neo4j write."""
    block_number = int(block["number"], 16)
    timestamp = int(block["timestamp"], 16)

    txs = block.get("transactions", [])

    # Prepare batch data
    transfers = []   # normal wallet-to-wallet transfers
    deploys = []     # contract creations

    for tx in txs:
        if isinstance(tx, str):
            continue

        from_addr = tx.get("from", "").lower()
        to_addr = (tx.get("to") or "").lower()
        value_wei = int(tx.get("value", "0x0"), 16)
        value_mon = value_wei / 1e18
        tx_hash = tx["hash"]
        input_data = tx.get("input", "0x")
        method_sig = input_data[:10] if len(input_data) >= 10 else None
        is_contract_creation = not to_addr and input_data != "0x"

        if to_addr:
            transfers.append({
                "from_addr": from_addr,
                "to_addr": to_addr,
                "tx_hash": tx_hash,
                "value": value_mon,
                "method": method_sig,
            })
        elif is_contract_creation:
            try:
                receipt = get_tx_receipt(tx_hash, client)
                contract_addr = (receipt.get("contractAddress") or "").lower()
                if contract_addr:
                    deploys.append({
                        "from_addr": from_addr,
                        "contract_addr": contract_addr,
                        "tx_hash": tx_hash,
                    })
            except Exception as e:
                print(f"  ⚠️ Receipt failed for {tx_hash[:10]}...: {e}")

    # Single batched write: Block + all transfers in one Cypher call
    if transfers:
        db.write(
            """
            MERGE (b:Block {number: $block_number})
            SET b.timestamp = $timestamp, b.hash = $block_hash

            WITH b
            UNWIND $transfers AS t

            MERGE (from:Wallet {address: t.from_addr})
            ON CREATE SET from.first_seen = $timestamp
            SET from.last_seen = $timestamp

            MERGE (to:Wallet {address: t.to_addr})
            ON CREATE SET to.first_seen = $timestamp
            SET to.last_seen = $timestamp

            CREATE (tx:Transaction {
                hash: t.tx_hash,
                value: t.value,
                block_number: $block_number,
                timestamp: $timestamp,
                method: t.method
            })
            CREATE (from)-[:SENT]->(tx)
            CREATE (tx)-[:TO]->(to)

            // Maintain summary edge for fast fraud traversal
            MERGE (from)-[agg:TRANSACTED]->(to)
            ON CREATE SET agg.tx_count = 1,
                          agg.total_value = t.value,
                          agg.first_seen = $timestamp,
                          agg.last_seen = $timestamp
            ON MATCH SET agg.tx_count = agg.tx_count + 1,
                         agg.total_value = agg.total_value + t.value,
                         agg.last_seen = $timestamp
            """,
            {
                "block_number": block_number,
                "timestamp": timestamp,
                "block_hash": block["hash"],
                "transfers": transfers,
            },
        )
    else:
        # Block with no transfers — still record it
        db.write(
            "MERGE (b:Block {number: $number}) SET b.timestamp = $timestamp, b.hash = $hash",
            {"number": block_number, "timestamp": timestamp, "hash": block["hash"]},
        )

    # Batch contract deployments (rare, but handle them)
    if deploys:
        db.write(
            """
            UNWIND $deploys AS d

            MERGE (from:Wallet {address: d.from_addr})
            ON CREATE SET from.first_seen = $timestamp
            SET from.last_seen = $timestamp

            MERGE (c:Contract {address: d.contract_addr})
            ON CREATE SET c.created_at = $timestamp, c.creator = d.from_addr

            CREATE (tx:Transaction {
                hash: d.tx_hash,
                block_number: $block_number,
                timestamp: $timestamp,
                method: 'deploy'
            })
            CREATE (from)-[:SENT]->(tx)
            CREATE (tx)-[:DEPLOYED]->(c)
            """,
            {
                "block_number": block_number,
                "timestamp": timestamp,
                "deploys": deploys,
            },
        )

    return len(transfers) + len(deploys)


# ── Main Loop ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Monad Watchdog Indexer")
    parser.add_argument("--start", type=int, help="Start from this block number")
    parser.add_argument("--batch", type=int, default=50,
                        help="Blocks per RPC batch call (max 100)")
    args = parser.parse_args()
    args.batch = min(args.batch, 100)  # RPC batch limit

    db.connect()
    print("✅ Neo4j connected")

    state = load_state()
    if args.start:
        state["last_block"] = args.start
        print(f"📍 Starting from block {args.start}")

    client = httpx.Client()

    # If first run, start from near the tip (not genesis)
    if state["last_block"] == 0:
        latest = get_latest_block(client)
        state["last_block"] = latest - 100  # start 100 blocks behind tip
        print(f"📍 First run — starting from block {state['last_block']}")

    print(f"🐕 Monad Watchdog Indexer running (batch={args.batch})")
    print(f"   RPC: {settings.monad_rpc_url}")
    print(f"   Last block: {state['last_block']}")

    blocks_since_save = 0
    total_txs = 0
    start_time = time.time()

    while running:
        try:
            latest = get_latest_block(client)

            if state["last_block"] >= latest:
                time.sleep(settings.indexer_poll_interval)
                continue

            # Batch RPC: fetch N blocks in one call
            start_block = state["last_block"] + 1
            end_block = min(start_block + args.batch - 1, latest)
            block_nums = list(range(start_block, end_block + 1))

            blocks = get_blocks_batch(block_nums, client)

            batch_txs = 0
            for block in blocks:
                if not running:
                    break
                if block:
                    tx_count = index_block(block, client)
                    batch_txs += tx_count

                state["last_block"] = int(block["number"], 16)
                blocks_since_save += 1

            total_txs += batch_txs
            elapsed = time.time() - start_time
            bps = blocks_since_save / elapsed if elapsed > 0 else 0

            if batch_txs > 0:
                print(f"  📦 Blocks {start_block}-{end_block}: {batch_txs} txs ({bps:.0f} blocks/s, {total_txs:,} total)")

            # Save state after each batch
            save_state(state)
            blocks_since_save = 0
            start_time = time.time()

        except httpx.HTTPError as e:
            print(f"⚠️ RPC error: {e}. Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"❌ Error: {e}. Retrying in 5s...")
            time.sleep(5)

    # Final save
    save_state(state)
    db.close()
    print(f"✅ Indexer stopped at block {state['last_block']}")


if __name__ == "__main__":
    main()
