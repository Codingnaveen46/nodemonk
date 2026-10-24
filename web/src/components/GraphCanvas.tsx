import React, { useRef, useEffect, useCallback, useState } from 'react';
import * as d3 from 'd3-force';
import { GraphNode, GraphEdge } from '../types';
import { ZoomIn, ZoomOut, Maximize2, Play, Pause, RotateCcw } from 'lucide-react';

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNode: GraphNode | null;
  onSelectNode: (node: GraphNode | null) => void;
  highlightedCommunity: number | null;
  activePath: string[] | null;
  communityColors: Record<number, string>;
}

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  nodes,
  edges,
  selectedNode,
  onSelectNode,
  highlightedCommunity,
  activePath,
  communityColors,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, d3.SimulationLinkDatum<GraphNode>> | null>(null);

  // Transform state for pan and zoom
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [simRunning, setSimRunning] = useState(true);

  // Node ID to Node map for fast lookups
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  // Adjacency set for fast neighbor lookup during hover: "id1->id2" or "id1-id2"
  const adjSetRef = useRef<Set<string>>(new Set());

  // Initialize nodes and edges in simulation
  useEffect(() => {
    if (!nodes.length) return;

    const nMap = new Map<string, GraphNode>();
    nodes.forEach(n => {
      nMap.set(n.id, n);
      if (n.x === undefined || n.y === undefined) {
        n.x = (Math.random() - 0.5) * 800;
        n.y = (Math.random() - 0.5) * 600;
      }
    });
    nodeMapRef.current = nMap;

    const adj = new Set<string>();
    const simLinks: Array<{ source: GraphNode; target: GraphNode; relation?: string; confidence?: string }> = [];

    edges.forEach(e => {
      const sId = typeof e.source === 'string' ? e.source : e.source.id;
      const tId = typeof e.target === 'string' ? e.target : e.target.id;
      const sNode = nMap.get(sId);
      const tNode = nMap.get(tId);
      if (sNode && tNode) {
        simLinks.push({
          source: sNode,
          target: tNode,
          relation: e.relation,
          confidence: e.confidence,
        });
        adj.add(`${sId}|${tId}`);
        adj.add(`${tId}|${sId}`);
      }
    });
    adjSetRef.current = adj;

    // Build force simulation
    const sim = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, any>(simLinks).id(d => d.id).distance(50).strength(0.3))
      .force('charge', d3.forceManyBody().strength(-120).distanceMax(500))
      .force('center', d3.forceCenter(0, 0).strength(0.05))
      .force('collision', d3.forceCollide().radius(12))
      .alphaDecay(0.02)
      .on('tick', () => {
        draw();
      });

    simulationRef.current = sim;
    setSimRunning(true);

    return () => {
      sim.stop();
    };
  }, [nodes, edges]);

  // Handle Resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        draw();
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Main Draw Function
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    // Apply pan and zoom
    ctx.translate(width / 2 + transform.x, height / 2 + transform.y);
    ctx.scale(transform.k, transform.k);

    const activeNode = hoveredNode || selectedNode;
    const pathSet = activePath ? new Set(activePath) : null;

    // Draw Edges
    edges.forEach(e => {
      const s = typeof e.source === 'string' ? nodeMapRef.current.get(e.source) : e.source;
      const t = typeof e.target === 'string' ? nodeMapRef.current.get(e.target) : e.target;
      if (!s || !t || s.x === undefined || s.y === undefined || t.x === undefined || t.y === undefined) return;

      const isPathEdge = pathSet && pathSet.has(s.id) && pathSet.has(t.id);
      const isConnected = activeNode && (s.id === activeNode.id || t.id === activeNode.id);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);

      if (isPathEdge) {
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 3 / transform.k;
        ctx.setLineDash([]);
      } else if (isConnected) {
        ctx.strokeStyle = '#60a5fa';
        ctx.lineWidth = 2 / transform.k;
        ctx.setLineDash([]);
      } else {
        if (activeNode || pathSet) {
          ctx.strokeStyle = 'rgba(75, 85, 99, 0.15)';
        } else {
          ctx.strokeStyle = e.confidence === 'INFERRED' ? 'rgba(156, 163, 175, 0.25)' : 'rgba(107, 114, 128, 0.35)';
        }
        ctx.lineWidth = 1 / transform.k;
        if (e.confidence === 'INFERRED') {
          ctx.setLineDash([4 / transform.k, 4 / transform.k]);
        } else if (e.confidence === 'AMBIGUOUS') {
          ctx.setLineDash([2 / transform.k, 2 / transform.k]);
          ctx.strokeStyle = 'rgba(245, 158, 11, 0.4)';
        } else {
          ctx.setLineDash([]);
        }
      }
      ctx.stroke();
    });

    // Draw Nodes
    nodes.forEach(n => {
      if (n.x === undefined || n.y === undefined) return;

      const isSelected = selectedNode?.id === n.id;
      const isHovered = hoveredNode?.id === n.id;
      const isPathNode = pathSet && pathSet.has(n.id);
      const isNeighbor = activeNode && (adjSetRef.current.has(`${activeNode.id}|${n.id}`) || activeNode.id === n.id);
      const isSameComm = highlightedCommunity !== null && n.community === highlightedCommunity;

      let radius = Math.max(3, Math.min(14, 3 + (n.degree || 1) * 0.4));
      if (isSelected || isHovered) radius += 2;

      const color = (n.community !== undefined && communityColors[n.community]) || '#4f8cff';

      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);

      let alpha = 1;
      if (pathSet) {
        alpha = isPathNode ? 1 : 0.15;
      } else if (activeNode) {
        alpha = isNeighbor ? 1 : 0.2;
      } else if (highlightedCommunity !== null) {
        alpha = isSameComm ? 1 : 0.15;
      }

      ctx.fillStyle = color;
      ctx.globalAlpha = alpha;
      ctx.fill();

      // Outer ring for selected or hub nodes
      if (isSelected || isPathNode) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2.5 / transform.k;
        ctx.stroke();
      } else if (isHovered || isSameComm) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2 / transform.k;
        ctx.stroke();
      }

      ctx.globalAlpha = 1;

      // Draw labels when zoomed in or when selected/hovered/high degree
      const showLabel = isSelected || isHovered || isPathNode || (transform.k > 1.2 && alpha > 0.5) || (transform.k > 0.7 && (n.degree || 0) > 8);
      if (showLabel) {
        ctx.font = `${Math.max(10, 11 / transform.k)}px sans-serif`;
        ctx.fillStyle = alpha > 0.5 ? '#f3f4f6' : 'rgba(156, 163, 175, 0.4)';
        ctx.fillText(n.label || n.id, n.x + radius + 4, n.y + 4);
      }
    });

    ctx.restore();
  }, [nodes, edges, selectedNode, hoveredNode, highlightedCommunity, activePath, communityColors, transform]);

  useEffect(() => {
    draw();
  }, [draw]);

  // Wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    const newK = Math.max(0.1, Math.min(10, transform.k * zoomFactor));

    setTransform(prev => ({
      ...prev,
      k: newK,
    }));
  };

  // Convert mouse coord to graph space
  const screenToGraph = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;
    const width = rect.width;
    const height = rect.height;

    return {
      x: (mouseX - width / 2 - transform.x) / transform.k,
      y: (mouseY - height / 2 - transform.y) / transform.k,
    };
  };

  const findNodeAt = (x: number, y: number) => {
    for (const n of nodes) {
      if (n.x === undefined || n.y === undefined) continue;
      const dx = n.x - x;
      const dy = n.y - y;
      const r = Math.max(6, 4 + (n.degree || 1) * 0.4);
      if (dx * dx + dy * dy <= r * r * 1.5) {
        return n;
      }
    }
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setTransform(prev => ({
        ...prev,
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      }));
    } else {
      const gPos = screenToGraph(e.clientX, e.clientY);
      const hit = findNodeAt(gPos.x, gPos.y);
      setHoveredNode(hit);
    }
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    setIsDragging(false);
    const gPos = screenToGraph(e.clientX, e.clientY);
    const hit = findNodeAt(gPos.x, gPos.y);
    onSelectNode(hit);
  };

  const resetView = () => {
    setTransform({ x: 0, y: 0, k: 1 });
  };

  const toggleSimulation = () => {
    if (!simulationRef.current) return;
    if (simRunning) {
      simulationRef.current.stop();
      setSimRunning(false);
    } else {
      simulationRef.current.alpha(0.3).restart();
      setSimRunning(true);
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      <canvas
        ref={canvasRef}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{
          width: '100%',
          height: '100%',
          cursor: isDragging ? 'grabbing' : hoveredNode ? 'pointer' : 'grab',
          display: 'block',
        }}
      />

      {/* Floating Viewport Controls */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        right: 20,
        display: 'flex',
        gap: 6,
        background: 'rgba(17, 24, 39, 0.85)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 4,
        zIndex: 10,
      }}>
        <button
          onClick={() => setTransform(t => ({ ...t, k: Math.min(10, t.k * 1.25) }))}
          title="Zoom In"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => setTransform(t => ({ ...t, k: Math.max(0.1, t.k * 0.8) }))}
          title="Zoom Out"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomOut size={16} />
        </button>
        <button
          onClick={resetView}
          title="Reset View"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <RotateCcw size={16} />
        </button>
        <button
          onClick={toggleSimulation}
          title={simRunning ? "Pause Physics" : "Resume Physics"}
          style={{ background: 'transparent', border: 'none', color: simRunning ? 'var(--accent)' : 'var(--text-secondary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          {simRunning ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>

      {/* Node Count Badge */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        left: 20,
        background: 'rgba(17, 24, 39, 0.85)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '6px 12px',
        fontSize: 12,
        color: 'var(--text-secondary)',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
      }}>
        <span>Nodes: <strong style={{ color: 'var(--text-primary)' }}>{nodes.length}</strong></span>
        <span>Edges: <strong style={{ color: 'var(--text-primary)' }}>{edges.length}</strong></span>
        <span style={{ color: 'var(--success)' }}>Unlimited Engine</span>
      </div>
    </div>
  );
};
