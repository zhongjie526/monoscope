"""Application configuration — loaded from environment / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Monad RPC
    monad_rpc_url: str = "https://rpc.monad.xyz"
    monad_ws_url: str = "wss://rpc.monad.xyz"
    monad_chain_id: int = 143

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: str = "monad"

    # Monadscan (Etherscan V2) API
    monadscan_api_key: str | None = None
    monadscan_api_url: str = "https://api.etherscan.io/v2/api"
    monadscan_chain_id: int = 143

    # Indexer
    indexer_batch_size: int = 10  # blocks per batch
    indexer_poll_interval: float = 0.5  # seconds between polls

    # LLM (optional)
    llm_provider: str | None = None
    gemini_api_key: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
