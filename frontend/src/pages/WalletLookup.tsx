import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Search, Clock, ExternalLink, ShieldAlert, TrendingUp, TrendingDown, Activity, CalendarRange, Scan, Lock } from 'lucide-react';
import { getWallet, getWalletTransactions, getWalletRisk, scanWallet } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import RiskBadge from '../components/RiskBadge';
import AddressLink from '../components/AddressLink';
import CopyButton from '../components/CopyButton';
import FavouriteButton from '../components/FavouriteButton';
import { getCached, setCache, getRecentWithLabels } from '../stores/walletCache';
import { formatTimestamp, formatMON, formatMethod } from '../utils/format';
import { computeTxSummary, analyzeRisk } from '../utils/riskAnalysis';
import type { WalletSummary, TransactionRecord, WalletRisk } from '../types';

function IndexedPeriodCard({ wallet, onRefresh }: { wallet: WalletSummary; onRefresh: () => void }) {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Initialize dates once on mount
  useEffect(() => {
    if (initialized) return;
    if (wallet.first_seen) {
      setStartDate(new Date(wallet.first_seen * 1000).toISOString().slice(0, 16));
    }
    if (wallet.last_seen) {
      setEndDate(new Date(wallet.last_seen * 1000).toISOString().slice(0, 16));
    }
    if (wallet.first_seen || wallet.last_seen) setInitialized(true);
  }, [wallet.first_seen, wallet.last_seen, initialized]);

  const hasIndexedData = wallet.source === 'indexed' && wallet.first_seen && wallet.last_seen;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CalendarRange size={16} color="#818cf8" />
          <span style={{ fontWeight: 600, fontSize: 14 }}>Indexed Period</span>
          {hasIndexedData && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              · {wallet.tx_count} transactions indexed
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 180 }}>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>FROM</label>
          <input
            type="datetime-local"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            onClick={(e) => (e.target as HTMLInputElement).showPicker?.()}
            style={{
              width: '100%', padding: '8px 10px', background: 'var(--bg-input)',
              border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
              fontSize: 13, outline: 'none', cursor: 'pointer',
              colorScheme: 'dark',
            }}
          />
        </div>
        <div style={{ flex: 1, minWidth: 180 }}>
          <label style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>TO</label>
          <input
            type="datetime-local"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            onClick={(e) => (e.target as HTMLInputElement).showPicker?.()}
            style={{
              width: '100%', padding: '8px 10px', background: 'var(--bg-input)',
              border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
              fontSize: 13, outline: 'none', cursor: 'pointer',
              colorScheme: 'dark',
            }}
          />
        </div>
        <button
          onClick={async () => {
            setScanning(true);
            setScanResult(null);
            try {
              const startTs = startDate ? Math.floor(new Date(startDate).getTime() / 1000) : undefined;
              const endTs = endDate ? Math.floor(new Date(endDate).getTime() / 1000) : undefined;
              const result = await scanWallet(wallet.address, startTs, endTs);
              setScanResult(`Indexed ${result.indexed} transactions`);
              // Update dates from refreshed wallet data
              if (result.wallet?.first_seen) {
                setStartDate(new Date(result.wallet.first_seen * 1000).toISOString().slice(0, 16));
              }
              if (result.wallet?.last_seen) {
                setEndDate(new Date(result.wallet.last_seen * 1000).toISOString().slice(0, 16));
              }
              onRefresh();
            } catch (err) {
              setScanResult(`Scan failed: ${(err as Error).message}`);
            } finally {
              setScanning(false);
            }
          }}
          disabled={scanning}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px',
            background: scanning ? 'var(--bg-secondary)' : 'rgba(99,102,241,0.15)',
            border: '1px solid rgba(99,102,241,0.3)', borderRadius: 6,
            cursor: scanning ? 'not-allowed' : 'pointer',
            color: '#818cf8', fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap',
          }}
        >
          {scanning ? (
            <><Scan size={14} className="spin" /> Scanning...</>
          ) : (
            <><Scan size={14} /> Scan Period</>
          )}
        </button>
      </div>

      {scanResult && (
        <div style={{ marginTop: 10, fontSize: 12, color: '#22c55e' }}>
          ✅ {scanResult}
        </div>
      )}

      {!hasIndexedData && !scanResult && (
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-muted)' }}>
          No indexed data yet. Click Scan to index transactions for this wallet.
        </div>
      )}

      <div style={{
        marginTop: 10, padding: '6px 10px', borderRadius: 6,
        background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)',
        display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#d97706',
      }}>
        <Lock size={12} /> Custom date range scanning will be a Pro feature
      </div>
    </div>
  );
}

