#!/usr/bin/env python3
"""Sync existing data from local Neo4j to Aura, then run indexer against Aura."""

import json
from neo4j import GraphDatabase

# Local
LOCAL_URI = "bolt://localhost:7687"
LOCAL_USER = "neo4j"
LOCAL_PASS = "frank123"
LOCAL_DB = "monad"

# Aura
AURA_URI = "neo4j+s://7592264a.databases.neo4j.io"
AURA_USER = "7592264a"
AURA_PASS = "ObMQl_xhD5XUlrnJuCkk-XvUyslcSrsfPkildWPhn8M"
AURA_DB = "7592264a"

BATCH = 2000  # records per batch


def main():
    print("📦 Connecting to local Neo4j...")
    local = GraphDatabase.driver(LOCAL_URI, auth=(LOCAL_USER, LOCAL_PASS))
    local.verify_connectivity()

    print("☁️  Connecting to Aura...")
    aura = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASS))
    aura.verify_connectivity()

    # --- Count local data ---
    with local.session(database=LOCAL_DB) as s:
        blocks = s.run("MATCH (b:Block) RETURN count(b) AS c").single()["c"]
        txs = s.run("MATCH (tx:Transaction) RETURN count(tx) AS c").single()["c"]
        wallets = s.run("MATCH (w:Wallet) RETURN count(w) AS c").single()["c"]
    print(f"📊 Local: {blocks:,} blocks, {txs:,} txs, {wallets:,} wallets")

    # --- Sync Blocks ---
    print(f"\n🔄 Syncing blocks...")
    offset = 0
    total_blocks = 0
    while True:
        with local.session(database=LOCAL_DB) as s:
            rows = s.run(
                "MATCH (b:Block) RETURN b.number AS number, b.timestamp AS timestamp, "
                "b.tx_count AS tx_count, b.hash AS hash "
                "ORDER BY b.number SKIP $skip LIMIT $limit",
                {"skip": offset, "limit": BATCH},
            ).data()
        if not rows:
            break
        with aura.session(database=AURA_DB) as s:
            s.run(
                """
                UNWIND $blocks AS b
                MERGE (blk:Block {number: b.number})
                ON CREATE SET blk.timestamp = b.timestamp,
                              blk.tx_count = b.tx_count,
                              blk.hash = b.hash
                """,
                {"blocks": rows},
            )
        total_blocks += len(rows)
        print(f"  ✅ {total_blocks:,} blocks synced")
        offset += BATCH

    # --- Sync Transactions + Wallets + Relationships ---
    print(f"\n🔄 Syncing transactions + wallets...")
    offset = 0
    total_txs = 0
    while True:
        with local.session(database=LOCAL_DB) as s:
            rows = s.run(
                """
                MATCH (from:Wallet)-[:SENT]->(tx:Transaction)-[:TO]->(to:Wallet)
                RETURN from.address AS from_addr, to.address AS to_addr,
                       tx.hash AS tx_hash, tx.value AS value,
                       tx.block_number AS block_number, tx.timestamp AS timestamp,
                       tx.method AS method, tx.source AS source
                ORDER BY tx.block_number
                SKIP $skip LIMIT $limit
                """,
                {"skip": offset, "limit": BATCH},
            ).data()
        if not rows:
            break
        with aura.session(database=AURA_DB) as s:
            s.run(
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
                              tx.source = coalesce(t.source, 'sync')

                MERGE (from)-[:SENT]->(tx)
                MERGE (tx)-[:TO]->(to)
                """,
                {"transfers": rows},
            )
        total_txs += len(rows)
        print(f"  ✅ {total_txs:,} transactions synced")
        offset += BATCH

    # --- Verify ---
    with aura.session(database=AURA_DB) as s:
        ab = s.run("MATCH (b:Block) RETURN count(b) AS c").single()["c"]
        at = s.run("MATCH (tx:Transaction) RETURN count(tx) AS c").single()["c"]
        aw = s.run("MATCH (w:Wallet) RETURN count(w) AS c").single()["c"]
    print(f"\n☁️  Aura: {ab:,} blocks, {at:,} txs, {aw:,} wallets")
    print("✅ Sync complete!")

    local.close()
    aura.close()


if __name__ == "__main__":
    main()
