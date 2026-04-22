import { useState } from 'react';
import { Star } from 'lucide-react';
import { isFavourite, toggleFavourite } from '../stores/favourites';

export default function FavouriteButton({ address }: { address: string }) {
  const [faved, setFaved] = useState(() => isFavourite(address));
  const handleToggle = () => {
    const nowFaved = toggleFavourite(address);
    setFaved(nowFaved);
  };
  return (
    <button
      onClick={handleToggle}
      title={faved ? 'Remove from favourites' : 'Add to favourites'}
      style={{
        background: 'none',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '4px 6px',
        cursor: 'pointer',
        color: faved ? '#f59e0b' : 'var(--text-muted)',
        display: 'inline-flex',
        alignItems: 'center',
        transition: 'color 0.15s',
      }}
    >
      <Star size={14} fill={faved ? '#f59e0b' : 'none'} />
    </button>
  );
}
