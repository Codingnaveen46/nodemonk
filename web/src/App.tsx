import React, { useState, useEffect } from 'react';
import { GraphCanvas } from './components/GraphCanvas';
import { StatsBar } from './components/StatsBar';
import { CommunityExplorer } from './components/CommunityExplorer';
import { GodNodesPanel } from './components/GodNodesPanel';
import { PathFinder } from './components/PathFinder';
import { QueryConsole } from './components/QueryConsole';
import { CycleViewer } from './components/CycleViewer';
import { NodeInspector } from './components/NodeInspector';
import { GraphNode, GraphEdge, GraphStats, CommunityInfo, GodNode, CycleInfo } from './types';
import { Layers, Crown, GitCommit, Terminal, RefreshCw, Search } from 'lucide-react';

const COMMUNITY_COLORS: Record<number, string> = {
  0: '#4f8cff', 1: '#22c55e', 2: '#f97316', 3: '#a855f7',
  4: '#06b6d4', 5: '#e11d48', 6: '#84cc16', 7: '#f59e0b',
  8: '#8b5cf6', 9: '#14b8a6', 10: '#ef4444', 11: '#0ea5e9',
  12: '#84e1bc', 13: '#d946ef', 14: '#f472b6', 15: '#38bdf8',
  16: '#fb923c', 17: '#34d399', 18: '#c084fc', 19: '#facc15',
};

