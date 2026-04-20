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

// Wallet
export const getWallet = (address: string) =>
  fetchJson<WalletSummary>(`/api/wallet/${address.toLowerCase()}`);

export const getWalletTransactions = (address: string, limit = 50) =>
  fetchJson<TransactionRecord[]>(`/api/wallet/${address.toLowerCase()}/transactions?limit=${limit}`);

export const getWalletGraph = (address: string, depth = 2, limit = 100) =>
  fetchJson<GraphData>(`/api/wallet/${address.toLowerCase()}/graph?depth=${depth}&limit=${limit}`);

// Fraud
export const getWashTrading = (minRoundTrips = 2) =>
  fetchJson<FraudAlert[]>(`/api/fraud/wash-trading?min_round_trips=${minRoundTrips}`);

export const getSybilClusters = (minClusterSize = 5) =>
  fetchJson<FraudAlert[]>(`/api/fraud/sybil-clusters?min_cluster_size=${minClusterSize}`);

export const getHighVelocity = (minTxsPerHour = 60) =>
  fetchJson<FraudAlert[]>(`/api/fraud/high-velocity?min_txs_per_hour=${minTxsPerHour}`);

export const getWalletRisk = (address: string) =>
  fetchJson<WalletRisk>(`/api/fraud/risk/${address.toLowerCase()}`);

// Search
export const searchQuery = (question: string) =>
  fetchJson<SearchResult>('/api/search/', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
