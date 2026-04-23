#!/usr/bin/env python3
"""Monoscope Batch Indexer — fetches blocks from Monad RPC and indexes
transactions into Neo4j.

Usage:
    python3 scripts/indexer.py                  # resume from last_block
    python3 scripts/indexer.py --from 69302727  # start from specific block
    python3 scripts/indexer.py --batches 500    # limit number of RPC batches

Each RPC call fetches BATCH_SIZE blocks (50 by default).
Transactions are written in bulk using UNWIND Cypher.
State is persisted to data/indexer_state.json after each batch.
"""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Load .env from backend/ (where the app keeps its config)
_env_paths = [
    Path(__file__).parent.parent / "backend" / ".env",
    Path(__file__).parent.parent / ".env",
]
for p in _env_paths:
    if p.exists():
        load_dotenv(p)

# ── Config ──────────────────────────────────────────────────────────

RPC_URL = os.getenv("MONAD_RPC_URL", "https://rpc.monad.xyz")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DB = os.getenv("NEO4J_DATABASE", "monad")

BATCH_SIZE = 50          # blocks per RPC batch call
WRITE_BATCH = 500        # max txs per Cypher UNWIND
RPC_TIMEOUT = 30         # seconds
SLEEP_BETWEEN = 0.1      # seconds between RPC batches (rate limiting)
STATE_FILE = Path(__file__).parent.parent / "data" / "indexer_state.json"

# ── Globals ─────────────────────────────────────────────────────────

running = True
stats = {"blocks": 0, "txs": 0, "wallets_seen": set(), "start_time": 0}


