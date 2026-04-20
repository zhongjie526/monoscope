import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { searchQuery, getWashTrading, getSybilClusters, getHighVelocity } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import SeverityBadge from '../components/SeverityBadge';
import AddressLink from '../components/AddressLink';
import type { Stats, FraudAlert } from '../types';

export default function Overview() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<FraudAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchAddr, setSearchAddr] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [statsRes, wash, sybil, velocity] = await Promise.all([
          searchQuery('stats'),
          getWashTrading(),
          getSybilClusters(),
          getHighVelocity(),
        ]);
        if (statsRes.data && statsRes.data.length > 0) {
          setStats(statsRes.data[0] as unknown as Stats);
        }
        // Combine and sort by severity
        const allAlerts = [...wash, ...sybil, ...velocity];
        const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
        allAlerts.sort((a, b) => (severityOrder[a.severity] ?? 4) - (severityOrder[b.severity] ?? 4));
        setRecentAlerts(allAlerts.slice(0, 10));
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const addr = searchAddr.trim();
    if (addr) navigate(`/wallet/${addr}`);
  };

  if (loading) return <Loading message="Loading overview..." />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div>
      <div className="page-header">
        <h2>🐕 Monad Watchdog</h2>
        <p>AI-powered fraud detection and wallet analytics for Monad</p>
      </div>

      {/* Quick Search */}
      <form onSubmit={handleSearch}>
        <div className="search-container">
          <Search size={18} className="search-icon" />
          <input
            className="search-input"
            type="text"
            placeholder="Paste a wallet address to investigate..."
            value={searchAddr}
            onChange={(e) => setSearchAddr(e.target.value)}
          />
        </div>
      </form>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Wallets Indexed</div>
          <div className="value">{stats?.wallet_count?.toLocaleString() ?? '—'}</div>
          <div className="sub">Unique addresses tracked</div>
        </div>
        <div className="stat-card">
          <div className="label">Transactions</div>
          <div className="value">{stats?.tx_count?.toLocaleString() ?? '—'}</div>
          <div className="sub">Total indexed transfers</div>
        </div>
        <div className="stat-card">
          <div className="label">Fraud Alerts</div>
          <div className="value" style={{ color: recentAlerts.length > 0 ? 'var(--orange)' : 'var(--green)' }}>
            {recentAlerts.length}
          </div>
          <div className="sub">Active detections</div>
        </div>
        <div className="stat-card">
          <div className="label">Chain</div>
          <div className="value" style={{ fontSize: 20 }}>Monad</div>
          <div className="sub">Chain ID 143 • Mainnet</div>
        </div>
      </div>

      {/* Recent Alerts */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">🚨 Recent Fraud Alerts</span>
          <button className="btn btn-ghost" onClick={() => navigate('/fraud')}>View All</button>
        </div>
        {recentAlerts.length === 0 ? (
          <div className="empty-state">
            <div className="icon">✅</div>
            <h3>All Clear</h3>
            <p>No fraud patterns detected in indexed data</p>
          </div>
        ) : (
          <div>
            {recentAlerts.map((alert, i) => (
              <div key={i} className="alert-card">
                <div className="alert-header">
                  <span className="alert-pattern">
                    {alert.pattern.replace('_', ' ')}
                  </span>
                  <SeverityBadge severity={alert.severity} />
                </div>
                <div className="alert-desc">{alert.description}</div>
                <div className="alert-wallets">
                  {alert.wallets.slice(0, 4).map((w) => (
                    <AddressLink key={w} address={w} />
                  ))}
                  {alert.wallets.length > 4 && (
                    <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      +{alert.wallets.length - 4} more
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
