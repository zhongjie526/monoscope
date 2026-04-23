// API response types matching the FastAPI backend

export interface StakingInfo {
  validator_id: number;
  staked: number;
  rewards: number;
}

export interface WalletSummary {
  address: string;
  balance: number | null;
  tx_count: number;
  total_sent: number;
  total_received: number;
  unique_interactions: number;
  first_seen: number | null;
  last_seen: number | null;
  risk_score: number | null;
  labels: string[];
  source: 'indexed' | 'rpc' | 'not_indexed';
  staking: StakingInfo[];
}

export interface TransactionRecord {
  hash: string;
  block_number: number;
  timestamp: number;
  from_addr: string;
  to_addr: string;
  value: number;
  method: string | null;
}

export interface FraudAlert {
  pattern: string;
  severity: string;
  wallets: string[];
  description: string;
  evidence: Record<string, unknown> | null;
}

export interface WalletRisk {
  address: string;
  risk_score: number;
  flags: string[];
  details: string;
}

export interface GraphData {
  nodes: {
    address: string;
    balance?: number;
    tx_count?: number;
    total_sent?: number;
    total_received?: number;
    staked?: number;
    staking_rewards?: number;
  }[];
  edges: {
    from: string;
    to: string;
    tx_hash: string;
    value: number;
    timestamp: number;
  }[];
}

export interface SearchResult {
  answer: string;
  data: Record<string, unknown>[] | null;
  query_used: string | null;
  source?: 'template' | 'ai';
}

export interface HealthStatus {
  status: string;
  neo4j: boolean;
}

export interface Stats {
  wallet_count: number;
  tx_count: number;
  first_tx: number | null;
  last_tx: number | null;
}
