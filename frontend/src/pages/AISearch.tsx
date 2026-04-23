import { useState } from 'react';
import { Search } from 'lucide-react';
import { searchQuery } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import AddressLink from '../components/AddressLink';
import type { SearchResult } from '../types';

const EXAMPLE_QUERIES = [
  'Show me the top wallets',
  'Any large transfers?',
  'Suspicious activity',
  'New wallets',
  'Give me the stats',
  'Which wallets sent the most transactions?',
  'Find wallets that transacted with each other',
  'Who are the most connected wallets?',
];

export default function AISearch() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setQuery(text);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await searchQuery(text);
      setResult(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch(query);
  };

  // Try to render data in a table if it's an array of objects
  function renderData(data: Record<string, unknown>[]) {
    if (data.length === 0) return <p style={{ color: 'var(--text-muted)' }}>No results</p>;
    const keys = Object.keys(data[0]);
    return (
      <div className="table-container">
        <table>
          <thead>
            <tr>
              {keys.map((k) => (
                <th key={k}>{k.replace(/_/g, ' ')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i}>
                {keys.map((k) => {
                  const val = row[k];
                  const str = typeof val === 'number'
                    ? val.toLocaleString(undefined, { maximumFractionDigits: 4 })
                    : String(val ?? '');
                  // If it looks like an address, make it clickable
                  if (typeof val === 'string' && val.startsWith('0x') && val.length === 42) {
                    return <td key={k}><AddressLink address={val} /></td>;
                  }
                  return <td key={k}>{str}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h2>🤖 AI Search</h2>
        <p>Ask questions about Monad blockchain data in natural language</p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="search-container">
          <Search size={18} className="search-icon" />
          <input
            className="search-input"
            type="text"
            placeholder="Ask a question... e.g. 'Show me the top wallets'"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </form>

      {/* Example queries */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 24 }}>
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            className="btn btn-ghost"
            onClick={() => {
              setQuery(q);
              handleSearch(q);
            }}
          >
            {q}
          </button>
        ))}
      </div>

      {error && <ErrorBox message={error} />}
      {loading && <Loading message="Searching..." />}

      {result && (
        <div className="result-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            {result.source === 'ai' && (
              <span style={{
                fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.5px', padding: '2px 8px', borderRadius: 4,
                background: 'rgba(131, 110, 249, 0.12)', color: '#836EF9',
              }}>
                ✨ AI
              </span>
            )}
          </div>
          <div className="answer">{result.answer}</div>
          {result.data && result.data.length > 0 && renderData(result.data)}

        </div>
      )}

      {!result && !loading && (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <div className="icon">💬</div>
          <h3>Ask anything</h3>
          <p>Try one of the example queries above, or type your own question</p>
        </div>
      )}
    </div>
  );
}
