import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Search, Clock, ExternalLink, Copy, Check } from 'lucide-react';
import { getWallet, getWalletTransactions, getWalletRisk } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import RiskBadge from '../components/RiskBadge';
import AddressLink from '../components/AddressLink';
import { getCached, setCache, getRecentWithLabels } from '../stores/walletCache';
import type { WalletSummary, TransactionRecord, WalletRisk } from '../types';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Copy address'}
      style={{
        background: 'none',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '4px 6px',
        cursor: 'pointer',
        color: copied ? '#22c55e' : 'var(--text-muted)',
        display: 'inline-flex',
        alignItems: 'center',
        transition: 'color 0.15s, border-color 0.15s',
      }}
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function formatTimestamp(ts: number | null) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

function formatMON(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
  return value.toFixed(4);
}

const KNOWN_METHODS: Record<string, string> = {
  '0x84994fec': 'Delegate',
  '0xa9059cbb': 'Transfer',
  '0x095ea7b3': 'Approve',
  '0x23b872dd': 'TransferFrom',
  '0x573c1ce0': 'GetDelegator',
  '0x4fd66050': 'GetDelegations',
};

function formatMethod(method: string | null) {
  if (!method) return '—';
  return KNOWN_METHODS[method] || method;
}

function WalletDashboard({ address }: { address: string }) {
  const [tab, setTab] = useState<'summary' | 'transactions'>('summary');
  const [wallet, setWallet] = useState<WalletSummary | null>(null);
  const [risk, setRisk] = useState<WalletRisk | null>(null);
  const [txs, setTxs] = useState<TransactionRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    // Check cache first
    const cached = getCached(address);
    if (cached) {
      setWallet(cached.wallet);
      setRisk(cached.risk);
      setTxs(cached.transactions);
      setLoading(false);
      // Background refresh
      Promise.all([
        getWallet(address),
        getWalletRisk(address).catch(() => null),
        getWalletTransactions(address).catch(() => null),
      ]).then(([w, r, t]) => {
        if (!cancelled) {
          setWallet(w);
          setRisk(r);
          setTxs(t);
          setCache(address, w, r, t);
        }
      }).catch(() => {});
      return () => { cancelled = true; };
    }

    // No cache — full load
    setLoading(true);
    setError(null);
    Promise.all([
      getWallet(address),
      getWalletRisk(address).catch(() => null),
      getWalletTransactions(address).catch(() => null),
    ])
      .then(([w, r, t]) => {
        if (!cancelled) {
          setWallet(w);
          setRisk(r);
          setTxs(t);
          setCache(address, w, r, t);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Unknown error');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [address]);

  if (loading) return <Loading message="Fetching wallet data..." />;
  if (error) return <ErrorBox message={error} />;
  if (!wallet) return <ErrorBox message="Wallet not found" />;

  return (
    <div>
      {/* Address header */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>WALLET ADDRESS</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="address-full">{wallet.address}</span>
              <CopyButton text={wallet.address} />
            </div>
            {wallet.source === 'rpc' && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#f59e0b', display: 'flex', alignItems: 'center', gap: 6 }}>
                ⚡ Live data from Monad RPC — this wallet hasn't been indexed yet for full analytics
                <a
                  href={`https://monadscan.com/address/${wallet.address}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#818cf8', marginLeft: 8, display: 'inline-flex', alignItems: 'center', gap: 4 }}
                >
                  Monadscan <ExternalLink size={12} />
                </a>
              </div>
            )}
          </div>
          {wallet.source === 'indexed' && risk && <RiskBadge score={risk.risk_score} />}
        </div>
        {wallet.source === 'indexed' && risk && risk.flags.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {risk.flags.map((flag) => (
              <span key={flag} className="badge badge-high">{flag}</span>
            ))}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="stats-grid">
        {wallet.balance != null && (
          <div className="stat-card">
            <div className="label">Balance</div>
            <div className="value">{formatMON(wallet.balance)} MON</div>
          </div>
        )}
        <div className="stat-card">
          <div className="label">{wallet.source === 'rpc' ? 'Nonce (Total Sent)' : 'Total Transactions'}</div>
          <div className="value">{wallet.tx_count.toLocaleString()}</div>
        </div>
        {wallet.source === 'indexed' && (
          <>
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
          </>
        )}
      </div>

      {/* Staking info */}
      {wallet.staking && wallet.staking.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 12 }}>🥩 Staking Positions</div>
          {wallet.staking.map((s) => (
            <div key={s.validator_id} style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
              <div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Validator </span>
                <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>#{s.validator_id}</span>
              </div>
              <div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Staked: </span>
                <span style={{ fontWeight: 600, color: '#22c55e' }}>{formatMON(s.staked)} MON</span>
              </div>
              <div>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Rewards: </span>
                <span style={{ fontWeight: 600, color: '#f59e0b' }}>{s.rewards.toFixed(4)} MON</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Time range */}
      {wallet.source === 'indexed' && (
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
      )}

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
          {!txs || txs.length === 0 ? (
            <div className="empty-state">
              <h3>No Transactions Found</h3>
              {wallet.source === 'rpc' ? (
                <>
                  <p style={{ marginBottom: 12 }}>
                    Transaction history requires indexing. This wallet hasn't been indexed yet.
                  </p>
                  <a
                    href={`https://monadscan.com/address/${wallet.address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '8px 16px',
                      background: 'var(--accent)',
                      color: '#fff',
                      borderRadius: 8,
                      fontSize: 13,
                      fontWeight: 600,
                      textDecoration: 'none',
                    }}
                  >
                    View on Monadscan <ExternalLink size={14} />
                  </a>
                </>
              ) : (
                <p>No transactions found for this wallet</p>
              )}
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
                      <td>
                        <a
                          href={`https://monadscan.com/tx/${tx.hash}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="address"
                          style={{ color: 'var(--accent)', textDecoration: 'none' }}
                        >
                          {tx.hash.slice(0, 10)}…
                        </a>
                      </td>
                      <td>{tx.block_number.toLocaleString()}</td>
                      <td><AddressLink address={tx.from_addr} /></td>
                      <td><AddressLink address={tx.to_addr} /></td>
                      <td style={{ fontFamily: 'monospace' }}>{formatMON(tx.value)} MON</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        <span style={{ marginRight: 8 }}>{formatMethod(tx.method)}</span>
                        {formatTimestamp(tx.timestamp)}
                      </td>
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

function RecentSearches({ onSelect }: { onSelect: (addr: string) => void }) {
  const recent = getRecentWithLabels();
  if (recent.length === 0) return null;

  return (
    <div className="card" style={{ marginTop: 24 }}>
      <div className="card-title" style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Clock size={16} />
        Recent Searches
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {recent.map((r) => (
          <button
            key={r.address}
            onClick={() => onSelect(r.address)}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              cursor: 'pointer',
              color: 'var(--text)',
              textAlign: 'left',
              transition: 'border-color 0.15s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
          >
            <span className="address" style={{ fontSize: 13 }}>
              {r.address.slice(0, 10)}…{r.address.slice(-8)}
            </span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {r.labels.map((l) => (
                <span key={l} className="badge badge-info" style={{ fontSize: 11 }}>{l}</span>
              ))}
              {r.balance != null && (
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
                  {formatMON(r.balance)} MON
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default function WalletLookup() {
  const { address } = useParams<{ address?: string }>();
  const navigate = useNavigate();
  const [searchAddr, setSearchAddr] = useState(address || '');

  // Sync input when URL param changes
  useEffect(() => {
    if (address) setSearchAddr(address);
  }, [address]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const addr = searchAddr.trim();
    if (addr) navigate(`/wallet/${addr}`);
  };

  const handleSelectRecent = (addr: string) => {
    setSearchAddr(addr);
    navigate(`/wallet/${addr}`);
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
        <div>
          <div className="empty-state">
            <div className="icon">🔎</div>
            <h3>Search for a wallet</h3>
            <p>Enter a Monad wallet address above to see its analytics</p>
          </div>
          <RecentSearches onSelect={handleSelectRecent} />
        </div>
      )}
    </div>
  );
}