export const App: React.FC = () => {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [communities, setCommunities] = useState<CommunityInfo[]>([]);
  const [godNodes, setGodNodes] = useState<GodNode[]>([]);
  const [cycles, setCycles] = useState<CycleInfo[]>([]);
  const [activeTab, setActiveTab] = useState<'communities' | 'gods' | 'path' | 'query' | 'cycles'>('communities');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightedCommunity, setHighlightedCommunity] = useState<number | null>(null);
  const [activePath, setActivePath] = useState<string[] | null>(null);
  const [queryResults, setQueryResults] = useState<any | null>(null);
  const [globalSearch, setGlobalSearch] = useState('');
  const [loading, setLoading] = useState(true);

  // Load Initial Graph Data from backend
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [graphRes, statsRes, godsRes, cyclesRes] = await Promise.all([
          fetch('/api/graph.json').then(r => r.json()),
          fetch('/api/stats').then(r => r.json()).catch(() => null),
          fetch('/api/hubs?limit=25').then(r => r.json()).catch(() => ({ hubs: [] })),
          fetch('/api/cycles?limit=20').then(r => r.json()).catch(() => ({ cycles: [] })),
        ]);

        if (graphRes && graphRes.nodes) {
          // Normalize nodes and edges
          const commMap: Record<string, number> = {};
          const commInfoList: CommunityInfo[] = [];

          if (graphRes.communities) {
            Object.entries(graphRes.communities).forEach(([cidStr, members]) => {
              const cid = parseInt(cidStr, 10);
              const mList = members as string[];
              mList.forEach(m => (commMap[m] = cid));
              commInfoList.push({
                id: cid,
                label: (graphRes.community_labels && graphRes.community_labels[cidStr]) || `Community ${cid}`,
                size: mList.length,
                cohesion: (graphRes.cohesion && graphRes.cohesion[cidStr]) || 0.8,
                members: mList,
              });
            });
            commInfoList.sort((a, b) => b.size - a.size);
            setCommunities(commInfoList);
          }

          const rawNodes: GraphNode[] = graphRes.nodes.map((n: any) => ({
            id: n.id,
            label: n.label || n.id,
            file: n.source_file || n.file,
            source_file: n.source_file || n.file,
            source_location: n.source_location,
            kind: n.kind,
            community: commMap[n.id] !== undefined ? commMap[n.id] : n.community,
            docstring: n.docstring,
            degree: n.degree || 1,
          }));

          const rawEdges: GraphEdge[] = (graphRes.links || graphRes.edges || []).map((e: any) => ({
            source: e.source,
            target: e.target,
            relation: e.relation,
            confidence: e.confidence || 'EXTRACTED',
          }));

          setNodes(rawNodes);
          setEdges(rawEdges);

          if (statsRes) {
            setStats({
              nodes: statsRes.nodes || rawNodes.length,
              edges: statsRes.edges || rawEdges.length,
              avg_degree: statsRes.avg_degree || 0,
              median_degree: statsRes.median_degree || 0,
              max_degree: statsRes.max_degree || 0,
              self_loops: statsRes.self_loops || 0,
              edge_density: statsRes.edge_density || 0,
              confidence_profile: statsRes.confidence_profile || {},
              communities_count: commInfoList.length,
            });
          }

          if (godsRes && godsRes.hubs) {
            setGodNodes(godsRes.hubs.map((h: any) => ({
              id: h.id,
              label: h.label || h.id,
              score: h.score,
              kind: h.kind,
              file: h.file,
            })));
          }

          if (cyclesRes && cyclesRes.cycles) {
            setCycles(cyclesRes.cycles.map((c: any) => ({
              cycle: c.cycle || c,
              length: (c.cycle || c).length,
            })));
          }
        }
      } catch (err) {
        console.error('Failed to load graph data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleSelectNodeById = (id: string) => {
    const node = nodes.find(n => n.id === id);
    if (node) {
      setSelectedNode(node);
    }
  };

  const handleFindPath = async (sourceId: string, targetId: string) => {
    const res = await fetch(`/api/path?a=${encodeURIComponent(sourceId)}&b=${encodeURIComponent(targetId)}`);
    const data = await res.json();
    if (data.path && data.path.length > 0) {
      setActivePath(data.path);
      return data.path;
    }
    setActivePath(null);
    return null;
  };

  const handleRunQuery = async (question: string, mode: 'bfs' | 'dfs') => {
    const res = await fetch(`/api/query?question=${encodeURIComponent(question)}&mode=${mode}`);
    const data = await res.json();
    setQueryResults(data);
  };

  const handleExport = (format: string) => {
    window.open(`/api/graph.json`, '_blank');
  };

  // Filtered nodes based on search or community
  const filteredNodes = nodes.filter(n => {
    if (globalSearch.trim()) {
      const q = globalSearch.toLowerCase();
      return n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {/* Top Navbar / Metrics */}
      <StatsBar stats={stats} onExport={handleExport} />

      {/* Main Workspace */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, position: 'relative' }}>
        {/* Left Control Sidebar */}
        <div style={{
          width: 320,
          background: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
        }}>
          {/* Quick Search */}
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search nodes or functions..."
                value={globalSearch}
                onChange={e => setGlobalSearch(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 10px 6px 30px',
                  borderRadius: 6,
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: 12,
                  outline: 'none',
                }}
              />
            </div>
          </div>

          {/* Navigation Tabs */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg-card)',
          }}>
            <button
              onClick={() => setActiveTab('communities')}
              title="Communities"
              style={{
                flex: 1,
                padding: '9px 0',
                background: activeTab === 'communities' ? 'var(--bg-secondary)' : 'transparent',
                border: 'none',
                borderBottom: activeTab === 'communities' ? '2px solid var(--accent)' : 'none',
                color: activeTab === 'communities' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <Layers size={16} />
            </button>
            <button
              onClick={() => setActiveTab('gods')}
              title="Hubs & God Nodes"
              style={{
                flex: 1,
                padding: '9px 0',
                background: activeTab === 'gods' ? 'var(--bg-secondary)' : 'transparent',
                border: 'none',
                borderBottom: activeTab === 'gods' ? '2px solid var(--accent)' : 'none',
                color: activeTab === 'gods' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <Crown size={16} />
            </button>
            <button
              onClick={() => setActiveTab('path')}
              title="Shortest Path Finder"
              style={{
                flex: 1,
                padding: '9px 0',
                background: activeTab === 'path' ? 'var(--bg-secondary)' : 'transparent',
                border: 'none',
                borderBottom: activeTab === 'path' ? '2px solid var(--accent)' : 'none',
                color: activeTab === 'path' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <GitCommit size={16} />
            </button>
            <button
              onClick={() => setActiveTab('query')}
              title="Query Traversal"
              style={{
                flex: 1,
                padding: '9px 0',
                background: activeTab === 'query' ? 'var(--bg-secondary)' : 'transparent',
                border: 'none',
                borderBottom: activeTab === 'query' ? '2px solid var(--accent)' : 'none',
                color: activeTab === 'query' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <Terminal size={16} />
            </button>
            <button
              onClick={() => setActiveTab('cycles')}
              title="Cycles"
              style={{
                flex: 1,
                padding: '9px 0',
                background: activeTab === 'cycles' ? 'var(--bg-secondary)' : 'transparent',
                border: 'none',
                borderBottom: activeTab === 'cycles' ? '2px solid var(--accent)' : 'none',
                color: activeTab === 'cycles' ? 'var(--accent)' : 'var(--text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <RefreshCw size={16} />
            </button>
          </div>

          {/* Active Tab Panel */}
          <div style={{ flex: 1, minHeight: 0 }}>
            {activeTab === 'communities' && (
              <CommunityExplorer
                communities={communities}
                highlightedCommunity={highlightedCommunity}
                onSelectCommunity={setHighlightedCommunity}
                communityColors={COMMUNITY_COLORS}
              />
            )}
            {activeTab === 'gods' && (
              <GodNodesPanel
                godNodes={godNodes}
                onSelectNodeById={handleSelectNodeById}
              />
            )}
            {activeTab === 'path' && (
              <PathFinder
                nodes={nodes}
                onFindPath={handleFindPath}
                activePath={activePath}
                onClearPath={() => setActivePath(null)}
                onSelectNodeById={handleSelectNodeById}
              />
            )}
            {activeTab === 'query' && (
              <QueryConsole
                onRunQuery={handleRunQuery}
                queryResults={queryResults}
                onSelectNodeById={handleSelectNodeById}
                onClearQuery={() => setQueryResults(null)}
              />
            )}
            {activeTab === 'cycles' && (
              <CycleViewer
                cycles={cycles}
                onSelectNodeById={handleSelectNodeById}
              />
            )}
          </div>
        </div>

        {/* Center: Interactive Knowledge Graph Canvas */}
        <div style={{ flex: 1, height: '100%', minWidth: 0, position: 'relative' }}>
          <GraphCanvas
            nodes={filteredNodes}
            edges={edges}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            highlightedCommunity={highlightedCommunity}
            activePath={activePath}
            communityColors={COMMUNITY_COLORS}
          />
        </div>

        {/* Right: Node Inspector Drawer */}
        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onSelectNodeById={handleSelectNodeById}
            communityColors={COMMUNITY_COLORS}
          />
        )}
      </div>
    </div>
  );
};
