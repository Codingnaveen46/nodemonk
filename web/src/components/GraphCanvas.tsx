import React, { useRef, useEffect, useCallback, useState } from 'react';
import * as d3 from 'd3-force';
import { GraphNode, GraphEdge } from '../types';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Play,
  Pause,
  GitBranch,
  Layers,
  Sparkles,
  Tag,
  ArrowRight,
  Maximize2
} from 'lucide-react';

interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNode: GraphNode | null;
  onSelectNode: (node: GraphNode | null) => void;
  highlightedCommunity: number | null;
  activePath: string[] | null;
  communityColors: Record<number, string>;
}

type LayoutMode = 'architecture' | 'islands' | 'force';

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

  // View & Layout State
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 0.85 });
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('islands');
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [draggedNode, setDraggedNode] = useState<GraphNode | null>(null);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [simRunning, setSimRunning] = useState(true);
  const [showArrows, setShowArrows] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [nodeViewMode, setNodeViewMode] = useState<'cards' | 'dots'>('cards');

  // Lookups & Cache
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  const adjMapRef = useRef<Map<string, Map<string, { relation: string; confidence: string; isOutgoing: boolean }>>>(new Map());
  const simLinksRef = useRef<Array<{ source: GraphNode; target: GraphNode; relation: string; confidence: string }>>([]);
  const commCentersRef = useRef<Record<number, { x: number; y: number; label: string }>>({});

  // 1. Compute Architectural Tiers for Architecture Mode
  const computeArchitecturePositions = useCallback(() => {
    const tierMap: Record<number, GraphNode[]> = { 0: [], 1: [], 2: [], 3: [], 4: [], 5: [] };

    nodes.forEach(n => {
      const path = (n.file || n.source_file || n.id).toLowerCase();
      if (path.includes('cli') || path.includes('__main__') || path.includes('hook')) {
        tierMap[0].push(n); // Tier 0: Entrypoints
      } else if (path.includes('pipeline') || path.includes('build') || path.includes('detect') || path.includes('manifest')) {
        tierMap[1].push(n); // Tier 1: Orchestration
      } else if (path.includes('graph') || path.includes('cluster') || path.includes('analyze') || path.includes('query')) {
        tierMap[2].push(n); // Tier 2: Core Graph Engines
      } else if (path.includes('extract') || path.includes('ast') || path.includes('resolution') || path.includes('ingest') || path.includes('security')) {
        tierMap[3].push(n); // Tier 3: Extractors & Ingestion
      } else if (path.includes('export') || path.includes('serve') || path.includes('viz') || path.includes('mcp') || path.includes('report')) {
        tierMap[4].push(n); // Tier 4: Exporters & APIs
      } else {
        tierMap[5].push(n); // Tier 5: Tests / Docs / External
      }
    });

    const tierX = [-700, -380, -60, 260, 580, 900];
    Object.entries(tierMap).forEach(([tStr, tNodes]) => {
      const t = Number(tStr);
      const startX = tierX[t] || 0;
      const count = tNodes.length;
      const totalH = Math.max(500, count * 36);
      const startY = -totalH / 2;

      tNodes.forEach((n, idx) => {
        n.x = startX + (Math.random() - 0.5) * 40;
        n.y = startY + (idx / Math.max(1, count - 1)) * totalH;
        n.vx = 0;
        n.vy = 0;
      });
    });
  }, [nodes]);

  // 2. Compute Community Islands
  const computeIslandsPositions = useCallback(() => {
    const comms: Record<number, GraphNode[]> = {};
    nodes.forEach(n => {
      const c = n.community ?? -1;
      if (!comms[c]) comms[c] = [];
      comms[c].push(n);
    });

    const ckeys = Object.keys(comms).map(Number).sort((a, b) => comms[b].length - comms[a].length);
    const numComms = Math.max(1, ckeys.length);
    const baseDist = Math.max(800, 160 * Math.sqrt(numComms));
    const centers: Record<number, { x: number; y: number; label: string }> = {};

    ckeys.forEach((k, ki) => {
      const angle = (2 * Math.PI * ki) / numComms;
      const radius = (ki === 0 && comms[k].length > 30) ? 0 : baseDist * (0.4 + 0.6 * Math.sqrt((ki + 1) / numComms));
      centers[k] = {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        label: `Community ${k}`,
      };
    });
    commCentersRef.current = centers;

    ckeys.forEach(k => {
      const arr = comms[k];
      const center = centers[k] || { x: 0, y: 0 };
      const ringRadius = 25 + 18 * Math.sqrt(arr.length);
      arr.forEach((n, ni) => {
        const ang = (2 * Math.PI * ni) / arr.length;
        const r = (ni === 0 && arr.length > 3) ? 0 : (ringRadius * (0.3 + 0.7 * ((ni % 3 + 1) / 3)));
        n.x = center.x + Math.cos(ang) * r;
        n.y = center.y + Math.sin(ang) * r;
        n.vx = 0;
        n.vy = 0;
      });
    });
  }, [nodes]);

  // Setup simulation and positions
  useEffect(() => {
    if (!nodes.length) return;

    const nMap = new Map<string, GraphNode>();
    nodes.forEach(n => nMap.set(n.id, n));
    nodeMapRef.current = nMap;

    if (layoutMode === 'architecture') {
      computeArchitecturePositions();
    } else {
      computeIslandsPositions();
    }

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

    if (layoutMode === 'architecture') {
      // Architecture Mode: Static hierarchical layout, gentle relaxing
      if (simulationRef.current) simulationRef.current.stop();
      setSimRunning(false);
      draw();
      return;
    }

    // Force/Islands Simulation with fast convergence
    const centers = commCentersRef.current;
    const sim = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, any>(simLinks).id(d => d.id).distance(d => {
        const s = d.source as GraphNode;
        const t = d.target as GraphNode;
        return (s.community === t.community) ? 45 : 140;
      }).strength(d => {
        const s = d.source as GraphNode;
        const t = d.target as GraphNode;
        return (s.community === t.community) ? 0.35 : 0.05;
      }))
      .force('charge', d3.forceManyBody().strength(-100).distanceMax(450))
      .force('communityX', d3.forceX<GraphNode>(d => (centers[d.community ?? -1]?.x || 0)).strength(layoutMode === 'islands' ? 0.08 : 0.02))
      .force('communityY', d3.forceY<GraphNode>(d => (centers[d.community ?? -1]?.y || 0)).strength(layoutMode === 'islands' ? 0.08 : 0.02))
      .force('collision', d3.forceCollide<GraphNode>().radius(16))
      .alpha(0.8)
      .alphaDecay(0.025)
      .velocityDecay(0.4)
      .on('tick', () => {
        draw();
      })
      .on('end', () => {
        setSimRunning(false);
      });

    simulationRef.current = sim;
    setSimRunning(true);

    return () => {
      sim.stop();
    };
  }, [nodes, edges, layoutMode, computeArchitecturePositions, computeIslandsPositions]);

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

  // Helper to get Node Icon Glyph & Kind Color
  const getNodeMeta = (n: GraphNode) => {
    const kind = (n.kind || '').toLowerCase();
    const id = n.id.toLowerCase();
    if (kind === 'class' || id.startsWith('class::')) {
      return { glyph: 'C', badge: 'class', color: '#a855f7' };
    }
    if (kind === 'function' || id.includes('()')) {
      return { glyph: 'ƒ', badge: 'fn', color: '#3b82f6' };
    }
    if (id.startsWith('file::') || n.file) {
      return { glyph: '📄', badge: 'file', color: '#10b981' };
    }
    if (id.startsWith('module::') || id.includes('external')) {
      return { glyph: '🌐', badge: 'ext', color: '#9ca3af' };
    }
    return { glyph: '•', badge: 'sym', color: '#06b6d4' };
  };

  // Main Canvas Draw Function
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

    // 1. Draw Subtle Tech Grid Background
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.025)';
    ctx.lineWidth = 1;
    const gridSize = 40 * transform.k;
    const offsetX = (width / 2 + transform.x) % gridSize;
    const offsetY = (height / 2 + transform.y) % gridSize;
    for (let x = offsetX; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = offsetY; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }
    ctx.restore();

    // 2. Camera Transform
    ctx.translate(width / 2 + transform.x, height / 2 + transform.y);
    ctx.scale(transform.k, transform.k);

    const activeNode = hoveredNode || selectedNode;
    const pathSet = activePath ? new Set(activePath) : null;
    const activeAdj = activeNode ? adjMapRef.current.get(activeNode.id) : null;

    // 3. Draw Architectural Tier Headers if in Architecture Mode
    if (layoutMode === 'architecture' && transform.k > 0.4) {
      const headers = [
        { label: 'ENTRYPOINTS & CLI', x: -700, col: '#38bdf8' },
        { label: 'ORCHESTRATION & BUILD', x: -380, col: '#10b981' },
        { label: 'CORE GRAPH ENGINES', x: -60, col: '#f59e0b' },
        { label: 'EXTRACTORS & RESOLUTION', x: 260, col: '#8b5cf6' },
        { label: 'EXPORTERS & SERVERS', x: 580, col: '#ec4899' },
        { label: 'TESTS & ASSETS', x: 900, col: '#9ca3af' },
      ];
      ctx.font = 'bold 12px Inter, system-ui, sans-serif';
      headers.forEach(h => {
        ctx.fillStyle = `${h.col}18`;
        ctx.fillRect(h.x - 120, -520, 240, 26);
        ctx.strokeStyle = `${h.col}44`;
        ctx.strokeRect(h.x - 120, -520, 240, 26);
        ctx.fillStyle = h.col;
        ctx.fillText(h.label, h.x - 100, -502);
      });
    }

    // 4. Draw Community Island Halos in Islands Mode
    if (layoutMode === 'islands' && transform.k < 1.2) {
      const centers = commCentersRef.current;
      Object.entries(centers).forEach(([cidStr, center]) => {
        const cid = Number(cidStr);
        if (highlightedCommunity !== null && highlightedCommunity !== cid) return;
        const color = communityColors[cid] || '#3b82f6';
        ctx.beginPath();
        ctx.arc(center.x, center.y, 75, 0, Math.PI * 2);
        ctx.fillStyle = `${color}0d`; // 5% fill
        ctx.fill();
        ctx.strokeStyle = `${color}25`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      });
    }

    // 5. Draw Smooth Curved Edges
    const linksToDraw = simLinksRef.current;
    linksToDraw.forEach(link => {
      const s = link.source;
      const t = link.target;
      if (!s || !t || s.x === undefined || s.y === undefined || t.x === undefined || t.y === undefined) return;

      const isPathEdge = pathSet && pathSet.has(s.id) && pathSet.has(t.id);
      const isConnected = activeNode && (s.id === activeNode.id || t.id === activeNode.id);
      const isDimmed = (activeNode || pathSet) && !isConnected && !isPathEdge;

      // Calculate elegant quadratic bezier curve
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.hypot(dx, dy) || 1;
      const midX = (s.x + t.x) / 2;
      const midY = (s.y + t.y) / 2;

      // Subtle arc curve (perpendicular offset)
      const curveStrength = Math.min(25, dist * 0.08);
      const cpX = midX - (dy / dist) * curveStrength;
      const cpY = midY + (dx / dist) * curveStrength;

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.quadraticCurveTo(cpX, cpY, t.x, t.y);

      if (isPathEdge) {
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = Math.max(3.2 / transform.k, 3);
        ctx.setLineDash([]);
      } else if (isConnected) {
        const isOutgoing = s.id === activeNode.id;
        ctx.strokeStyle = isOutgoing ? '#10b981' : '#38bdf8';
        ctx.lineWidth = Math.max(2.6 / transform.k, 2.4);
        ctx.setLineDash([]);
      } else if (isDimmed) {
        ctx.strokeStyle = 'rgba(75, 85, 99, 0.1)';
        ctx.lineWidth = Math.max(0.7 / transform.k, 0.7);
        ctx.setLineDash([]);
      } else {
        if (link.confidence === 'EXTRACTED') {
          ctx.strokeStyle = 'rgba(148, 163, 184, 0.45)';
          ctx.lineWidth = Math.max(1.1 / transform.k, 1.1);
          ctx.setLineDash([]);
        } else if (link.confidence === 'AMBIGUOUS') {
          ctx.strokeStyle = 'rgba(245, 158, 11, 0.55)';
          ctx.lineWidth = Math.max(1.1 / transform.k, 1.1);
          ctx.setLineDash([3 / transform.k, 3 / transform.k]);
        } else {
          ctx.strokeStyle = 'rgba(96, 165, 250, 0.4)';
          ctx.lineWidth = Math.max(1.1 / transform.k, 1.1);
          ctx.setLineDash([5 / transform.k, 4 / transform.k]);
        }
      }
      ctx.stroke();

      // Draw Arrowheads on Bezier curve
      if (showArrows && (isConnected || isPathEdge || (transform.k > 1.1 && !isDimmed))) {
        // Tangent angle at curve end (t.x, t.y)
        const angle = Math.atan2(t.y - cpY, t.x - cpX);
        const headlen = isConnected || isPathEdge ? Math.max(8 / transform.k, 7) : Math.max(5 / transform.k, 5);
        const targetOffset = nodeViewMode === 'cards' && transform.k > 0.6 ? 16 : 8;
        const arrowX = t.x - Math.cos(angle) * targetOffset;
        const arrowY = t.y - Math.sin(angle) * targetOffset;

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

      // Draw Edge Relation Label
      if (showEdgeLabels && (isConnected || (transform.k > 1.6 && !isDimmed))) {
        ctx.font = `${Math.max(9, 10 / transform.k)}px sans-serif`;
        ctx.fillStyle = isConnected ? '#f3f4f6' : 'rgba(209, 213, 219, 0.7)';
        ctx.fillText(link.relation || 'links', cpX + 2, cpY - 2);
      }
    });

    ctx.setLineDash([]);

    // 6. Draw Nodes (Capsule Cards vs Minimal Dots)
    nodes.forEach(n => {
      if (n.x === undefined || n.y === undefined) return;

      const isSelected = selectedNode?.id === n.id;
      const isHovered = hoveredNode?.id === n.id;
      const isPathNode = pathSet && pathSet.has(n.id);
      const isNeighbor = activeAdj && activeAdj.has(n.id);
      const isSelf = activeNode && activeNode.id === n.id;
      const isSameComm = highlightedCommunity !== null && n.community === highlightedCommunity;

      const meta = getNodeMeta(n);
      const commColor = (n.community !== undefined && communityColors[n.community]) || '#4f8cff';

      let alpha = 1;
      if (pathSet) {
        alpha = isPathNode ? 1 : 0.15;
      } else if (activeNode) {
        alpha = isSelf || isNeighbor ? 1 : 0.18;
      } else if (highlightedCommunity !== null) {
        alpha = isSameComm ? 1 : 0.18;
      }

      const drawAsCard = nodeViewMode === 'cards' && (transform.k > 0.55 || isSelected || isHovered || isNeighbor);

      if (drawAsCard) {
        // --- High-End Capsule Card Rendering ---
        const labelText = (n.label || n.id).slice(0, 32);
        ctx.font = '500 11px Inter, system-ui, sans-serif';
        const textWidth = ctx.measureText(labelText).width;
        const cardW = Math.max(75, textWidth + 34);
        const cardH = 22;
        const cardX = n.x - cardW / 2;
        const cardY = n.y - cardH / 2;
        const r = 6; // rounded corners

        // Background shadow
        if (isSelected || isHovered) {
          ctx.shadowColor = isSelected ? '#ffffff' : commColor;
          ctx.shadowBlur = 12;
        } else {
          ctx.shadowBlur = 0;
        }

        // Card Body
        ctx.beginPath();
        ctx.roundRect(cardX, cardY, cardW, cardH, r);
        ctx.fillStyle = alpha > 0.5 ? 'rgba(15, 23, 42, 0.94)' : 'rgba(15, 23, 42, 0.3)';
        ctx.fill();

        // Card Border
        ctx.lineWidth = isSelected ? 2 : isHovered || isNeighbor ? 1.5 : 1;
        ctx.strokeStyle = isSelected ? '#ffffff' : isHovered ? '#38bdf8' : isNeighbor ? commColor : `${commColor}88`;
        ctx.stroke();
        ctx.shadowBlur = 0; // reset shadow

        if (alpha > 0.4) {
          // Left Glyph Tag
          ctx.beginPath();
          ctx.roundRect(cardX + 2, cardY + 2, 18, cardH - 4, 4);
          ctx.fillStyle = `${meta.color}25`;
          ctx.fill();
          ctx.font = 'bold 9px monospace';
          ctx.fillStyle = meta.color;
          ctx.textAlign = 'center';
          ctx.fillText(meta.glyph, cardX + 11, cardY + 14);

          // Card Label
          ctx.font = '500 11px Inter, system-ui, sans-serif';
          ctx.fillStyle = isSelected ? '#ffffff' : '#f3f4f6';
          ctx.textAlign = 'left';
          ctx.fillText(labelText, cardX + 25, cardY + 15);
        }
      } else {
        // --- Clean Circular Dot Rendering (when zoomed out) ---
        let radius = Math.max(3.5, Math.min(14, 3 + (n.degree || 1) * 0.45));
        if (isSelected || isHovered) radius += 2.5;

        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = commColor;
        ctx.globalAlpha = alpha;
        ctx.fill();

        if (isSelected || isPathNode) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = Math.max(2.5 / transform.k, 2);
          ctx.stroke();
        } else if (isHovered || isNeighbor) {
          ctx.strokeStyle = isHovered ? '#38bdf8' : commColor;
          ctx.lineWidth = Math.max(2 / transform.k, 1.8);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;

        // Label on hover/select in dot mode
        if (isSelected || isHovered || isNeighbor) {
          const text = n.label || n.id;
          ctx.font = '11px Inter, system-ui, sans-serif';
          const tw = ctx.measureText(text).width;
          ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
          ctx.fillRect(n.x + radius + 4, n.y - 10, tw + 8, 18);
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
          ctx.strokeRect(n.x + radius + 4, n.y - 10, tw + 8, 18);
          ctx.fillStyle = '#ffffff';
          ctx.textAlign = 'left';
          ctx.fillText(text, n.x + radius + 8, n.y + 3);
        }
      }
    });

    ctx.restore();
  }, [nodes, edges, selectedNode, hoveredNode, highlightedCommunity, activePath, communityColors, transform, showArrows, showEdgeLabels, layoutMode, nodeViewMode]);

  useEffect(() => {
    draw();
  }, [draw]);

  // Wheel zoom attached directly to canvas with { passive: false } to prevent passive listener warning
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      setTransform(prev => ({
        ...prev,
        k: Math.max(0.04, Math.min(8, prev.k * zoomFactor))
      }));
    };

    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      canvas.removeEventListener('wheel', onWheel);
    };
  }, []);

  // Screen to Graph coordinates
  const screenToGraph = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;
    return {
      x: (mouseX - rect.width / 2 - transform.x) / transform.k,
      y: (mouseY - rect.height / 2 - transform.y) / transform.k,
    };
  };

  const findNodeAt = (x: number, y: number) => {
    for (const n of nodes) {
      if (n.x === undefined || n.y === undefined) continue;
      const dx = n.x - x;
      const dy = n.y - y;
      const hitRadius = nodeViewMode === 'cards' && transform.k > 0.55 ? 30 : Math.max(10, 5 + (n.degree || 1) * 0.45);
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        return n;
      }
    }
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const gPos = screenToGraph(e.clientX, e.clientY);
    const hit = findNodeAt(gPos.x, gPos.y);

    if (hit) {
      setDraggedNode(hit);
      hit.fx = hit.x;
      hit.fy = hit.y;
      if (simulationRef.current) {
        simulationRef.current.alphaTarget(0.1).restart();
        setSimRunning(true);
      }
    } else {
      setIsDraggingCanvas(true);
      setDragStart({ x: e.clientX - transform.x, y: e.clientY - transform.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggedNode) {
      const gPos = screenToGraph(e.clientX, e.clientY);
      draggedNode.fx = gPos.x;
      draggedNode.fy = gPos.y;
      draggedNode.x = gPos.x;
      draggedNode.y = gPos.y;
      draw();
    } else if (isDraggingCanvas) {
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
    if (draggedNode) {
      draggedNode.fx = null;
      draggedNode.fy = null;
      setDraggedNode(null);
      if (simulationRef.current) {
        simulationRef.current.alphaTarget(0);
      }
    } else if (isDraggingCanvas) {
      setIsDraggingCanvas(false);
      const gPos = screenToGraph(e.clientX, e.clientY);
      const hit = findNodeAt(gPos.x, gPos.y);
      onSelectNode(hit);
    }
  };

  const resetView = () => {
    setTransform({ x: 0, y: 0, k: 0.85 });
  };

  const toggleSimulation = () => {
    if (!simulationRef.current) return;
    if (simRunning) {
      simulationRef.current.stop();
      setSimRunning(false);
    } else {
      simulationRef.current.alpha(0.35).restart();
      setSimRunning(true);
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: '#090d16' }}>
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        style={{
          width: '100%',
          height: '100%',
          cursor: isDraggingCanvas || draggedNode ? 'grabbing' : hoveredNode ? 'pointer' : 'grab',
          display: 'block',
        }}
      />

      {/* Top Layout Switcher Toolbar */}
      <div style={{
        position: 'absolute',
        top: 14,
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: 'rgba(15, 23, 42, 0.88)',
        backdropFilter: 'blur(10px)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '4px 6px',
        zIndex: 10,
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
      }}>
        <button
          onClick={() => setLayoutMode('islands')}
          title="Community Islands Layout"
          style={{
            background: layoutMode === 'islands' ? 'var(--bg-hover)' : 'transparent',
            border: layoutMode === 'islands' ? '1px solid var(--accent)' : '1px solid transparent',
            color: layoutMode === 'islands' ? 'var(--accent)' : 'var(--text-secondary)',
            padding: '5px 10px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Layers size={14} />
          <span>Islands</span>
        </button>

        <button
          onClick={() => setLayoutMode('architecture')}
          title="Architecture Pipeline Tiers (Entrypoint → Engine → Output)"
          style={{
            background: layoutMode === 'architecture' ? 'var(--bg-hover)' : 'transparent',
            border: layoutMode === 'architecture' ? '1px solid var(--accent)' : '1px solid transparent',
            color: layoutMode === 'architecture' ? 'var(--accent)' : 'var(--text-secondary)',
            padding: '5px 10px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <GitBranch size={14} />
          <span>Architecture Flow</span>
        </button>

        <button
          onClick={() => setLayoutMode('force')}
          title="Organic Force Constellation"
          style={{
            background: layoutMode === 'force' ? 'var(--bg-hover)' : 'transparent',
            border: layoutMode === 'force' ? '1px solid var(--accent)' : '1px solid transparent',
            color: layoutMode === 'force' ? 'var(--accent)' : 'var(--text-secondary)',
            padding: '5px 10px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Sparkles size={14} />
          <span>Organic</span>
        </button>

        <div style={{ width: 1, height: 16, background: 'var(--border)', margin: '0 4px' }} />

        {/* Card vs Dot View Switcher */}
        <button
          onClick={() => setNodeViewMode(m => m === 'cards' ? 'dots' : 'cards')}
          title="Toggle Capsule Cards vs Minimal Dots"
          style={{
            background: 'transparent',
            border: '1px solid transparent',
            color: 'var(--text-secondary)',
            padding: '5px 8px',
            borderRadius: 6,
            fontSize: 11,
          }}
        >
          {nodeViewMode === 'cards' ? 'Cards View' : 'Dots View'}
        </button>
      </div>

      {/* Floating Bottom-Right Controls */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        right: 20,
        display: 'flex',
        gap: 6,
        background: 'rgba(15, 23, 42, 0.9)',
        backdropFilter: 'blur(10px)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: 4,
        zIndex: 10,
      }}>
        <button
          onClick={() => setShowArrows(!showArrows)}
          title={showArrows ? 'Hide Directional Arrows' : 'Show Directional Arrows'}
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
          title={showEdgeLabels ? 'Hide Edge Relation Labels' : 'Show Edge Relation Labels'}
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
          onClick={() => setTransform(t => ({ ...t, k: Math.min(8, t.k * 1.25) }))}
          title="Zoom In"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => setTransform(t => ({ ...t, k: Math.max(0.04, t.k * 0.8) }))}
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
        {layoutMode !== 'architecture' && (
          <button
            onClick={toggleSimulation}
            title={simRunning ? 'Freeze Layout' : 'Settle Layout'}
            style={{
              background: simRunning ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
              border: simRunning ? '1px solid var(--accent)' : 'none',
              color: simRunning ? 'var(--accent)' : 'var(--text-secondary)',
              padding: 6,
              borderRadius: 4,
              display: 'flex',
            }}
          >
            {simRunning ? <Pause size={16} /> : <Play size={16} />}
          </button>
        )}
      </div>

      {/* Floating Bottom-Left Stats & Status */}
      <div style={{
        position: 'absolute',
        bottom: 20,
        left: 20,
        background: 'rgba(15, 23, 42, 0.9)',
        backdropFilter: 'blur(10px)',
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
          <span style={{ color: 'var(--success)', fontWeight: 600 }}>
            {layoutMode === 'architecture' ? 'Architecture Flow' : simRunning ? 'Settling...' : 'Stable'}
          </span>
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
