import { useState, useEffect } from 'react';
import { getWashTrading, getSybilClusters, getHighVelocity } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import SeverityBadge from '../components/SeverityBadge';
import AddressLink from '../components/AddressLink';
import type { FraudAlert } from '../types';

type FilterType = 'all' | 'wash_trading' | 'sybil_cluster' | 'high_velocity';

const PATTERN_LABELS: Record<string, { label: string; icon: string; desc: string }> = {
  wash_trading: { label: 'Wash Trading', icon: '🔄', desc: 'Bidirectional fund flows between wallets' },
  sybil_cluster: { label: 'Sybil Cluster', icon: '🕸️', desc: 'Single funder distributing to many wallets' },
  high_velocity: { label: 'High Velocity', icon: '⚡', desc: 'Bot-like transaction frequency' },
};

export default function FraudAlerts() {
  const [alerts, setAlerts] = useState<FraudAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');

  useEffect(() => {
    async function load() {
      try {
        const [wash, sybil, velocity] = await Promise.all([
          getWashTrading(),
          getSybilClusters(),
          getHighVelocity(),
        ]);
        const all = [...wash, ...sybil, ...velocity];
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

  const counts = {
    all: alerts.length,
    wash_trading: alerts.filter((a) => a.pattern === 'wash_trading').length,
    sybil_cluster: alerts.filter((a) => a.pattern === 'sybil_cluster').length,
    high_velocity: alerts.filter((a) => a.pattern === 'high_velocity').length,
  };

  if (loading) return <Loading message="Running fraud detection..." />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div>
      <div className="page-header">
        <h2>🛡️ Fraud Detection</h2>
        <p>Graph-based pattern analysis across indexed wallets</p>
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
      <div className="tabs">
        {(['all', 'wash_trading', 'sybil_cluster', 'high_velocity'] as const).map((f) => (
          <button
            key={f}
            className={`tab ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? `All (${counts.all})` : `${PATTERN_LABELS[f]?.label} (${counts[f]})`}
          </button>
        ))}
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
                  <AddressLink key={w} address={w} />
                ))}
                {alert.wallets.length > 6 && (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    +{alert.wallets.length - 6} more
                  </span>
                )}
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
