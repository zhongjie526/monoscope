import { useState, useCallback, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import ForceGraph2D from 'react-force-graph-2d';
import { Search } from 'lucide-react';
import { getWalletGraph } from '../services/api';
import Loading from '../components/Loading';
import ErrorBox from '../components/ErrorBox';
import type { GraphData } from '../types';

interface GraphNode {
  id: string;
  label: string;
  isCenter: boolean;
}

interface GraphLink {
  source: string;
  target: string;
  value: number;
  tx_hash: string;
}

export default function GraphExplorer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialAddr = searchParams.get('address') || '';
  const [address, setAddress] = useState(initialAddr);
  const [inputVal, setInputVal] = useState(initialAddr);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphLink[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, 500),
        });
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const loadGraph = useCallback(async (addr: string) => {
    if (!addr) return;
    setLoading(true);
    setError(null);
    try {
      const data: GraphData = await getWalletGraph(addr);
      const nodes: GraphNode[] = data.nodes.map((n) => ({
        id: n.address,
        label: `${n.address.slice(0, 6)}…${n.address.slice(-4)}`,
        isCenter: n.address.toLowerCase() === addr.toLowerCase(),
      }));
      const links: GraphLink[] = data.edges.map((e) => ({
        source: e.from,
        target: e.to,
        value: e.value,
        tx_hash: e.tx_hash,
      }));
      setGraphData({ nodes, links });
    } catch (err) {
      setError((err as Error).message);
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialAddr) loadGraph(initialAddr);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const addr = inputVal.trim();
    if (addr) {
      setAddress(addr);
      setSearchParams({ address: addr });
      loadGraph(addr);
    }
  };

  const handleNodeClick = useCallback((node: GraphNode) => {
    setInputVal(node.id);
    setAddress(node.id);
    setSearchParams({ address: node.id });
    loadGraph(node.id);
  }, [loadGraph, setSearchParams]);

  return (
    <div>
      <div className="page-header">
        <h2>🕸️ Graph Explorer</h2>
        <p>Visualize wallet connections and fund flows</p>
      </div>

      <form onSubmit={handleSearch}>
        <div className="search-container">
          <Search size={18} className="search-icon" />
          <input
            className="search-input"
            type="text"
            placeholder="Enter wallet address to explore its graph..."
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
          />
        </div>
      </form>

      {error && <ErrorBox message={error} />}

      {loading ? (
        <Loading message="Loading graph data..." />
      ) : graphData ? (
        <div>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 13, color: 'var(--text-muted)' }}>
            <span>📊 {graphData.nodes.length} nodes</span>
            <span>🔗 {graphData.links.length} edges</span>
            {hoveredNode && <span>🎯 {hoveredNode}</span>}
          </div>
          <div ref={containerRef} className="graph-container" style={{ height: 500 }}>
            <ForceGraph2D
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData}
              nodeLabel={(node: GraphNode) => node.id}
              nodeColor={(node: GraphNode) =>
                node.isCenter ? '#6366f1' : '#06b6d4'
              }
              nodeRelSize={6}
              nodeCanvasObjectMode={() => 'after'}
              nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D) => {
                const label = node.label || '';
                const fontSize = node.isCenter ? 11 : 9;
                ctx.font = `${fontSize}px Inter, sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.fillStyle = node.isCenter ? '#e2e8f0' : '#94a3b8';
                ctx.fillText(label, node.x!, node.y! + 8);
              }}
              linkColor={() => 'rgba(99, 102, 241, 0.3)'}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={0.9}
              linkWidth={1.5}
              backgroundColor="transparent"
              onNodeHover={(node: GraphNode | null) => setHoveredNode(node?.id ?? null)}
              onNodeClick={(node: any) => handleNodeClick(node as GraphNode)}
              cooldownTicks={100}
            />
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
            💡 Click on a node to explore its connections. Scroll to zoom, drag to pan.
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
