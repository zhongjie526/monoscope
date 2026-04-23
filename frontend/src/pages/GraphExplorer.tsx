import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import ForceGraph2D from 'react-force-graph-2d';
import { Search, Star, ChevronDown, X, ExternalLink, Maximize2, ZoomIn, ZoomOut, RotateCcw, Copy, Check } from 'lucide-react';
import { getWalletGraph } from '../services/api';
import { getFavourites, isFavourite } from '../stores/favourites';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import { formatMON } from '../utils/format';
import type { GraphData } from '../types';

// ── Types ──────────────────────────────────────────────────────────────

const STAKING_CONTRACT = '0x0000000000000000000000000000000000001000';

type NodeCategory = 'center' | 'contract' | 'favourite' | 'wallet';

interface GraphNode {
  id: string;
  label: string;
  category: NodeCategory;
  totalValue: number;  // total MON flowing through this node (in edges)
  edgeCount: number;   // number of edges touching this node
  radius: number;      // computed node size
  balance?: number;
  txCount?: number;
  totalSent?: number;
  totalReceived?: number;
  staked?: number;
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
  txCount: number;
}

// ── Color palette (Bloom-inspired) ────────────────────────────────────

const COLORS: Record<NodeCategory, { fill: string; stroke: string; glow: string; text: string }> = {
  center:    { fill: '#6366f1', stroke: '#818cf8', glow: 'rgba(99,102,241,0.4)',  text: '#e2e8f0' },
  contract:  { fill: '#ef4444', stroke: '#f87171', glow: 'rgba(239,68,68,0.3)',   text: '#fca5a5' },
  favourite: { fill: '#f59e0b', stroke: '#fbbf24', glow: 'rgba(245,158,11,0.3)',  text: '#fde68a' },
  wallet:    { fill: '#06b6d4', stroke: '#22d3ee', glow: 'rgba(6,182,212,0.25)',  text: '#a5f3fc' },
};

const EDGE_COLOR = 'rgba(148, 163, 184, 0.4)';
const EDGE_HIGHLIGHT = 'rgba(129, 140, 248, 0.85)';
const BG_COLOR = '#0a0a14';

// ── Helpers ────────────────────────────────────────────────────────────

