import { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function CopyButton({ text }: { text: string }) {
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
