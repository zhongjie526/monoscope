"""Neo4j database connection and schema setup.

Provides both sync (query/write) and async (aquery/awrite) interfaces.
The sync methods are used by the indexer and background threads.
The async methods use asyncio.to_thread() to avoid blocking the event loop
and should be used by all FastAPI endpoint handlers.
"""

import asyncio

from neo4j import GraphDatabase
from app.config import settings


class Neo4jDB:
    """Manages Neo4j driver lifecycle and provides query helpers."""

    def __init__(self):
        self.driver = None

    def connect(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self.driver.verify_connectivity()
        self._create_schema()

    def close(self):
        if self.driver:
            self.driver.close()

    def _session(self):
        """Return a session bound to the configured database."""
        return self.driver.session(database=settings.neo4j_database)

    def _create_schema(self):
        """Create indexes and constraints for the graph schema."""
        with self._session() as session:
            # --- Node constraints (unique IDs) ---
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (w:Wallet) REQUIRE w.address IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (b:Block) REQUIRE b.number IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (tx:Transaction) REQUIRE tx.hash IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (c:Contract) REQUIRE c.address IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (t:Token) REQUIRE t.address IS UNIQUE"
            )

            # --- Indexes for fast lookups ---
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (w:Wallet) ON (w.first_seen)"
            )
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (tx:Transaction) ON (tx.block_number)"
            )
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (tx:Transaction) ON (tx.timestamp)"
            )
            session.run(
                "CREATE INDEX IF NOT EXISTS FOR (w:Wallet) ON (w.risk_score)"
            )

    # ── Sync interface (for indexer / background threads) ────────────

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Run a read query and return list of record dicts (sync)."""
        with self._session() as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def write(self, cypher: str, params: dict | None = None):
        """Run a write query (sync)."""
        with self._session() as session:
            session.run(cypher, params or {})

    # ── Async interface (for FastAPI endpoints) ─────────────────────

    async def aquery(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Run a read query without blocking the event loop."""
        return await asyncio.to_thread(self.query, cypher, params)

    async def awrite(self, cypher: str, params: dict | None = None):
        """Run a write query without blocking the event loop."""
        await asyncio.to_thread(self.write, cypher, params)


# Singleton
db = Neo4jDB()
