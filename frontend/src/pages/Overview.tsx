import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStatus, getWashTrading, getSybilClusters, getHighVelocity } from '../services/api';
import type { SystemStatus } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import SeverityBadge from '../components/SeverityBadge';
import AddressLink from '../components/AddressLink';
import type { FraudAlert } from '../types';

function formatDate(ts: number | null): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleDateString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  });
}

export default function Overview() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [recentAlerts, setRecentAlerts] = useState<FraudAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    async function load() {
      try {
        const [statusRes, wash, sybil, velocity] = await Promise.all([
          getStatus(),
          getWashTrading(),
          getSybilClusters(),
          getHighVelocity(),
        ]);
        setStatus(statusRes);
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

  if (loading) return <Loading message="Loading..." />;
  if (error) return <ErrorBox message={error} />;

  const idx = status?.indexer;

  return (
    <div>
      {/* Header */}
      <div style={{ textAlign: 'center', padding: '32px 0 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginBottom: 6 }}>
          <img src="/logo.svg" alt="Monoscope" style={{ width: 36, height: 36 }} />
          <h2 style={{ fontFamily: 'Outfit, sans-serif', fontSize: 28, fontWeight: 600, letterSpacing: '3px', textTransform: 'uppercase' }}>Monoscope</h2>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: 15 }}>
          On-chain intelligence for Monad
        </p>
      </div>

      {/* Tracking period */}
      {idx && idx.start_time && idx.last_time && (
        <div style={{
          marginBottom: 16, padding: '10px 16px', borderRadius: 8,
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          fontSize: 13, color: 'var(--text-muted)', display: 'flex',
          alignItems: 'center', gap: 8, flexWrap: 'wrap',
        }}>
          📅 Tracking period: {formatDate(idx.start_time)} — {formatDate(idx.last_time)}
          {idx.start_block && idx.last_block && (
            <span style={{ marginLeft: 8, opacity: 0.6, fontSize: 12 }}>
              · Blocks {idx.start_block.toLocaleString()} – {idx.last_block.toLocaleString()}
            </span>
          )}
        </div>
      )}

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Wallets Tracked</div>
          <div className="value">{status?.wallet_count?.toLocaleString() ?? '—'}</div>
          <div className="sub">Unique addresses</div>
        </div>
        <div className="stat-card">
          <div className="label">Transactions</div>
          <div className="value">{status?.tx_count?.toLocaleString() ?? '—'}</div>
          <div className="sub">Total transfers</div>
        </div>
        <div className="stat-card">
          <div className="label">Fraud Detection</div>
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
          <span className="card-title">🚨 Recent Detections</span>
          <button className="btn btn-ghost" onClick={() => navigate('/fraud')}>View All</button>
        </div>
        {recentAlerts.length === 0 ? (
          <div className="empty-state">
            <div className="icon">✅</div>
            <h3>All Clear</h3>
            <p>No fraud patterns detected</p>
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
