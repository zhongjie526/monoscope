import type { WalletSummary, TransactionRecord, WalletRisk } from '../types';

interface CachedWallet {
  wallet: WalletSummary;
  risk: WalletRisk | null;
  transactions: TransactionRecord[] | null;
  timestamp: number;
}

const MAX_RECENT = 10;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

// Module-level — survives component unmounts, cleared on page refresh
const cache = new Map<string, CachedWallet>();
let recentAddresses: string[] = [];

export function getCached(address: string): CachedWallet | null {
  const key = address.toLowerCase();
  const entry = cache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
    cache.delete(key);
    return null;
  }
  return entry;
}

export function setCache(
  address: string,
  wallet: WalletSummary,
  risk: WalletRisk | null,
  transactions: TransactionRecord[] | null
) {
  const key = address.toLowerCase();
  cache.set(key, { wallet, risk, transactions, timestamp: Date.now() });
  // Update recent list
  recentAddresses = [key, ...recentAddresses.filter((a) => a !== key)].slice(0, MAX_RECENT);
}

export function getRecentAddresses(): string[] {
  return recentAddresses;
}

export function getRecentWithLabels(): Array<{ address: string; labels: string[]; balance: number | null }> {
  return recentAddresses
    .map((addr) => {
      const entry = cache.get(addr);
      if (!entry) return null;
      return {
        address: entry.wallet.address, // preserve original case
        labels: entry.wallet.labels,
        balance: entry.wallet.balance,
      };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);
}
