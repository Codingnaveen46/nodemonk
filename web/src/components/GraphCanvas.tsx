import React, { useRef, useEffect, useCallback, useState } from 'react';
import * as d3 from 'd3-force';
import { GraphNode, GraphEdge } from '../types';
import { ZoomIn, ZoomOut, Play, Pause, RotateCcw, ArrowRight, Tag } from 'lucide-react';

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
  const [showArrows, setShowArrows] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(true);

  // Node ID to Node map for fast lookups
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  // Adjacency map: nodeId -> Map<neighborId, { relation: string, confidence: string, isOutgoing: boolean }>
  const adjMapRef = useRef<Map<string, Map<string, { relation: string; confidence: string; isOutgoing: boolean }>>>(new Map());

  // Store active simulation links
  const simLinksRef = useRef<Array<{ source: GraphNode; target: GraphNode; relation: string; confidence: string }>>([]);

  // Initialize simulation
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

    const adj = new Map<string, Map<string, { relation: string; confidence: string; isOutgoing: boolean }>>();
    const simLinks: Array<{ source: GraphNode; target: GraphNode; relation: string; confidence: string }> = [];

    edges.forEach(e => {
      const sId = typeof e.source === 'string' ? e.source : e.source.id;
      const tId = typeof e.target === 'string' ? e.target : e.target.id;
      const sNode = nMap.get(sId);
      const tNode = nMap.get(tId);
      if (sNode && tNode) {
        const rel = e.relation || 'links';
        const conf = e.confidence || 'EXTRACTED';

        simLinks.push({
          source: sNode,
          target: tNode,
          relation: rel,
          confidence: conf,
        });

        if (!adj.has(sId)) adj.set(sId, new Map());
        if (!adj.has(tId)) adj.set(tId, new Map());
        adj.get(sId)!.set(tId, { relation: rel, confidence: conf, isOutgoing: true });
        adj.get(tId)!.set(sId, { relation: rel, confidence: conf, isOutgoing: false });
      }
    });

    adjMapRef.current = adj;
    simLinksRef.current = simLinks;

    // Build force simulation
    const sim = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, any>(simLinks).id(d => d.id).distance(65).strength(0.35))
      .force('charge', d3.forceManyBody().strength(-140).distanceMax(600))
      .force('center', d3.forceCenter(0, 0).strength(0.05))
      .force('collision', d3.forceCollide().radius(14))
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
    const activeAdj = activeNode ? adjMapRef.current.get(activeNode.id) : null;

    // 1. Draw Edges
    const linksToDraw = simLinksRef.current;
    linksToDraw.forEach(link => {
      const s = link.source;
      const t = link.target;
      if (!s || !t || s.x === undefined || s.y === undefined || t.x === undefined || t.y === undefined) return;

      const isPathEdge = pathSet && pathSet.has(s.id) && pathSet.has(t.id);
      const isConnected = activeNode && (s.id === activeNode.id || t.id === activeNode.id);
      const isDimmed = (activeNode || pathSet) && !isConnected && !isPathEdge;

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);

      if (isPathEdge) {
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = Math.max(3.5 / transform.k, 3);
        ctx.setLineDash([]);
      } else if (isConnected) {
        const isOutgoing = s.id === activeNode.id;
        ctx.strokeStyle = isOutgoing ? '#10b981' : '#38bdf8';
        ctx.lineWidth = Math.max(2.8 / transform.k, 2.5);
        ctx.setLineDash([]);
      } else if (isDimmed) {
        ctx.strokeStyle = 'rgba(75, 85, 99, 0.12)';
        ctx.lineWidth = Math.max(0.8 / transform.k, 0.8);
        ctx.setLineDash([]);
      } else {
        // Normal visible connection
        if (link.confidence === 'EXTRACTED') {
          ctx.strokeStyle = 'rgba(148, 163, 184, 0.55)'; // Crisp light slate
          ctx.lineWidth = Math.max(1.3 / transform.k, 1.2);
          ctx.setLineDash([]);
        } else if (link.confidence === 'AMBIGUOUS') {
          ctx.strokeStyle = 'rgba(245, 158, 11, 0.65)'; // Amber
          ctx.lineWidth = Math.max(1.3 / transform.k, 1.2);
          ctx.setLineDash([3 / transform.k, 3 / transform.k]);
        } else {
          ctx.strokeStyle = 'rgba(96, 165, 250, 0.6)'; // Blue Inferred
          ctx.lineWidth = Math.max(1.3 / transform.k, 1.2);
          ctx.setLineDash([5 / transform.k, 4 / transform.k]);
        }
      }
      ctx.stroke();

      // 2. Draw Arrowheads
      if (showArrows && (isConnected || isPathEdge || (transform.k > 0.85 && !isDimmed))) {
        const angle = Math.atan2(t.y - s.y, t.x - s.x);
        const headlen = isConnected || isPathEdge ? Math.max(9 / transform.k, 8) : Math.max(6 / transform.k, 5);
        const targetR = Math.max(4, Math.min(14, 3 + (t.degree || 1) * 0.4));
        const arrowX = t.x - Math.cos(angle) * (targetR + 3);
        const arrowY = t.y - Math.sin(angle) * (targetR + 3);

        ctx.fillStyle = isPathEdge ? '#38bdf8' :
          isConnected ? (s.id === activeNode.id ? '#10b981' : '#38bdf8') :
          'rgba(148, 163, 184, 0.7)';

        ctx.beginPath();
        ctx.moveTo(arrowX, arrowY);
        ctx.lineTo(arrowX - headlen * Math.cos(angle - Math.PI / 7), arrowY - headlen * Math.sin(angle - Math.PI / 7));
        ctx.lineTo(arrowX - headlen * Math.cos(angle + Math.PI / 7), arrowY - headlen * Math.sin(angle + Math.PI / 7));
        ctx.closePath();
        ctx.fill();
      }

      // 3. Draw Edge Relation Labels
      if (showEdgeLabels && (isConnected || (transform.k > 1.4 && !isDimmed))) {
        const midX = (s.x + t.x) / 2;
        const midY = (s.y + t.y) / 2;
        ctx.font = `${Math.max(9, 10 / transform.k)}px sans-serif`;
        ctx.fillStyle = isConnected ? '#f3f4f6' : 'rgba(209, 213, 219, 0.7)';
        ctx.fillText(link.relation || 'links', midX + 3, midY - 3);
      }
    });

    ctx.setLineDash([]);

    // 4. Draw Nodes
    nodes.forEach(n => {
      if (n.x === undefined || n.y === undefined) return;

      const isSelected = selectedNode?.id === n.id;
      const isHovered = hoveredNode?.id === n.id;
      const isPathNode = pathSet && pathSet.has(n.id);
      const isNeighbor = activeAdj && activeAdj.has(n.id);
      const isSelf = activeNode && activeNode.id === n.id;
      const isSameComm = highlightedCommunity !== null && n.community === highlightedCommunity;

      let radius = Math.max(4, Math.min(15, 3.5 + (n.degree || 1) * 0.45));
      if (isSelected || isHovered) radius += 2.5;

      const color = (n.community !== undefined && communityColors[n.community]) || '#4f8cff';

      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);

      let alpha = 1;
      if (pathSet) {
        alpha = isPathNode ? 1 : 0.15;
      } else if (activeNode) {
        alpha = isSelf || isNeighbor ? 1 : 0.18;
      } else if (highlightedCommunity !== null) {
        alpha = isSameComm ? 1 : 0.18;
      }

      ctx.fillStyle = color;
      ctx.globalAlpha = alpha;
      ctx.fill();

      // Outer rings & glow
      if (isSelected || isPathNode) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = Math.max(3 / transform.k, 2.5);
        ctx.stroke();
      } else if (isNeighbor) {
        const info = activeAdj!.get(n.id);
        ctx.strokeStyle = info?.isOutgoing ? '#10b981' : '#38bdf8';
        ctx.lineWidth = Math.max(2.2 / transform.k, 2);
        ctx.stroke();
      } else if (isHovered || isSameComm) {
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(2 / transform.k, 2);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;

      // Draw node labels
      const showLabel = isSelected || isHovered || isPathNode || isNeighbor ||
        (transform.k > 1.1 && alpha > 0.5) ||
        (transform.k > 0.6 && (n.degree || 0) > 6);

      if (showLabel) {
        ctx.font = `${Math.max(10, 11 / transform.k)}px sans-serif`;
        ctx.fillStyle = alpha > 0.5 ? '#f3f4f6' : 'rgba(156, 163, 175, 0.4)';
        ctx.fillText(n.label || n.id, n.x + radius + 5, n.y + 4);
      }
    });

    ctx.restore();
  }, [nodes, edges, selectedNode, hoveredNode, highlightedCommunity, activePath, communityColors, transform, showArrows, showEdgeLabels]);

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
      const r = Math.max(7, 5 + (n.degree || 1) * 0.45);
      if (dx * dx + dy * dy <= r * r * 1.6) {
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

      {/* Floating Viewport & Visualization Controls */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        right: 20,
        display: 'flex',
        gap: 6,
        background: 'rgba(17, 24, 39, 0.9)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 4,
        zIndex: 10,
      }}>
        <button
          onClick={() => setShowArrows(!showArrows)}
          title={showArrows ? "Hide Directional Arrows" : "Show Directional Arrows"}
          style={{
            background: showArrows ? 'var(--bg-hover)' : 'transparent',
            border: showArrows ? '1px solid var(--accent)' : '1px solid transparent',
            color: showArrows ? 'var(--accent)' : 'var(--text-secondary)',
            padding: 6,
            borderRadius: 4,
            display: 'flex',
          }}
        >
          <ArrowRight size={16} />
        </button>
        <button
          onClick={() => setShowEdgeLabels(!showEdgeLabels)}
          title={showEdgeLabels ? "Hide Edge Relation Labels" : "Show Edge Relation Labels"}
          style={{
            background: showEdgeLabels ? 'var(--bg-hover)' : 'transparent',
            border: showEdgeLabels ? '1px solid var(--accent)' : '1px solid transparent',
            color: showEdgeLabels ? 'var(--accent)' : 'var(--text-secondary)',
            padding: 6,
            borderRadius: 4,
            display: 'flex',
          }}
        >
          <Tag size={16} />
        </button>
        <button
          onClick={() => setTransform(t => ({ ...t, k: Math.min(10, t.k * 1.25) }))}
          title="Zoom In"
          style={{ background: 'transparent', border: '1px solid transparent', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => setTransform(t => ({ ...t, k: Math.max(0.1, t.k * 0.8) }))}
          title="Zoom Out"
          style={{ background: 'transparent', border: '1px solid transparent', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomOut size={16} />
        </button>
        <button
          onClick={resetView}
          title="Reset View"
          style={{ background: 'transparent', border: '1px solid transparent', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <RotateCcw size={16} />
        </button>
        <button
          onClick={toggleSimulation}
          title={simRunning ? "Pause Physics" : "Resume Physics"}
          style={{ background: 'transparent', border: '1px solid transparent', color: simRunning ? 'var(--accent)' : 'var(--text-secondary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          {simRunning ? <Pause size={16} /> : <Play size={16} />}
        </button>
      </div>

      {/* Node & Connection Legend Badge */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        left: 20,
        background: 'rgba(17, 24, 39, 0.9)',
        backdropFilter: 'blur(8px)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 12,
        color: 'var(--text-secondary)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        pointerEvents: 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span>Nodes: <strong style={{ color: 'var(--text-primary)' }}>{nodes.length}</strong></span>
          <span>Edges: <strong style={{ color: 'var(--text-primary)' }}>{edges.length}</strong></span>
          <span style={{ color: 'var(--success)', fontWeight: 600 }}>Unlimited Engine</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 14, height: 2, background: 'rgba(148, 163, 184, 0.85)' }} />
            <span>Extracted</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 14, height: 2, borderTop: '2px dashed #60a5fa' }} />
            <span>Inferred</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 14, height: 2, borderTop: '2px dotted #f59e0b' }} />
            <span>Ambiguous</span>
          </div>
        </div>
      </div>
    </div>
  );
};