def signal_handler(sig, frame):
    global running
    print("\n🛑 Graceful shutdown requested...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ── RPC ─────────────────────────────────────────────────────────────

client = httpx.Client(timeout=RPC_TIMEOUT)


def rpc_call(method, params=None):
    resp = client.post(
        RPC_URL,
        json={"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1},
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data["result"]


def rpc_batch(requests):
    """Send a batch JSON-RPC request."""
    resp = client.post(RPC_URL, json=requests)
    results = resp.json()
    # Sort by id to match request order
    if isinstance(results, list):
        results.sort(key=lambda r: r.get("id", 0))
    return results


def get_latest_block():
    return int(rpc_call("eth_blockNumber"), 16)


def fetch_blocks(start, count):
    """Fetch `count` blocks starting from `start` using batch RPC."""
    requests = [
        {
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": [hex(start + i), True],  # True = include full txs
            "id": i,
        }
        for i in range(count)
    ]
    responses = rpc_batch(requests)

    blocks = []
    for r in responses:
        if isinstance(r, dict) and r.get("result"):
            blocks.append(r["result"])
    return blocks


# ── Neo4j ───────────────────────────────────────────────────────────

def connect_neo4j():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    return driver


def write_blocks(driver, blocks):
    """Write blocks and their transactions to Neo4j."""
    # Prepare block data
    block_data = []
    tx_data = []

    for block in blocks:
        block_num = int(block["number"], 16)
        timestamp = int(block["timestamp"], 16)
        tx_count = len(block.get("transactions", []))

        block_data.append({
            "number": block_num,
            "timestamp": timestamp,
            "tx_count": tx_count,
            "hash": block["hash"],
        })

        for tx in block.get("transactions", []):
            from_addr = (tx.get("from") or "").lower()
            to_addr = (tx.get("to") or "").lower()
            value_wei = int(tx.get("value", "0x0"), 16)
            value_mon = value_wei / 1e18

            if not from_addr:
                continue

            tx_data.append({
                "tx_hash": tx["hash"],
                "from_addr": from_addr,
                "to_addr": to_addr or from_addr,  # contract creation → self
                "value": value_mon,
                "block_number": block_num,
                "timestamp": timestamp,
                "method": (tx.get("input") or "0x")[:10] if tx.get("input", "0x") != "0x" else None,
            })

            stats["wallets_seen"].add(from_addr)
            if to_addr:
                stats["wallets_seen"].add(to_addr)

    with driver.session(database=NEO4J_DB) as session:
        # Write blocks (skip if --no-blocks to save Aura Free node limit)
        if block_data and not getattr(write_blocks, '_no_blocks', False):
            session.run(
                """
                UNWIND $blocks AS b
                MERGE (blk:Block {number: b.number})
                ON CREATE SET blk.timestamp = b.timestamp,
                              blk.tx_count = b.tx_count,
                              blk.hash = b.hash
                """,
                {"blocks": block_data},
            )

        # Write transactions in chunks
        for i in range(0, len(tx_data), WRITE_BATCH):
            chunk = tx_data[i : i + WRITE_BATCH]
            session.run(
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
                              tx.source = 'indexer'

                MERGE (from)-[:SENT]->(tx)
                MERGE (tx)-[:TO]->(to)
                """,
                {"transfers": chunk},
            )

    stats["blocks"] += len(blocks)
    stats["txs"] += len(tx_data)


# ── State ───────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(last_block, start_block=None):
    state = load_state()
    state["last_block"] = last_block
    if start_block and "start_block" not in state:
        state["start_block"] = start_block
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Monoscope Batch Indexer")
    parser.add_argument("--from", dest="from_block", type=int, help="Start from this block")
    parser.add_argument("--batches", type=int, default=0, help="Max RPC batches (0=unlimited)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Blocks per RPC batch (default {BATCH_SIZE})")
    parser.add_argument("--tail", action="store_true", help="Keep running, tail new blocks")
    parser.add_argument("--no-blocks", action="store_true", help="Skip Block node creation (saves nodes on Aura Free)")
    args = parser.parse_args()

    batch_size = args.batch_size

    print("🔬 Monoscope Indexer")
    print("=" * 50)

    # Connect Neo4j
    print("📦 Connecting to Neo4j...")
    driver = connect_neo4j()
    print("✅ Neo4j connected")

    # Set no-blocks flag on write_blocks function
    if args.no_blocks:
        write_blocks._no_blocks = True
        print("⚡ Skipping Block node creation (--no-blocks)")
    else:
        write_blocks._no_blocks = False

    # Determine start block
    latest = get_latest_block()
    state = load_state()

    if args.from_block:
        start = args.from_block
    elif state.get("last_block"):
        start = state["last_block"] + 1
    else:
        # Try to resume from highest block in Neo4j
        try:
            with driver.session(database=NEO4J_DB) as s:
                result = s.run("MATCH (b:Block) RETURN MAX(b.number) AS max_block").single()
                max_block = result["max_block"] if result else None
            if max_block:
                start = max_block + 1
                print(f"📍 Resuming from Neo4j max block: {max_block:,}")
            else:
                start = latest - 1000
        except Exception:
            start = latest - 1000

    gap = latest - start
    print(f"📊 Latest block: {latest:,}")
    print(f"📍 Starting from: {start:,}")
    print(f"📏 Gap: {gap:,} blocks (~{gap // batch_size} batches)")
    print(f"⚙️  Batch size: {batch_size} blocks")
    if args.batches:
        print(f"🔢 Max batches: {args.batches}")
    print()

    stats["start_time"] = time.time()
    batch_count = 0
    current = start

    try:
        while running:
            # Check if we've caught up
            if current > latest:
                if args.tail:
                    time.sleep(2)
                    latest = get_latest_block()
                    continue
                else:
                    print("✅ Caught up to chain head!")
                    break

            # Check batch limit
            if args.batches and batch_count >= args.batches:
                print(f"✅ Reached batch limit ({args.batches})")
                break

            # Fetch blocks
            fetch_count = min(batch_size, latest - current + 1)
            try:
                blocks = fetch_blocks(current, fetch_count)
            except Exception as e:
                print(f"⚠️  RPC error at block {current}: {e}")
                time.sleep(2)
                continue

            if not blocks:
                current += fetch_count
                continue

            # Write to Neo4j
            try:
                write_blocks(driver, blocks)
            except Exception as e:
                print(f"⚠️  Neo4j write error at block {current}: {e}")
                time.sleep(1)
                continue

            # Update state
            max_block = max(int(b["number"], 16) for b in blocks)
            save_state(max_block, start_block=start)
            current = max_block + 1
            batch_count += 1

            # Progress
            elapsed = time.time() - stats["start_time"]
            blocks_done = current - start
            bps = blocks_done / elapsed if elapsed > 0 else 0
            remaining = latest - current
            eta = remaining / bps if bps > 0 else 0

            if batch_count % 10 == 0:
                print(
                    f"  📦 Batch {batch_count}: block {max_block:,} | "
                    f"{stats['txs']:,} txs | {len(stats['wallets_seen']):,} wallets | "
                    f"{bps:.0f} blocks/s | ETA {eta/60:.0f}m"
                )

            time.sleep(SLEEP_BETWEEN)

    except KeyboardInterrupt:
        pass
    finally:
        elapsed = time.time() - stats["start_time"]
        print()
        print("=" * 50)
        print(f"📊 Indexed {stats['blocks']:,} blocks, {stats['txs']:,} transactions")
        print(f"👛 {len(stats['wallets_seen']):,} unique wallets seen")
        print(f"⏱️  {elapsed:.1f}s elapsed ({stats['blocks']/elapsed:.0f} blocks/s)" if elapsed > 0 else "")
        print(f"📍 Last block: {current - 1:,}")
        driver.close()
        print("🛑 Done.")


if __name__ == "__main__":
    main()
