const API_BASE = import.meta.env.VITE_API_URL || '';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`API ${resp.status}: ${text}`);
  }
  return resp.json();
}

// Types
import type {
  WalletSummary,
  TransactionRecord,
  FraudAlert,
  WalletRisk,
  GraphData,
  SearchResult,
  HealthStatus,
} from '../types';

// Health
export const getHealth = () => fetchJson<HealthStatus>('/health');

// Status
export interface SystemStatus {
  indexer: {
    start_block: number | null;
    last_block: number | null;
    start_time: number | null;
    last_time: number | null;
  };
  wallet_count: number;
  tx_count: number;
}

export const getStatus = () => fetchJson<SystemStatus>('/api/status');

// Wallet
export const getWallet = (address: string) =>
  fetchJson<WalletSummary>(`/api/wallet/${address.toLowerCase()}`);

export const getWalletTransactions = (address: string, limit = 50) =>
  fetchJson<TransactionRecord[]>(`/api/wallet/${address.toLowerCase()}/transactions?limit=${limit}`);

export const scanWallet = (address: string, startTs?: number, endTs?: number) =>
  fetchJson<{ indexed: number; wallet: WalletSummary | null }>(`/api/wallet/${address.toLowerCase()}/scan`, {
    method: 'POST',
    body: JSON.stringify({
      ...(startTs ? { start_ts: startTs } : {}),
      ...(endTs ? { end_ts: endTs } : {}),
    }),
  });

export const getWalletGraph = (address: string, depth = 2, limit = 100) =>
  fetchJson<GraphData>(`/api/wallet/${address.toLowerCase()}/graph?depth=${depth}&limit=${limit}`);

export interface BatchWalletStats {
  address: string;
  balance: number | null;
  tx_count: number | null;
  total_sent: number | null;
  total_received: number | null;
  staked: number | null;
  staking_rewards: number | null;
  labels: string[];
  has_data: boolean;
}

export const getBatchWalletStats = (addresses: string[]) =>
  fetchJson<BatchWalletStats[]>('/api/wallet/batch-stats', {
    method: 'POST',
    body: JSON.stringify(addresses),
  });

// Fraud
export const getWashTrading = (minRoundTrips = 2) =>
  fetchJson<FraudAlert[]>(`/api/fraud/wash-trading?min_round_trips=${minRoundTrips}`);

export const getSybilClusters = (minClusterSize = 5) =>
  fetchJson<FraudAlert[]>(`/api/fraud/sybil-clusters?min_cluster_size=${minClusterSize}`);

export const getHighVelocity = (minTxsPerHour = 60) =>
  fetchJson<FraudAlert[]>(`/api/fraud/high-velocity?min_txs_per_hour=${minTxsPerHour}`);

export const getWalletRisk = (address: string) =>
  fetchJson<WalletRisk>(`/api/fraud/risk/${address.toLowerCase()}`);

// Advanced Fraud
export const getFundCycling = (windowSecs = 60, minValue = 1000) =>
  fetchJson<FraudAlert[]>(`/api/fraud/fund-cycling?window_seconds=${windowSecs}&min_value=${minValue}`);

export const getBridgeWallets = (minSources = 5, minTargets = 5) =>
  fetchJson<FraudAlert[]>(`/api/fraud/bridge-wallets?min_unique_sources=${minSources}&min_unique_targets=${minTargets}`);

export const getRapidCashout = (windowBlocks = 50, drainPct = 0.9) =>
  fetchJson<FraudAlert[]>(`/api/fraud/rapid-cashout?window_blocks=${windowBlocks}&drain_pct=${drainPct}`);

export const getSybilExpansion = (minClusterSize = 5) =>
  fetchJson<FraudAlert[]>(`/api/fraud/sybil-expansion?min_cluster_size=${minClusterSize}`);

export const getSharedTargets = (minSenders = 5) =>
  fetchJson<FraudAlert[]>(`/api/fraud/shared-targets?min_senders=${minSenders}`);

export const getRiskScores = (limit = 50) =>
  fetchJson<Record<string, unknown>[]>(`/api/fraud/risk-scores?limit=${limit}`);

// Search
export const searchQuery = (question: string) =>
  fetchJson<SearchResult>('/api/search/', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
