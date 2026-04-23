import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getWashTrading, getSybilClusters, getHighVelocity, getFundCycling, getBridgeWallets, getRapidCashout, getSybilExpansion, getSharedTargets } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import SeverityBadge from '../components/SeverityBadge';
import AddressLink from '../components/AddressLink';
import type { FraudAlert } from '../types';

type FilterType = 'all' | 'wash_trading' | 'sybil_cluster' | 'high_velocity' | 'fund_cycling' | 'bridge_wallet' | 'rapid_cashout' | 'sybil_expansion' | 'shared_target';

const PATTERN_LABELS: Record<string, { label: string; icon: string; desc: string }> = {
  wash_trading: { label: 'Wash Trading', icon: '🔄', desc: 'Bidirectional fund flows between wallets' },
  sybil_cluster: { label: 'Sybil Cluster', icon: '🕸️', desc: 'Single funder distributing to many wallets' },
  high_velocity: { label: 'High Velocity', icon: '⚡', desc: 'Bot-like transaction frequency' },
  fund_cycling: { label: 'Fund Cycling', icon: '💸', desc: 'Rapid receive→forward relay pattern' },
  bridge_wallet: { label: 'Bridge Wallet', icon: '🌉', desc: 'Intermediary connecting separate clusters' },
  rapid_cashout: { label: 'Rapid Cash-Out', icon: '🚨', desc: 'Large inflow drained quickly' },
  sybil_expansion: { label: 'Sybil Expansion', icon: '🔍', desc: 'Accomplices 1-hop from sybil clusters' },
  shared_target: { label: 'Shared Target', icon: '🎯', desc: 'Wallet receiving from many unique senders' },
};

export default function FraudAlerts() {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<FraudAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');

  useEffect(() => {
    async function load() {
      try {
        const [wash, sybil, velocity, cycling, bridge, cashout, sybilExp, shared] = await Promise.all([
          getWashTrading(),
          getSybilClusters(),
          getHighVelocity(),
          getFundCycling().catch(() => []),
          getBridgeWallets().catch(() => []),
          getRapidCashout().catch(() => []),
          getSybilExpansion().catch(() => []),
          getSharedTargets().catch(() => []),
        ]);
        const all = [...wash, ...sybil, ...velocity, ...cycling, ...bridge, ...cashout, ...sybilExp, ...shared];
        const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
        all.sort((a, b) => (severityOrder[a.severity] ?? 4) - (severityOrder[b.severity] ?? 4));
        setAlerts(all);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = filter === 'all' ? alerts : alerts.filter((a) => a.pattern === filter);

  const counts: Record<string, number> = {
    all: alerts.length,
    ...Object.fromEntries(
      Object.keys(PATTERN_LABELS).map((k) => [k, alerts.filter((a) => a.pattern === k).length])
    ),
  };

  if (loading) return <Loading message="Running fraud detection..." />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div>
      <div className="page-header">
        <h2>🛡️ Fraud Detection</h2>
        <p>Graph-based pattern analysis across tracked wallets</p>
      </div>

      {/* Summary cards */}
      <div className="stats-grid">
        {Object.entries(PATTERN_LABELS).map(([key, { label, icon, desc }]) => (
          <div
            key={key}
            className="stat-card"
            style={{ cursor: 'pointer', borderColor: filter === key ? 'var(--accent)' : undefined }}
            onClick={() => setFilter(key as FilterType)}
          >
            <div className="label">{icon} {label}</div>
            <div className="value">{counts[key as keyof typeof counts]}</div>
            <div className="sub">{desc}</div>
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="tabs" style={{ flexWrap: 'wrap' }}>
        <button
          className={`tab ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All ({counts.all})
        </button>
        {Object.entries(PATTERN_LABELS).map(([key, { label }]) => {
          const count = counts[key] || 0;
          if (count === 0) return null;
          return (
            <button
              key={key}
              className={`tab ${filter === key ? 'active' : ''}`}
              onClick={() => setFilter(key as FilterType)}
            >
              {label} ({count})
            </button>
          );
        })}
      </div>

      {/* Alerts list */}
      {filtered.length === 0 ? (
        <div className="empty-state">
          <div className="icon">✅</div>
          <h3>No Alerts</h3>
          <p>No fraud patterns detected in this category</p>
        </div>
      ) : (
        filtered.map((alert, i) => {
          const meta = PATTERN_LABELS[alert.pattern];
          return (
            <div key={i} className="alert-card">
              <div className="alert-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>{meta?.icon}</span>
                  <span className="alert-pattern">{meta?.label || alert.pattern}</span>
                </div>
                <SeverityBadge severity={alert.severity} />
              </div>
              <div className="alert-desc">{alert.description}</div>
              <div className="alert-wallets">
                {alert.wallets.slice(0, 6).map((w) => (
                  <AddressLink key={w} address={w} truncate={false} />
                ))}
                {alert.wallets.length > 6 && (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    +{alert.wallets.length - 6} more
                  </span>
                )}
              </div>
              <div style={{ marginTop: 10 }}>
                <button
                  className="btn btn-primary"
                  onClick={() => navigate(`/graph?address=${alert.wallets[0]}`)}
                  style={{ fontSize: 12, padding: '6px 14px' }}
                >
                  🔍 Investigate
                </button>
              </div>
              {alert.evidence && (
                <details style={{ marginTop: 8 }}>
                  <summary style={{ fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
                    Evidence Details
                  </summary>
                  <pre style={{
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    background: 'var(--bg-input)',
                    padding: 8,
                    borderRadius: 6,
                    marginTop: 6,
                    overflow: 'auto',
                  }}>
                    {JSON.stringify(alert.evidence, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