function WalletDashboard({ address }: { address: string }) {
  const [tab, setTab] = useState<'transactions' | 'summary' | 'risk'>('transactions');
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

  const refreshWallet = () => {
    Promise.all([
      getWallet(address),
      getWalletRisk(address).catch(() => null),
      getWalletTransactions(address).catch(() => null),
    ]).then(([w, r, t]) => {
      setWallet(w);
      setRisk(r);
      setTxs(t);
      setCache(address, w, r, t);
    }).catch(() => {});
  };

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
              <FavouriteButton address={wallet.address} />
            </div>
            {wallet.source === 'indexed' && wallet.first_seen && wallet.last_seen && (
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                📊 Indexed period: {formatTimestamp(wallet.first_seen)} → {formatTimestamp(wallet.last_seen)} · {wallet.tx_count} txs
              </div>
            )}
            {wallet.source === 'not_indexed' && (
              <div style={{ marginTop: 6, fontSize: 12, color: '#f59e0b', display: 'flex', alignItems: 'center', gap: 6 }}>
                ⚠️ This wallet hasn't been indexed yet. Use Scan Period below to index transactions.
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
          <div className="label">Total Transactions</div>
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

      {/* Indexed Period */}
      <IndexedPeriodCard wallet={wallet} onRefresh={refreshWallet} />

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



      {/* Tabs */}
      <div className="tabs">
        <button className={`tab ${tab === 'transactions' ? 'active' : ''}`} onClick={() => setTab('transactions')}>
          Transactions ({txs?.length ?? 0})
        </button>
        <button className={`tab ${tab === 'summary' ? 'active' : ''}`} onClick={() => setTab('summary')}>
          Summary
        </button>
        <button className={`tab ${tab === 'risk' ? 'active' : ''}`} onClick={() => setTab('risk')}>
          <ShieldAlert size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
          Risk Profile
        </button>
      </div>

      {tab === 'transactions' && (
        <div className="card">
          {!txs || txs.length === 0 ? (
            <div className="empty-state">
              <h3>No Transactions Found</h3>
              {wallet.source === 'not_indexed' ? (
                <>
                  <p style={{ marginBottom: 12 }}>
                    Use Scan Period above to index this wallet's transactions.
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

      {tab === 'summary' && (
        <div className="card">
          {/* Labels */}
          <div style={{ marginBottom: 20 }}>
            <div className="card-title" style={{ marginBottom: 12 }}>Labels</div>
            {wallet.labels.length > 0 ? (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {wallet.labels.map((l) => <span key={l} className="badge badge-info">{l}</span>)}
              </div>
            ) : (
              <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>No labels assigned</span>
            )}
          </div>

          {/* Transaction Summary Table */}
          {txs && txs.length > 0 && (() => {
            const summary = computeTxSummary(txs, address);
            return (
              <div>
                <div className="card-title" style={{ marginBottom: 12 }}>Transaction Activity</div>
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Period</th>
                        <th style={{ textAlign: 'right' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <TrendingDown size={13} color="#22c55e" /> Inbound
                          </span>
                        </th>
                        <th style={{ textAlign: 'right' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <TrendingUp size={13} color="#ef4444" /> Outbound
                          </span>
                        </th>
                        <th style={{ textAlign: 'right' }}>Net Flow</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.map((p) => {
                        const net = p.inValue - p.outValue;
                        return (
                          <tr key={p.label}>
                            <td style={{ fontWeight: 500 }}>{p.label}</td>
                            <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                              {p.inCount > 0 ? (
                                <span style={{ color: '#22c55e' }}>
                                  {p.inCount} tx · {formatMON(p.inValue)} MON
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-muted)' }}>—</span>
                              )}
                            </td>
                            <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                              {p.outCount > 0 ? (
                                <span style={{ color: '#ef4444' }}>
                                  {p.outCount} tx · {formatMON(p.outValue)} MON
                                </span>
                              ) : (
                                <span style={{ color: 'var(--text-muted)' }}>—</span>
                              )}
                            </td>
                            <td style={{ textAlign: 'right', fontFamily: 'monospace', fontWeight: 600, color: net >= 0 ? '#22c55e' : '#ef4444' }}>
                              {net >= 0 ? '+' : ''}{formatMON(net)} MON
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {(!txs || txs.length === 0) && (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No transaction data available for summary.</div>
          )}
        </div>
      )}

      {tab === 'risk' && (() => {
        const riskAnalysis = analyzeRisk(txs || [], address, risk);
        return (
          <div className="card">
            {/* Score header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 24, marginBottom: 24, flexWrap: 'wrap' }}>
              <div style={{
                width: 80, height: 80, borderRadius: '50%',
                border: `4px solid ${riskAnalysis.color}`,
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              }}>
                <span style={{ fontSize: 28, fontWeight: 700, color: riskAnalysis.color, lineHeight: 1 }}>
                  {riskAnalysis.score}
                </span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>/10</span>
              </div>
              <div>
                <div style={{ fontSize: 20, fontWeight: 700, textTransform: 'uppercase', color: riskAnalysis.color }}>
                  {riskAnalysis.level === 'clean' ? '✅ Clean' : `⚠️ ${riskAnalysis.level} risk`}
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
                  Based on {txs?.length ?? 0} transactions
                  {risk && risk.flags.length > 0 ? ' + graph analysis' : ''}
                </div>
              </div>
            </div>

            {/* Risk factors */}
            <div className="card-title" style={{ marginBottom: 12 }}>
              <Activity size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Risk Factors
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {riskAnalysis.factors.map((f, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 14px', background: 'var(--bg-secondary)', borderRadius: 8,
                  borderLeft: `3px solid ${f.weight === 0 ? '#22c55e' : f.weight >= 2 ? '#ef4444' : f.weight >= 1 ? '#f59e0b' : '#3b82f6'}`,
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{f.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{f.detail}</div>
                  </div>
                  {f.weight > 0 && (
                    <span style={{
                      fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 12,
                      background: f.weight >= 2 ? 'rgba(239,68,68,0.15)' : 'rgba(245,158,11,0.15)',
                      color: f.weight >= 2 ? '#ef4444' : '#f59e0b',
                    }}>
                      +{f.weight.toFixed(1)}
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* Methodology note */}
            <div style={{ marginTop: 20, padding: 12, background: 'var(--bg-secondary)', borderRadius: 8, fontSize: 12, color: 'var(--text-muted)' }}>
              <strong>Methodology:</strong> Score combines on-chain transaction patterns
              (round-trips, self-transfers, velocity, value symmetry, counterparty diversity)
              {wallet.source === 'indexed' ? ' and Neo4j graph analysis (circular flows, fan-out, fan-in)' : ''}.
              Scale: 0 = clean, 10 = maximum risk.
            </div>
          </div>
        );
      })()}
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