function shortAddr(addr: string): string {
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function categorize(addr: string, centerAddr: string): NodeCategory {
  if (addr.toLowerCase() === centerAddr.toLowerCase()) return 'center';
  if (addr === STAKING_CONTRACT || addr.startsWith('0x00000000000000000000000000000000')) return 'contract';
  if (isFavourite(addr)) return 'favourite';
  return 'wallet';
}

// ── Favourites Dropdown ───────────────────────────────────────────────

function FavouritesDropdown({ onSelect }: { onSelect: (addr: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const favs = getFavourites();

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (favs.length === 0) return null;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '0 14px', height: 47,
          background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
          cursor: 'pointer', color: 'var(--text)', fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap',
        }}
      >
        <Star size={14} fill="#f59e0b" color="#f59e0b" /> Favourites
        <ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>
      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', right: 0, minWidth: 320,
          background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.3)', zIndex: 50, maxHeight: 300, overflowY: 'auto',
        }}>
          {favs.map((f) => (
            <button key={f.address} onClick={() => { onSelect(f.address); setOpen(false); }}
              style={{
                display: 'flex', flexDirection: 'column', width: '100%', padding: '10px 14px',
                background: 'none', border: 'none', borderBottom: '1px solid var(--border)',
                cursor: 'pointer', color: 'var(--text)', textAlign: 'left',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-secondary)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              {f.nickname && <span style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>{f.nickname}</span>}
              <span className="address" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {f.address.slice(0, 14)}…{f.address.slice(-10)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Inspector Panel ───────────────────────────────────────────────────

function InspectorPanel({
  node, edges, onClose, onExpand,
}: {
  node: GraphNode;
  edges: GraphLink[];
  onClose: () => void;
  onExpand: (addr: string) => void;
}) {
  const navigate = useNavigate();
  const colors = COLORS[node.category];
  const inEdges = edges.filter((e) => {
    const t = typeof e.target === 'string' ? e.target : (e.target as any).id;
    return t === node.id;
  });
  const outEdges = edges.filter((e) => {
    const s = typeof e.source === 'string' ? e.source : (e.source as any).id;
    return s === node.id;
  });
  const inTotal = inEdges.reduce((s, e) => s + e.value, 0);
  const outTotal = outEdges.reduce((s, e) => s + e.value, 0);

  return (
    <div style={{
      position: 'absolute', top: 12, right: 12, width: 300, maxHeight: 'calc(100% - 24px)',
      background: 'rgba(15,15,25,0.95)', border: `1px solid ${colors.stroke}`, borderRadius: 12,
      padding: 16, overflowY: 'auto', zIndex: 100, backdropFilter: 'blur(12px)',
      boxShadow: `0 0 24px ${colors.glow}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: colors.fill, textTransform: 'uppercase', marginBottom: 4 }}>
            {node.category === 'center' ? '📍 Center Node' :
             node.category === 'contract' ? '📜 Contract' :
             node.category === 'favourite' ? '⭐ Favourite' : '👛 Wallet'}
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 12, color: '#e2e8f0', wordBreak: 'break-all' }}>
            {node.id}
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}>
          <X size={16} />
        </button>
      </div>

      {/* Balance (if available) */}
      {node.balance != null && (
        <div style={{ background: 'rgba(99,102,241,0.1)', padding: '8px 10px', borderRadius: 8, marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: '#818cf8', fontWeight: 600 }}>BALANCE</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>{formatMON(node.balance)} MON</div>
          {node.staked != null && node.staked > 0 && (
            <div style={{ fontSize: 11, color: '#a5b4fc' }}>🥩 {formatMON(node.staked)} staked</div>
          )}
        </div>
      )}

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 14 }}>
        <div style={{ background: 'rgba(34,197,94,0.1)', padding: '8px 10px', borderRadius: 8 }}>
          <div style={{ fontSize: 10, color: '#22c55e', fontWeight: 600 }}>RECEIVED</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#22c55e' }}>
            {node.totalReceived != null ? formatMON(node.totalReceived) : inEdges.reduce((s, e) => s + e.txCount, 0)} {node.totalReceived != null ? 'MON' : 'tx'}
          </div>
        </div>
        <div style={{ background: 'rgba(239,68,68,0.1)', padding: '8px 10px', borderRadius: 8 }}>
          <div style={{ fontSize: 10, color: '#ef4444', fontWeight: 600 }}>SENT</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#ef4444' }}>
            {node.totalSent != null ? formatMON(node.totalSent) : outEdges.reduce((s, e) => s + e.txCount, 0)} {node.totalSent != null ? 'MON' : 'tx'}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button
          onClick={() => onExpand(node.id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px',
            background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 8, cursor: 'pointer', color: '#818cf8', fontSize: 13, fontWeight: 500,
          }}
        >
          <Maximize2 size={14} /> Expand Neighbours
        </button>
        <button
          onClick={() => navigate(`/wallet/${node.id}`)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px',
            background: 'rgba(6,182,212,0.15)', border: '1px solid rgba(6,182,212,0.3)',
            borderRadius: 8, cursor: 'pointer', color: '#22d3ee', fontSize: 13, fontWeight: 500,
          }}
        >
          <Search size={14} /> Open in Wallet Lookup
        </button>
        <a
          href={`https://monadscan.com/address/${node.id}`}
          target="_blank" rel="noopener noreferrer"
          style={{
            display: 'flex', alignItems: 'center', gap: 6, width: '100%', padding: '8px 12px',
            background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)',
            borderRadius: 8, color: '#fbbf24', fontSize: 13, fontWeight: 500, textDecoration: 'none',
          }}
        >
          <ExternalLink size={14} /> View on Monadscan
        </a>
      </div>
    </div>
  );
}

// ── Legend ─────────────────────────────────────────────────────────────

function Legend() {
  const items: { category: NodeCategory; label: string }[] = [
    { category: 'center', label: 'Search Target' },
    { category: 'favourite', label: 'Favourite' },
    { category: 'contract', label: 'Contract' },
    { category: 'wallet', label: 'Wallet' },
  ];
  return (
    <div style={{
      position: 'absolute', bottom: 12, left: 12, display: 'flex', gap: 14,
      background: 'rgba(15,15,25,0.85)', padding: '8px 14px', borderRadius: 8,
      backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.08)',
    }}>
      {items.map((it) => (
        <div key={it.category} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: COLORS[it.category].fill,
            boxShadow: `0 0 6px ${COLORS[it.category].glow}`,
          }} />
          <span style={{ fontSize: 11, color: '#94a3b8' }}>{it.label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────

export default function GraphExplorer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialAddr = searchParams.get('address') || '';
  const [address, setAddress] = useState(initialAddr);
  const [inputVal, setInputVal] = useState(initialAddr);
  const [rawData, setRawData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{ node: GraphNode; x: number; y: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({ width: entry.contentRect.width, height: Math.max(entry.contentRect.height, 600) });
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Load graph data
  const loadGraph = useCallback(async (addr: string) => {
    if (!addr) return;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    try {
      const data: GraphData = await getWalletGraph(addr);
      setRawData(data);
    } catch (err) {
      setError((err as Error).message);
      setRawData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialAddr) loadGraph(initialAddr);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Process raw data into rich graph nodes/links
  const graphData = useMemo(() => {
    if (!rawData) return null;

    // Aggregate edge values per node
    const nodeValues = new Map<string, { totalValue: number; edgeCount: number }>();
    for (const edge of rawData.edges) {
      for (const addr of [edge.from, edge.to]) {
        const existing = nodeValues.get(addr) || { totalValue: 0, edgeCount: 0 };
        existing.totalValue += edge.value;
        existing.edgeCount += 1;
        nodeValues.set(addr, existing);
      }
    }

    // Compute radius range
    const values = [...nodeValues.values()].map((v) => v.totalValue);
    const maxVal = Math.max(...values, 1);

    const nodes: GraphNode[] = rawData.nodes.map((n) => {
      const stats = nodeValues.get(n.address) || { totalValue: 0, edgeCount: 0 };
      const category = categorize(n.address, address);
      // Larger nodes to fit label inside — center 14, others 10
      const baseRadius = category === 'center' ? 14 : 10;
      const valueRadius = Math.sqrt(stats.totalValue / maxVal) * 4;
      const radius = Math.max(baseRadius, baseRadius + valueRadius);
      return {
        id: n.address,
        label: shortAddr(n.address),
        category,
        totalValue: stats.totalValue,
        edgeCount: stats.edgeCount,
        radius,
        balance: n.balance,
        txCount: n.tx_count,
        totalSent: n.total_sent,
        totalReceived: n.total_received,
        staked: n.staked,
      };
    });

    // Aggregate edges: combine all txs between same (from, to) pair
    const edgeMap = new Map<string, { source: string; target: string; value: number; txCount: number }>();
    for (const e of rawData.edges) {
      const key = `${e.from}->${e.to}`;
      const existing = edgeMap.get(key);
      if (existing) {
        existing.value += e.value;
        existing.txCount += 1;
      } else {
        edgeMap.set(key, { source: e.from, target: e.to, value: e.value, txCount: 1 });
      }
    }
    const links: GraphLink[] = [...edgeMap.values()];

    return { nodes, links };
  }, [rawData, address]);

  // Spread nodes further apart once graph mounts
  useEffect(() => {
    const t = setTimeout(() => {
      if (graphRef.current) {
        try {
          graphRef.current.d3Force('charge')?.strength(-500);
          graphRef.current.d3Force('link')?.distance(120);
          graphRef.current.d3ReheatSimulation();
        } catch (_) { /* ref not ready */ }
      }
    }, 100);
    return () => clearTimeout(t);
  }, [graphData]);

  // Edge width range
  const edgeMaxValue = useMemo(() => {
    if (!graphData) return 1;
    return Math.max(...graphData.links.map((l) => l.value), 1);
  }, [graphData]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const addr = inputVal.trim();
    if (addr) {
      setAddress(addr);
      setSearchParams({ address: addr });
      loadGraph(addr);
    }
  };

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as GraphNode);
  }, []);

  const handleExpand = useCallback((addr: string) => {
    setInputVal(addr);
    setAddress(addr);
    setSearchParams({ address: addr });
    loadGraph(addr);
  }, [loadGraph, setSearchParams]);

  const handleZoom = useCallback((dir: 'in' | 'out' | 'fit') => {
    const fg = graphRef.current;
    if (!fg) return;
    if (dir === 'fit') { fg.zoomToFit(400, 80); return; }
    const currentZoom = fg.zoom();
    fg.zoom(dir === 'in' ? currentZoom * 1.5 : currentZoom / 1.5, 300);
  }, []);

  // Custom node renderer (Bloom-style)
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const n = node as GraphNode;
    const x = node.x;
    const y = node.y;
    if (x == null || y == null || isNaN(x) || isNaN(y)) return;

    const colors = COLORS[n.category];
    const r = n.radius;
    const isHovered = hoveredNode === n.id;
    const isSelected = selectedNode?.id === n.id;

    // Glow
    if (isHovered || isSelected || n.category === 'center') {
      ctx.beginPath();
      ctx.arc(x, y, r + (isSelected ? 6 : 4), 0, Math.PI * 2);
      ctx.fillStyle = colors.glow;
      ctx.fill();
    }

    // Outer ring
    ctx.beginPath();
    ctx.arc(x, y, r + 1.5, 0, Math.PI * 2);
    ctx.fillStyle = isSelected ? '#fff' : colors.stroke;
    ctx.fill();

    // Gradient fill
    const grad = ctx.createRadialGradient(x - r * 0.3, y - r * 0.3, 0, x, y, r);
    grad.addColorStop(0, colors.stroke);
    grad.addColorStop(1, colors.fill);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    // Last 4 chars inside node
    const innerLabel = n.id.slice(-4);
    const innerFontSize = Math.max(8, Math.min(r * 0.8, 12));
    ctx.font = `bold ${innerFontSize}px 'JetBrains Mono', monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#fff';
    ctx.fillText(innerLabel, x, y);

    // Hover: show full address above + balance below
    if (isHovered || isSelected) {
      // Background pill for address
      const addrText = `${n.id.slice(0, 10)}…${n.id.slice(-6)}`;
      ctx.font = 'bold 10px JetBrains Mono, monospace';
      const addrWidth = ctx.measureText(addrText).width + 12;
      ctx.fillStyle = 'rgba(15,15,25,0.9)';
      ctx.beginPath();
      ctx.roundRect(x - addrWidth / 2, y - r - 22, addrWidth, 16, 4);
      ctx.fill();
      ctx.fillStyle = colors.text;
      ctx.textBaseline = 'middle';
      ctx.fillText(addrText, x, y - r - 14);

      // Balance below
      if (n.balance != null) {
        const balText = `${formatMON(n.balance)} MON`;
        ctx.font = 'bold 10px Inter, system-ui, sans-serif';
        const balWidth = ctx.measureText(balText).width + 12;
        ctx.fillStyle = 'rgba(15,15,25,0.9)';
        ctx.beginPath();
        ctx.roundRect(x - balWidth / 2, y + r + 4, balWidth, 16, 4);
        ctx.fill();
        ctx.fillStyle = '#fde68a';
        ctx.textBaseline = 'middle';
        ctx.fillText(balText, x, y + r + 12);
      }
    }
  }, [hoveredNode, selectedNode]);

  return (
    <div>
      <div className="page-header">
        <h2>🕸️ Graph Explorer</h2>
        <p>Visualize wallet connections and fund flows</p>
      </div>

      <form onSubmit={handleSearch}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
          <div className="search-container" style={{ flex: 1, marginBottom: 0 }}>
            <Search size={18} className="search-icon" />
            <input
              className="search-input"
              type="text"
              placeholder="Enter wallet address to explore its graph..."
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
            />
          </div>
          <FavouritesDropdown onSelect={(addr) => {
            setInputVal(addr);
            setAddress(addr);
            setSearchParams({ address: addr });
            loadGraph(addr);
          }} />
        </div>
      </form>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading message="Loading graph data..." />
      ) : graphData ? (
        <div style={{ position: 'relative' }}>
          {/* Stats bar */}
          <div style={{
            display: 'flex', gap: 16, marginBottom: 8, fontSize: 13, color: 'var(--text-muted)',
            alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', gap: 16 }}>
              <span>📊 {graphData.nodes.length} wallets</span>
              <span>🔗 {graphData.links.length} connections</span>
            </div>
          </div>

          {/* Graph canvas */}
          <div
            ref={containerRef}
            style={{
              height: 600, borderRadius: 12, overflow: 'hidden', position: 'relative',
              border: '1px solid rgba(255,255,255,0.06)',
              background: BG_COLOR,
            }}
          >
            <ForceGraph2D
              ref={graphRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              nodeCanvasObject={paintNode}
              nodeCanvasObjectMode={() => 'replace'}
              nodeRelSize={1}
              nodeVal={(node: any) => (node as GraphNode).radius}
              linkColor={(link: any) => {
                const l = link as GraphLink;
                if (selectedNode) {
                  const s = typeof l.source === 'string' ? l.source : (l.source as any).id;
                  const t = typeof l.target === 'string' ? l.target : (l.target as any).id;
                  if (s === selectedNode.id || t === selectedNode.id) return EDGE_HIGHLIGHT;
                }
                return EDGE_COLOR;
              }}
              linkWidth={(link: any) => {
                const l = link as GraphLink;
                return Math.max(1, Math.sqrt(l.value / edgeMaxValue) * 5);
              }}
              linkDirectionalArrowLength={7}
              linkDirectionalArrowRelPos={0.85}
              linkDirectionalArrowColor={() => 'rgba(148, 163, 184, 0.7)'}
              linkDirectionalParticles={(link: any) => {
                if (!selectedNode) return 0;
                const l = link as GraphLink;
                const s = typeof l.source === 'string' ? l.source : (l.source as any).id;
                const t = typeof l.target === 'string' ? l.target : (l.target as any).id;
                return (s === selectedNode.id || t === selectedNode.id) ? 2 : 0;
              }}
              linkDirectionalParticleWidth={2}
              linkDirectionalParticleColor={() => '#818cf8'}
              backgroundColor={BG_COLOR}
              onNodeHover={(node: any) => setHoveredNode(node?.id ?? null)}
              onNodeClick={(node: any) => { setContextMenu(null); handleNodeClick(node); }}
              onNodeRightClick={(node: any, event: MouseEvent) => {
                event.preventDefault();
                const container = containerRef.current;
                const rect = container?.getBoundingClientRect();
                setContextMenu({
                  node: node as GraphNode,
                  x: event.clientX - (rect?.left ?? 0),
                  y: event.clientY - (rect?.top ?? 0),
                });
                setCopied(false);
              }}
              onNodeDrag={(node: any) => {
                // Pin during drag
                node.fx = node.x;
                node.fy = node.y;
              }}
              onNodeDragEnd={(node: any) => {
                // Keep pinned
                node.fx = node.x;
                node.fy = node.y;
              }}
              onEngineStop={() => {
                // After initial layout settles, freeze all nodes in place
                if (graphData) {
                  graphData.nodes.forEach((n: any) => {
                    if (n.fx == null) { n.fx = n.x; n.fy = n.y; }
                  });
                }
                graphRef.current?.zoomToFit(400, 80);
              }}

              onBackgroundClick={() => { setSelectedNode(null); setContextMenu(null); }}
              cooldownTicks={100}
              d3AlphaDecay={0.05}
              d3VelocityDecay={0.4}
              warmupTicks={50}
              enableNodeDrag={true}
              autoPauseRedraw={false}

            />

            {/* Legend */}
            <Legend />

            {/* Zoom controls */}
            <div style={{
              position: 'absolute', bottom: 12, right: 12, display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              {[
                { icon: <ZoomIn size={16} />, action: () => handleZoom('in'), title: 'Zoom in' },
                { icon: <ZoomOut size={16} />, action: () => handleZoom('out'), title: 'Zoom out' },
                { icon: <Maximize2 size={16} />, action: () => handleZoom('fit'), title: 'Fit to view' },
                { icon: <RotateCcw size={16} />, action: () => {
                  // Unpin all nodes and reheat simulation
                  if (graphData) {
                    graphData.nodes.forEach((n: any) => { n.fx = undefined; n.fy = undefined; });
                    graphRef.current?.d3ReheatSimulation();
                    setTimeout(() => graphRef.current?.zoomToFit(400, 80), 500);
                  }
                }, title: 'Reset layout' },
              ].map((btn, i) => (
                <button
                  key={i}
                  onClick={btn.action}
                  title={btn.title}
                  style={{
                    width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(15,15,25,0.85)', border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 6, cursor: 'pointer', color: '#94a3b8',
                  }}
                >
                  {btn.icon}
                </button>
              ))}
            </div>

            {/* Inspector panel */}
            {selectedNode && (
              <InspectorPanel
                node={selectedNode}
                edges={graphData.links}
                onClose={() => setSelectedNode(null)}
                onExpand={handleExpand}
              />
            )}

            {/* Right-click context menu */}
            {contextMenu && (
              <div
                style={{
                  position: 'absolute', left: contextMenu.x, top: contextMenu.y,
                  background: 'rgba(15,15,25,0.95)', border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 8, padding: 4, zIndex: 200, minWidth: 180,
                  boxShadow: '0 8px 24px rgba(0,0,0,0.5)', backdropFilter: 'blur(12px)',
                }}
                onClick={() => setContextMenu(null)}
              >
                <div style={{ padding: '6px 10px', fontSize: 11, color: '#64748b', borderBottom: '1px solid rgba(255,255,255,0.08)', marginBottom: 2 }}>
                  {shortAddr(contextMenu.node.id)}
                </div>
                {[
                  {
                    icon: copied ? <Check size={14} color="#22c55e" /> : <Copy size={14} />,
                    label: copied ? 'Copied!' : 'Copy Address',
                    action: (e: React.MouseEvent) => {
                      e.stopPropagation();
                      navigator.clipboard.writeText(contextMenu.node.id);
                      setCopied(true);
                      setTimeout(() => { setCopied(false); setContextMenu(null); }, 800);
                    },
                  },
                  {
                    icon: <Maximize2 size={14} />,
                    label: 'Expand Neighbours',
                    action: () => handleExpand(contextMenu.node.id),
                  },
                  {
                    icon: <Search size={14} />,
                    label: 'Open in Wallet Lookup',
                    action: () => navigate(`/wallet/${contextMenu.node.id}`),
                  },
                  {
                    icon: <ExternalLink size={14} />,
                    label: 'View on Monadscan',
                    action: () => window.open(`https://monadscan.com/address/${contextMenu.node.id}`, '_blank'),
                  },
                ].map((item, i) => (
                  <button
                    key={i}
                    onClick={item.action}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 10px',
                      background: 'none', border: 'none', cursor: 'pointer', color: '#e2e8f0',
                      fontSize: 13, borderRadius: 4, textAlign: 'left',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                  >
                    {item.icon} {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
            💡 Click a node to inspect. Right-click for actions. Scroll to zoom. Drag to pan.
          </p>
        </div>
      ) : !address ? (
        <div className="empty-state">
          <div className="icon">🕸️</div>
          <h3>Explore the Graph</h3>
          <p>Enter a wallet address to visualize its connections</p>
        </div>
      ) : null}
    </div>
  );
}