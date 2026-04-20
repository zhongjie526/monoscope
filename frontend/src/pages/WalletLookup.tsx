import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { getWallet, getWalletTransactions, getWalletRisk } from '../services/api';
import { useApi } from '../hooks/useApi';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import RiskBadge from '../components/RiskBadge';
import AddressLink from '../components/AddressLink';
import type { WalletSummary, TransactionRecord, WalletRisk } from '../types';

function formatTimestamp(ts: number | null) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

function formatMON(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
  return value.toFixed(4);
}

function WalletDashboard({ address }: { address: string }) {
  const [tab, setTab] = useState<'summary' | 'transactions'>('summary');
  const { data: wallet, loading: wLoading, error: wError } = useApi<WalletSummary>(
    () => getWallet(address), [address]
  );
  const { data: risk, loading: rLoading } = useApi<WalletRisk>(
    () => getWalletRisk(address), [address]
  );
  const { data: txs, loading: tLoading } = useApi<TransactionRecord[]>(
    () => getWalletTransactions(address), [address]
  );

  if (wLoading || rLoading) return <Loading message="Fetching wallet data..." />;
  if (wError) return <ErrorBox message={wError} />;
  if (!wallet) return <ErrorBox message="Wallet not found" />;

  return (
    <div>
      {/* Address header */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>WALLET ADDRESS</div>
            <div className="address-full">{wallet.address}</div>
          </div>
          {risk && <RiskBadge score={risk.risk_score} />}
        </div>
        {risk && risk.flags.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {risk.flags.map((flag) => (
              <span key={flag} className="badge badge-high">{flag}</span>
            ))}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Total Transactions</div>
          <div className="value">{wallet.tx_count}</div>
        </div>
        <div className="stat-card">
          <div className="label">Total Sent</div>
          <div className="value">{formatMON(wallet.total_sent)} MON</div>
        </div>
        <div className="stat-card">
          <div className="label">Total Received</div>
          <div className="value">{formatMON(wallet.total_received)} MON</div>
        </div>
        <div className="stat-card">
          <div className="label">Unique Interactions</div>
          <div className="value">{wallet.unique_interactions}</div>
        </div>
      </div>

      {/* Time range */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
          <div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>First Seen: </span>
            <span style={{ fontSize: 13 }}>{formatTimestamp(wallet.first_seen)}</span>
          </div>
          <div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Last Seen: </span>
            <span style={{ fontSize: 13 }}>{formatTimestamp(wallet.last_seen)}</span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        <button className={`tab ${tab === 'summary' ? 'active' : ''}`} onClick={() => setTab('summary')}>
          Summary
        </button>
        <button className={`tab ${tab === 'transactions' ? 'active' : ''}`} onClick={() => setTab('transactions')}>
          Transactions ({txs?.length ?? 0})
        </button>
      </div>

      {tab === 'summary' && (
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}>Labels</div>
          {wallet.labels.length > 0 ? (
            <div style={{ display: 'flex', gap: 8 }}>
              {wallet.labels.map((l) => <span key={l} className="badge badge-info">{l}</span>)}
            </div>
          ) : (
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>No labels assigned</span>
          )}
        </div>
      )}

      {tab === 'transactions' && (
        <div className="card">
          {tLoading ? (
            <Loading message="Loading transactions..." />
          ) : !txs || txs.length === 0 ? (
            <div className="empty-state">
              <h3>No Transactions</h3>
              <p>No transactions found for this wallet</p>
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Hash</th>
                    <th>Block</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Value</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {txs.map((tx) => (
                    <tr key={tx.hash}>
                      <td className="address">{tx.hash.slice(0, 10)}…</td>
                      <td>{tx.block_number.toLocaleString()}</td>
                      <td><AddressLink address={tx.from_addr} /></td>
                      <td><AddressLink address={tx.to_addr} /></td>
                      <td style={{ fontFamily: 'monospace' }}>{formatMON(tx.value)} MON</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{formatTimestamp(tx.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function WalletLookup() {
  const { address } = useParams<{ address?: string }>();
  const navigate = useNavigate();
  const [searchAddr, setSearchAddr] = useState(address || '');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const addr = searchAddr.trim();
    if (addr) navigate(`/wallet/${addr}`);
  };

  return (
    <div>
      <div className="page-header">
        <h2>🔍 Wallet Lookup</h2>
        <p>Investigate any Monad wallet address</p>
      </div>

      <form onSubmit={handleSearch}>
        <div className="search-container">
          <Search size={18} className="search-icon" />
          <input
            className="search-input"
            type="text"
            placeholder="Enter wallet address (0x...)..."
            value={searchAddr}
            onChange={(e) => setSearchAddr(e.target.value)}
          />
        </div>
      </form>

      {address ? (
        <WalletDashboard address={address} />
      ) : (
        <div className="empty-state">
          <div className="icon">🔎</div>
          <h3>Search for a wallet</h3>
          <p>Enter a Monad wallet address above to see its analytics</p>
        </div>
      )}
    </div>
  );
}
