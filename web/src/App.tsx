import React, { useState, useEffect, useMemo, useRef, useDeferredValue } from 'react';
import { GraphCanvas } from './components/GraphCanvas';
import { StatsBar } from './components/StatsBar';
import { CommunityExplorer } from './components/CommunityExplorer';
import { GodNodesPanel } from './components/GodNodesPanel';
import { PathFinder } from './components/PathFinder';
import { QueryConsole } from './components/QueryConsole';
import { CycleViewer } from './components/CycleViewer';
import { NodeInspector } from './components/NodeInspector';
import { GraphNode, GraphEdge, GraphStats, CommunityInfo, GodNode, CycleInfo } from './types';
import { Layers, Crown, GitCommit, Terminal, RefreshCw, Search, Crosshair } from 'lucide-react';

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
  const [searchListOpen, setSearchListOpen] = useState(true);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Load Initial Graph Data (either embedded in standalone graph.html or from HTTP API)
  useEffect(() => {
    const initData = async () => {
      try {
        let graphRes: any = null;
        let statsRes: any = null;
        let godsRes: any = null;
        let cyclesRes: any = null;

        const embedded = (window as any).__NODEMONK_DATA__;
        if (embedded && (embedded.graph || embedded.nodes)) {
          graphRes = embedded.graph || embedded;
          statsRes = embedded.stats || null;
          godsRes = embedded.gods || { hubs: [] };
          cyclesRes = embedded.cycles || { cycles: [] };
        } else if (window.location.protocol.startsWith('http')) {
          const results = await Promise.all([
            fetch('/api/graph.json').then(r => r.json()).catch(() => null),
            fetch('/api/stats').then(r => r.json()).catch(() => null),
            fetch('/api/hubs?limit=25').then(r => r.json()).catch(() => ({ hubs: [] })),
            fetch('/api/cycles?limit=20').then(r => r.json()).catch(() => ({ cycles: [] })),
          ]);
          graphRes = results[0];
          statsRes = results[1];
          godsRes = results[2];
          cyclesRes = results[3];
        }

        if (graphRes && (graphRes.nodes || Array.isArray(graphRes))) {
          const rawNodeList = Array.isArray(graphRes) ? graphRes : graphRes.nodes;
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
                cohesion: (graphRes.cohesion && (typeof graphRes.cohesion === 'object' ? graphRes.cohesion[cidStr] : graphRes.cohesion)) || 0.8,
                members: mList,
              });
            });
            commInfoList.sort((a, b) => b.size - a.size);
            setCommunities(commInfoList);
          }

          const rawNodes: GraphNode[] = rawNodeList.map((n: any) => ({
            id: n.id,
            label: n.label || n.l || n.id,
            file: n.source_file || n.file || n.f,
            source_file: n.source_file || n.file || n.f,
            source_location: n.source_location,
            kind: n.kind || n.t,
            community: commMap[n.id] !== undefined ? commMap[n.id] : (n.community !== undefined ? n.community : n.com),
            docstring: n.docstring,
            degree: n.degree || n.deg || 1,
          }));

          const rawEdges: GraphEdge[] = (graphRes.links || graphRes.edges || []).map((e: any) => {
            const sId = typeof e.source === 'object' ? e.source.id : (e.source !== undefined ? e.source : e.s);
            const tId = typeof e.target === 'object' ? e.target.id : (e.target !== undefined ? e.target : e.t);
            // Handle index-based links if present
            const finalS = typeof sId === 'number' && rawNodes[sId] ? rawNodes[sId].id : String(sId);
            const finalT = typeof tId === 'number' && rawNodes[tId] ? rawNodes[tId].id : String(tId);
            return {
              source: finalS,
              target: finalT,
              relation: e.relation || e.r || 'CALLS',
              confidence: e.confidence || e.c || 'EXTRACTED',
            };
          });

          setNodes(rawNodes);
          setEdges(rawEdges);

          if (statsRes) {
            setStats({
              nodes: statsRes.nodes || rawNodes.length,
              edges: statsRes.edges || rawEdges.length,
              avg_degree: statsRes.avg_degree || Number(((rawEdges.length * 2) / Math.max(1, rawNodes.length)).toFixed(2)),
              median_degree: statsRes.median_degree || 0,
              max_degree: statsRes.max_degree || 0,
              self_loops: statsRes.self_loops || 0,
              edge_density: statsRes.edge_density || 0,
              confidence_profile: statsRes.confidence_profile || {},
              communities_count: commInfoList.length || 1,
            });
          } else {
            setStats({
              nodes: rawNodes.length,
              edges: rawEdges.length,
              avg_degree: Number(((rawEdges.length * 2) / Math.max(1, rawNodes.length)).toFixed(2)),
              median_degree: 3,
              max_degree: Math.max(...rawNodes.map(n => n.degree || 1), 1),
              self_loops: 0,
              edge_density: Number((rawEdges.length / Math.max(1, rawNodes.length * (rawNodes.length - 1))).toFixed(4)),
              confidence_profile: { EXTRACTED: rawEdges.length },
              communities_count: commInfoList.length || 1,
            });
          }

          if (godsRes && godsRes.hubs && godsRes.hubs.length > 0) {
            setGodNodes(godsRes.hubs.map((h: any) => ({
              id: h.id,
              label: h.label || h.id,
              score: h.score,
              kind: h.kind,
              file: h.file,
            })));
          } else {
            // Local hubs computation
            const sortedByDeg = [...rawNodes].sort((a, b) => (b.degree || 0) - (a.degree || 0)).slice(0, 25);
            setGodNodes(sortedByDeg.map(n => ({
              id: n.id,
              label: n.label,
              score: n.degree || 1,
              kind: n.kind,
              file: n.file,
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

    initData();
  }, []);

  const handleSelectNodeById = (id: string) => {
    const node = nodes.find(n => n.id === id);
    if (node) {
      setSelectedNode(node);
      setFocusId(id);
    }
  };

  // Distinct-neighbour count per node id (drives "N connected nodes" labels).
  const neighborCountMap = useMemo(() => {
    const seen = new Map<string, Set<string>>();
    const add = (a: string, b: string) => {
      if (!seen.has(a)) seen.set(a, new Set());
      seen.get(a)!.add(b);
    };
    edges.forEach(e => {
      const s = typeof e.source === 'object' ? (e.source as any).id : e.source;
      const t = typeof e.target === 'object' ? (e.target as any).id : e.target;
      if (s === t) return;
      add(s, t);
      add(t, s);
    });
    const counts = new Map<string, number>();
    seen.forEach((set, id) => counts.set(id, set.size));
    return counts;
  }, [edges]);

  // Picking a search option: focus it on the canvas (neighbourhood highlight),
  // open the inspector with its connected nodes, collapse the options list.
  const handlePickSearchHit = (node: GraphNode) => {
    setSelectedNode(node);
    setFocusId(node.id);
    setSearchListOpen(false);
  };

  const handleFindPath = async (sourceId: string, targetId: string) => {
    if (window.location.protocol.startsWith('http')) {
      try {
        const res = await fetch(`/api/path?a=${encodeURIComponent(sourceId)}&b=${encodeURIComponent(targetId)}`);
        if (res.ok) {
          const data = await res.json();
          if (data.path && data.path.length > 0) {
            setActivePath(data.path);
            return data.path;
          }
        }
      } catch (_) {}
    }

    // In-memory BFS fallback
    const adj = new Map<string, string[]>();
    edges.forEach(e => {
      const s = typeof e.source === 'object' ? (e.source as any).id : e.source;
      const t = typeof e.target === 'object' ? (e.target as any).id : e.target;
      if (!adj.has(s)) adj.set(s, []);
      if (!adj.has(t)) adj.set(t, []);
      adj.get(s)!.push(t);
      adj.get(t)!.push(s);
    });

    const queue: string[][] = [[sourceId]];
    const visited = new Set<string>([sourceId]);
    while (queue.length > 0) {
      const p = queue.shift()!;
      const curr = p[p.length - 1];
      if (curr === targetId) {
        setActivePath(p);
        return p;
      }
      for (const nbr of (adj.get(curr) || [])) {
        if (!visited.has(nbr)) {
          visited.add(nbr);
          queue.push([...p, nbr]);
        }
      }
    }
    setActivePath(null);
    return null;
  };

  const handleRunQuery = async (question: string, mode: 'bfs' | 'dfs') => {
    if (window.location.protocol.startsWith('http')) {
      try {
        const res = await fetch(`/api/query?question=${encodeURIComponent(question)}&mode=${mode}`);
        if (res.ok) {
          const data = await res.json();
          setQueryResults(data);
          return;
        }
      } catch (_) {}
    }

    // Client-side query search
    const terms = question.toLowerCase().split(/\s+/).filter(Boolean);
    const startNodes = nodes.filter(n => {
      const l = (n.label || n.id).toLowerCase();
      return terms.some(t => l.includes(t));
    }).slice(0, 10).map(n => n.id);

    const adj = new Map<string, string[]>();
    edges.forEach(e => {
      const s = typeof e.source === 'object' ? (e.source as any).id : e.source;
      const t = typeof e.target === 'object' ? (e.target as any).id : e.target;
      if (!adj.has(s)) adj.set(s, []);
      adj.get(s)!.push(t);
    });

    const visited: string[] = [];
    const visitedSet = new Set<string>();
    const traversedEdges: any[] = [];
    const queue = [...startNodes];
    startNodes.forEach(id => visitedSet.add(id));

    while (queue.length > 0 && visited.length < 50) {
      const curr = mode === 'bfs' ? queue.shift()! : queue.pop()!;
      visited.push(curr);
      for (const nxt of (adj.get(curr) || [])) {
        traversedEdges.push({ source: curr, target: nxt });
        if (!visitedSet.has(nxt)) {
          visitedSet.add(nxt);
          queue.push(nxt);
        }
      }
    }

    setQueryResults({
      question,
      start_nodes: startNodes,
      visited,
      edges: traversedEdges,
      hops: visited.length,
    });
  };

  const handleExport = (format: string) => {
    if (format === 'cypher') {
      const cypherLines = [
        ...nodes.map(n => `CREATE (:\`${n.kind || 'Node'}\` {id: "${n.id.replace(/"/g, '\\"')}", label: "${(n.label || n.id).replace(/"/g, '\\"')}"})`),
        ...edges.map(e => {
          const s = typeof e.source === 'object' ? (e.source as any).id : String(e.source);
          const t = typeof e.target === 'object' ? (e.target as any).id : String(e.target);
          return `MATCH (a {id: "${s.replace(/"/g, '\\"')}"}), (b {id: "${t.replace(/"/g, '\\"')}"}) CREATE (a)-[:\`${e.relation || 'RELATED_TO'}\`]->(b);`;
        })
      ].join('\n');
      const blob = new Blob([cypherLines], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'graph_export.cypher';
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    const data = {
      nodes,
      links: edges,
      stats,
      communities: communities.map(c => ({ id: c.id, label: c.label, size: c.size, cohesion: c.cohesion })),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'graph.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  // Search: keep ALL nodes on canvas; matches get highlighted & dimmed elsewhere.
  // useDeferredValue keeps typing instant even on huge graphs.
  const deferredSearch = useDeferredValue(globalSearch);
  const searchActive = deferredSearch.trim().length > 0;
  const searchHits: GraphNode[] = useMemo(() => {
    const q = deferredSearch.trim().toLowerCase();
    if (!q) return [];
    return nodes.filter(n =>
      (n.label || '').toLowerCase().includes(q) ||
      (n.id || '').toLowerCase().includes(q) ||
      (n.file || (n as any).source_file || '').toLowerCase().includes(q)
    );
  }, [deferredSearch, nodes]);
  const matchedIds = useMemo(() => new Set<string>(searchHits.map(n => n.id)), [searchHits]);
  const visibleHits = searchHits.slice(0, 12);
  const showOptions = searchActive && searchListOpen && visibleHits.length > 0;
  const selectedConnCount = selectedNode
    ? (neighborCountMap.get(selectedNode.id) ?? selectedNode.degree ?? 0)
    : 0;

  // Keep the keyboard-highlighted option inside the dropdown's scroll viewport.
  const optionRefs = useRef<(HTMLDivElement | null)[]>([]);
  useEffect(() => {
    optionRefs.current[activeSearchIndex]?.scrollIntoView({ block: 'nearest' });
  }, [activeSearchIndex]);

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
          <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', position: 'relative' }}>
            <div style={{ position: 'relative' }}>
              <Search size={14} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search nodes, files, functions..."
                value={globalSearch}
                onChange={e => {
                  setGlobalSearch(e.target.value);
                  setSearchListOpen(true);
                  setActiveSearchIndex(0);
                }}
                onFocus={() => {
                  if (globalSearch.trim().length > 0) setSearchListOpen(true);
                }}
                onKeyDown={e => {
                  if (e.key === 'Escape') {
                    if (searchListOpen && searchActive) {
                      setSearchListOpen(false);
                    } else {
                      setGlobalSearch('');
                      setSelectedNode(null);
                    }
                    e.currentTarget.blur();
                  } else if (e.key === 'ArrowDown' && showOptions) {
                    e.preventDefault();
                    setActiveSearchIndex(i => Math.min(i + 1, visibleHits.length - 1));
                  } else if (e.key === 'ArrowUp' && showOptions) {
                    e.preventDefault();
                    setActiveSearchIndex(i => Math.max(i - 1, 0));
                  } else if (e.key === 'Enter') {
                    const hit = visibleHits[activeSearchIndex] || visibleHits[0];
                    if (hit) handlePickSearchHit(hit);
                  }
                }}
                style={{
                  width: '100%',
                  padding: '6px 26px 6px 30px',
                  borderRadius: 6,
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: 12,
                  outline: 'none',
                }}
              />
              {searchActive && (
                <button
                  onClick={() => { setGlobalSearch(''); setSelectedNode(null); setSearchListOpen(true); }}
                  title="Clear search & focus"
                  style={{ position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)', padding: '0 5px', fontSize: 13, lineHeight: 1, background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Focus chip: the picked search option + its connection count.
                Canvas keeps this node + its neighbours lit, everything else dimmed. */}
            {selectedNode && !showOptions && (
              <div style={{
                marginTop: 6,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 8px',
                borderRadius: 6,
                background: 'rgba(56, 189, 248, 0.08)',
                border: '1px solid rgba(56, 189, 248, 0.35)',
              }}>
                <Crosshair size={13} color="#38bdf8" style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {selectedNode.label || selectedNode.id}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    {selectedConnCount} connected node{selectedConnCount === 1 ? '' : 's'} shown on canvas & panel →
                  </div>
                </div>
                <button
                  onClick={() => setSelectedNode(null)}
                  title="Clear focus (show full graph)"
                  style={{ flexShrink: 0, padding: '0 5px', fontSize: 12, lineHeight: 1, background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                >
                  ✕
                </button>
              </div>
            )}

            {searchActive && searchListOpen && (
              <div style={{
                marginTop: 6,
                maxHeight: 260,
                overflowY: 'auto',
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                fontSize: 11,
              }}>
                {searchHits.length === 0 ? (
                  <div style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>no matches for “{globalSearch.trim()}”</div>
                ) : (
                  <>
                    {visibleHits.map((h, idx) => (
                      <div
                        key={h.id}
                        ref={el => { optionRefs.current[idx] = el; }}
                        onClick={() => handlePickSearchHit(h)}
                        onMouseEnter={() => setActiveSearchIndex(idx)}
                        style={{
                          padding: '6px 10px',
                          cursor: 'pointer',
                          borderBottom: '1px solid var(--border)',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          gap: 8,
                          background: idx === activeSearchIndex ? 'var(--bg-hover)' : 'transparent',
                        }}
                      >
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-primary)' }}>
                          {h.label || h.id}
                        </span>
                        <span style={{ color: 'var(--text-muted)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6 }}>
                          {h.kind && <span style={{ color: 'var(--accent)' }}>{h.kind}</span>}
                          <span title="connected nodes">{neighborCountMap.get(h.id) ?? h.degree ?? 0} links</span>
                        </span>
                      </div>
                    ))}
                    {searchHits.length > visibleHits.length && (
                      <div style={{ padding: '6px 10px', color: 'var(--text-muted)' }}>
                        +{searchHits.length - visibleHits.length} more matches ({searchHits.length} total)
                      </div>
                    )}
                    <div style={{ padding: '4px 10px', color: 'var(--text-muted)' }}>
                      {searchHits.length <= visibleHits.length ? `${searchHits.length} match${searchHits.length === 1 ? '' : 'es'} · ` : ''}
                      ↑↓ navigate · Enter opens connections · Esc closes
                    </div>
                  </>
                )}
              </div>
            )}
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
            nodes={nodes}
            edges={edges}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            highlightedCommunity={highlightedCommunity}
            activePath={activePath}
            communityColors={COMMUNITY_COLORS}
            searchQuery={searchActive ? globalSearch.trim().toLowerCase() : null}
            matchedIds={matchedIds}
            focusId={focusId}
            onFocusHandled={() => setFocusId(null)}
          />
        </div>

        {/* Right: Node Inspector Drawer */}
        {selectedNode && (
          <NodeInspector
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onSelectNodeById={handleSelectNodeById}
            communityColors={COMMUNITY_COLORS}
            allEdges={edges}
            allNodes={nodes}
          />
        )}
      </div>
    </div>
  );
};
