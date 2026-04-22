import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Star, Trash2, Pencil, Check, X, Copy } from 'lucide-react';
import { getFavourites, removeFavourite, updateNickname } from '../stores/favourites';
import { getWallet } from '../services/api';
import type { WalletSummary } from '../types';
import type { FavouriteWallet } from '../stores/favourites';

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      title={copied ? 'Copied!' : 'Copy address'}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 2,
        color: copied ? '#22c55e' : 'var(--text-muted)',
        display: 'inline-flex',
        alignItems: 'center',
      }}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  );
}

function formatMON(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}K`;
  return value.toFixed(4);
}

interface FavRow extends FavouriteWallet {
  wallet: WalletSummary | null;
  loading: boolean;
}

export default function Favourites() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<FavRow[]>([]);
  const [editingAddr, setEditingAddr] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  useEffect(() => {
    const favs = getFavourites();
    const initial: FavRow[] = favs.map((f) => ({ ...f, wallet: null, loading: true }));
    setRows(initial);

    // Fetch wallet data for each favourite
    favs.forEach((f, i) => {
      getWallet(f.address)
        .then((w) => {
          setRows((prev) => prev.map((r, j) => (j === i ? { ...r, wallet: w, loading: false } : r)));
        })
        .catch(() => {
          setRows((prev) => prev.map((r, j) => (j === i ? { ...r, loading: false } : r)));
        });
    });
  }, []);

  const handleRemove = (address: string) => {
    removeFavourite(address);
    setRows((prev) => prev.filter((r) => r.address.toLowerCase() !== address.toLowerCase()));
  };

  const handleStartEdit = (address: string, currentNickname: string) => {
    setEditingAddr(address);
    setEditValue(currentNickname);
  };

  const handleSaveEdit = (address: string) => {
    updateNickname(address, editValue.trim());
    setRows((prev) =>
      prev.map((r) =>
        r.address.toLowerCase() === address.toLowerCase()
          ? { ...r, nickname: editValue.trim() }
          : r
      )
    );
    setEditingAddr(null);
  };

  return (
    <div>
      <div className="page-header">
        <h2>⭐ Favourites</h2>
        <p>Your saved wallet addresses for quick access</p>
      </div>

      {rows.length === 0 ? (
        <div className="empty-state">
          <div className="icon">⭐</div>
          <h3>No favourites yet</h3>
          <p>Look up a wallet and click the star icon to add it here</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rows.map((r) => (
            <div
              key={r.address}
              className="card"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '14px 18px',
                cursor: 'pointer',
                transition: 'border-color 0.15s',
              }}
              onClick={() => navigate(`/wallet/${r.address}`)}
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--accent)')}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}>
                <Star size={18} fill="#f59e0b" color="#f59e0b" />
                <div style={{ minWidth: 0 }}>
                  {/* Nickname */}
                  {editingAddr === r.address ? (
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        placeholder="Nickname..."
                        style={{
                          background: 'var(--bg-secondary)',
                          border: '1px solid var(--border)',
                          borderRadius: 4,
                          padding: '2px 8px',
                          color: 'var(--text)',
                          fontSize: 14,
                          fontWeight: 600,
                          width: 180,
                        }}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveEdit(r.address);
                          if (e.key === 'Escape') setEditingAddr(null);
                        }}
                      />
                      <button
                        onClick={() => handleSaveEdit(r.address)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#22c55e', padding: 2 }}
                      >
                        <Check size={16} />
                      </button>
                      <button
                        onClick={() => setEditingAddr(null)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ) : (
                    r.nickname && (
                      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{r.nickname}</div>
                    )
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="address" style={{ fontSize: 13 }}>
                      {r.address.slice(0, 14)}…{r.address.slice(-10)}
                    </span>
                    <CopyBtn text={r.address} />
                  </div>
                </div>
              </div>

              {/* Right side: balance + labels + actions */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                {r.loading ? (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading...</span>
                ) : r.wallet ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {r.wallet.balance != null && (
                      <span style={{ fontFamily: 'monospace', fontSize: 13, fontWeight: 600 }}>
                        {formatMON(r.wallet.balance)} MON
                      </span>
                    )}
                    {r.wallet.staking && r.wallet.staking.length > 0 && (
                      <span className="badge badge-info" style={{ fontSize: 11 }}>🥩 Staking</span>
                    )}
                    {r.wallet.labels
                      .filter((l) => l !== 'not yet indexed' && l !== 'staker')
                      .map((l) => (
                        <span key={l} className="badge badge-info" style={{ fontSize: 11 }}>{l}</span>
                      ))}
                  </div>
                ) : null}

                {/* Edit nickname button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleStartEdit(r.address, r.nickname);
                  }}
                  title="Edit nickname"
                  style={{
                    background: 'none',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    padding: '4px 6px',
                    cursor: 'pointer',
                    color: 'var(--text-muted)',
                  }}
                >
                  <Pencil size={14} />
                </button>

                {/* Remove button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemove(r.address);
                  }}
                  title="Remove from favourites"
                  style={{
                    background: 'none',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    padding: '4px 6px',
                    cursor: 'pointer',
                    color: 'var(--text-muted)',
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
