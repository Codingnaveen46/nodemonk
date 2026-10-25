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
  searchQuery?: string | null;
  matchedIds?: Set<string> | null;
  focusId?: string | null;
  onFocusHandled?: () => void;
}

type LayoutMode = 'architecture' | 'islands' | 'force';
type NodeViewMode = 'obsidian' | 'cards';

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  nodes,
  edges,
  selectedNode,
  onSelectNode,
  highlightedCommunity,
  activePath,
  communityColors,
  searchQuery = null,
  matchedIds = null,
  focusId = null,
  onFocusHandled,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simulationRef = useRef<d3.Simulation<GraphNode, d3.SimulationLinkDatum<GraphNode>> | null>(null);

  // View & Layout State — camera lives in a ref (no React render on zoom/pan)
  const transformRef = useRef({ x: 0, y: 0, k: 0.85 });
  const drawRef = useRef<() => void>(() => {});
  const rafRef = useRef(0);
  const scheduleDraw = useCallback(() => {
    if (rafRef.current) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = 0;
      drawRef.current();
    });
  }, []);
  const metaCacheRef = useRef<Map<string, { glyph: string; badge: string; color: string }>>(new Map());
  const labelWidthCacheRef = useRef<Map<string, number>>(new Map());
  const gridRef = useRef<{ cell: number; map: Map<string, GraphNode[]>; builtAt: number }>({ cell: 64, map: new Map(), builtAt: 0 });
  const hoverRafRef = useRef(0);
  const lastHoverIdRef = useRef<string | null>(null);
  const downPosRef = useRef({ x: 0, y: 0 });
  const dragMovedRef = useRef(false);
  const pinnedRef = useRef<GraphNode | null>(null);

  // Release the previously pinned node when selection moves elsewhere
  useEffect(() => {
    const prev = pinnedRef.current;
    if (prev && prev.id !== selectedNode?.id && prev !== draggedNode) {
      prev.fx = null;
      prev.fy = null;
      pinnedRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode]);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('islands');
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [draggedNode, setDraggedNode] = useState<GraphNode | null>(null);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [simRunning, setSimRunning] = useState(true);
  const [showArrows, setShowArrows] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [nodeViewMode, setNodeViewMode] = useState<NodeViewMode>('obsidian');

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

    metaCacheRef.current.clear();
    labelWidthCacheRef.current.clear();
    gridRef.current.builtAt = 0;

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
        drawRef.current();
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

  // Center the camera on a requested node (search result click, inspector jump)
  useEffect(() => {
    if (!focusId) return;
    const n = nodeMapRef.current.get(focusId);
    const canvas = canvasRef.current;
    if (!n || n.x === undefined || n.y === undefined || !canvas) return;
    // draw maps node -> width/2 + t.x + k*n.x ; to land the node exactly at the
    // canvas center the camera offset must be -k*n (no width/2 term!)
    const t = transformRef.current;
    const k = Math.max(t.k, 0.9);
    t.x = -n.x * k;
    t.y = -n.y * k;
    t.k = k;
    scheduleDraw();
    onFocusHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  // Handle Resize (window + container: opening the inspector shrinks the canvas,
  // the backing store must follow or mouse coords drift from draw coords)
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width * window.devicePixelRatio;
        canvas.height = rect.height * window.devicePixelRatio;
        drawRef.current();
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    const parent = canvasRef.current?.parentElement;
    const ro = parent ? new ResizeObserver(handleResize) : null;
    if (parent && ro) ro.observe(parent);
    return () => {
      window.removeEventListener('resize', handleResize);
      ro?.disconnect();
    };
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

  const getNodeMetaCached = (n: GraphNode) => {
    let m = metaCacheRef.current.get(n.id);
    if (!m) {
      m = getNodeMeta(n);
      metaCacheRef.current.set(n.id, m);
    }
    return m;
  };

  // Main Canvas Draw Function
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const transform = transformRef.current;
    const huge = nodes.length > 3000;
    const obsidianMode = nodeViewMode === 'obsidian';

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.width / dpr;
    const height = canvas.height / dpr;

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    // 1. Draw Subtle Tech Grid Background (cards mode only — Obsidian uses plain black)
    if (!obsidianMode) {
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
    }

    // 2. Camera Transform
    ctx.translate(width / 2 + transform.x, height / 2 + transform.y);
    ctx.scale(transform.k, transform.k);

    const activeNode = hoveredNode || selectedNode;
    const pathSet = activePath ? new Set(activePath) : null;
    const activeAdj = activeNode ? adjMapRef.current.get(activeNode.id) : null;
    const searchIds: Set<string> | null = (searchQuery && matchedIds && matchedIds.size > 0) ? matchedIds : null;

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

    // 4. Draw Community Island Halos in Islands Mode (cards mode only)
    if (layoutMode === 'islands' && !obsidianMode && transform.k < 1.2) {
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

    // 5. Draw Edges — Obsidian mode: straight faint lines, batched per style bucket.
    //    Cards mode keeps the curved beziers.
    const linksToDraw = simLinksRef.current;
    const pathNormal = new Path2D();
    const pathInferred = new Path2D();
    const pathAmbiguous = new Path2D();
    const pathDimmed = new Path2D();
    const arrowsNormal = new Path2D();

    linksToDraw.forEach(link => {
      const s = link.source;
      const t = link.target;
      if (!s || !t || s.x === undefined || s.y === undefined || t.x === undefined || t.y === undefined) return;

      const isPathEdge = pathSet && pathSet.has(s.id) && pathSet.has(t.id);
      const isConnected = activeNode && (s.id === activeNode.id || t.id === activeNode.id);
      const searchConnected = !!(searchIds && (searchIds.has(s.id) || searchIds.has(t.id)));
      const isDimmed = (activeNode || pathSet)
        ? !isConnected && !isPathEdge
        : !!(searchIds && !searchConnected);

      let endX = t.x;
      let endY = t.y;
      let ctrlX: number | null = null;
      let ctrlY: number | null = null;
      if (!obsidianMode) {
        // Subtle arc curve (perpendicular offset) — cards mode only
        const dx = t.x - s.x;
        const dy = t.y - s.y;
        const dist = Math.hypot(dx, dy) || 1;
        const midX = (s.x + t.x) / 2;
        const midY = (s.y + t.y) / 2;
        const curveStrength = Math.min(25, dist * 0.08);
        ctrlX = midX - (dy / dist) * curveStrength;
        ctrlY = midY + (dx / dist) * curveStrength;
      }

      const trace = () => {
        if (ctrlX !== null && ctrlY !== null) {
          pathDimmed.moveTo(s.x, s.y);
          pathDimmed.quadraticCurveTo(ctrlX, ctrlY, endX, endY);
        } else {
          pathDimmed.moveTo(s.x, s.y);
          pathDimmed.lineTo(endX, endY);
        }
      };
      const traceInto = (p: Path2D) => {
        if (ctrlX !== null && ctrlY !== null) {
          p.moveTo(s.x, s.y);
          p.quadraticCurveTo(ctrlX, ctrlY, endX, endY);
        } else {
          p.moveTo(s.x, s.y);
          p.lineTo(endX, endY);
        }
      };

      if (isPathEdge || isConnected) {
        // highlighted edges are few: draw directly
        ctx.beginPath();
        if (ctrlX !== null && ctrlY !== null) {
          ctx.moveTo(s.x, s.y);
          ctx.quadraticCurveTo(ctrlX, ctrlY, endX, endY);
        } else {
          ctx.moveTo(s.x, s.y);
          ctx.lineTo(endX, endY);
        }
        if (isPathEdge) {
          ctx.strokeStyle = '#38bdf8';
          ctx.lineWidth = Math.max(3.2 / transform.k, 3);
        } else {
          ctx.strokeStyle = s.id === activeNode!.id ? (obsidianMode ? 'rgba(230,180,120,0.75)' : '#10b981') : '#38bdf8';
          ctx.lineWidth = Math.max(2.2 / transform.k, 2);
        }
        ctx.setLineDash([]);
        ctx.stroke();
      } else if (isDimmed) {
        trace();
      } else if (link.confidence === 'AMBIGUOUS') {
        traceInto(pathAmbiguous);
      } else if (link.confidence === 'INFERRED') {
        traceInto(pathInferred);
      } else {
        traceInto(pathNormal);
      }

      // Draw Arrowheads (cards mode + high zoom only; Obsidian has no arrows)
      if (!obsidianMode && showArrows && (isConnected || isPathEdge || (transform.k > 1.1 && !isDimmed))) {
        const angle = ctrlX !== null && ctrlY !== null
          ? Math.atan2(endY - ctrlY, endX - ctrlX)
          : Math.atan2(endY - s.y, endX - s.x);
        const headlen = isConnected || isPathEdge ? Math.max(8 / transform.k, 7) : Math.max(5 / transform.k, 5);
        const targetOffset = nodeViewMode === 'cards' && transform.k > 0.6 ? 16 : 8;
        const arrowX = endX - Math.cos(angle) * targetOffset;
        const arrowY = endY - Math.sin(angle) * targetOffset;

        if (isConnected || isPathEdge) {
          ctx.fillStyle = isPathEdge ? '#38bdf8' : (s.id === activeNode!.id ? '#10b981' : '#38bdf8');
          ctx.beginPath();
          ctx.moveTo(arrowX, arrowY);
          ctx.lineTo(arrowX - headlen * Math.cos(angle - Math.PI / 7), arrowY - headlen * Math.sin(angle - Math.PI / 7));
          ctx.lineTo(arrowX - headlen * Math.cos(angle + Math.PI / 7), arrowY - headlen * Math.sin(angle + Math.PI / 7));
          ctx.closePath();
          ctx.fill();
        } else {
          arrowsNormal.moveTo(arrowX, arrowY);
          arrowsNormal.lineTo(arrowX - headlen * Math.cos(angle - Math.PI / 7), arrowY - headlen * Math.sin(angle - Math.PI / 7));
          arrowsNormal.lineTo(arrowX - headlen * Math.cos(angle + Math.PI / 7), arrowY - headlen * Math.sin(angle + Math.PI / 7));
          arrowsNormal.closePath();
        }
      }

      // Draw Edge Relation Label
      if (showEdgeLabels && (isConnected || (transform.k > 1.6 && !isDimmed))) {
        ctx.font = `${Math.max(9, 10 / transform.k)}px sans-serif`;
        ctx.fillStyle = isConnected ? '#f3f4f6' : 'rgba(209, 213, 219, 0.7)';
        const lx = ctrlX !== null ? ctrlX + 2 : (s.x + endX) / 2;
        const ly = ctrlY !== null ? ctrlY - 2 : (s.y + endY) / 2;
        ctx.fillText(link.relation || 'links', lx, ly);
      }
    });

    // batched style pass
    ctx.setLineDash([]);
    const lineScale = 1 / transform.k;
    if (pathNormal) {
      ctx.strokeStyle = obsidianMode ? 'rgba(200, 200, 210, 0.10)' : 'rgba(148, 163, 184, 0.45)';
      ctx.lineWidth = Math.max(1.1 * lineScale, 1.1);
      ctx.stroke(pathNormal);
    }
    if (pathInferred) {
      ctx.strokeStyle = obsidianMode ? 'rgba(120, 160, 250, 0.09)' : 'rgba(96, 165, 250, 0.4)';
      ctx.lineWidth = Math.max(1.1 * lineScale, 1.1);
      ctx.setLineDash([5 / transform.k, 4 / transform.k]);
      ctx.stroke(pathInferred);
      ctx.setLineDash([]);
    }
    if (pathAmbiguous) {
      ctx.strokeStyle = obsidianMode ? 'rgba(245, 170, 80, 0.13)' : 'rgba(245, 158, 11, 0.55)';
      ctx.lineWidth = Math.max(1.1 * lineScale, 1.1);
      ctx.setLineDash([3 / transform.k, 3 / transform.k]);
      ctx.stroke(pathAmbiguous);
      ctx.setLineDash([]);
    }
    if (pathDimmed) {
      ctx.strokeStyle = 'rgba(75, 85, 99, 0.1)';
      ctx.lineWidth = Math.max(0.7 * lineScale, 0.7);
      ctx.stroke(pathDimmed);
    }
    if (showArrows) {
      ctx.fillStyle = 'rgba(148, 163, 184, 0.7)';
      ctx.fill(arrowsNormal);
    }
    ctx.setLineDash([]);

    // 6. Draw Nodes — Obsidian mode: tiny community-colored dots, labels only
    //    on hover/selection/high zoom. Cards mode keeps the capsule cards.
    //    Glow (shadowBlur) is restricted to the few active nodes so this stays
    //    fast on 50k+ node graphs.
    const labelBudget = obsidianMode ? 80 : Infinity; // cap labels drawn per frame
    let labelsDrawn = 0;
    nodes.forEach(n => {
      if (n.x === undefined || n.y === undefined) return;

      const isSelected = selectedNode?.id === n.id;
      const isHovered = hoveredNode?.id === n.id;
      const isPathNode = pathSet && pathSet.has(n.id);
      const isNeighbor = activeAdj && activeAdj.has(n.id);
      const isSelf = activeNode && activeNode.id === n.id;
      const isSameComm = highlightedCommunity !== null && n.community === highlightedCommunity;
      const isSearchMatch = !!(searchIds && searchIds.has(n.id));
      const isSearchMiss = !!searchIds && !isSearchMatch;

      const meta = getNodeMetaCached(n);
      const commColor = (n.community !== undefined && communityColors[n.community]) || '#4f8cff';

      let alpha = 1;
      if (pathSet) {
        alpha = isPathNode ? 1 : 0.15;
      } else if (activeNode) {
        alpha = isSelf || isNeighbor ? 1 : 0.18;
      } else if (isSearchMatch) {
        alpha = 1;
      } else if (isSearchMiss) {
        alpha = 0.15;
      } else if (highlightedCommunity !== null) {
        alpha = isSameComm ? 1 : 0.18;
      }

      const drawAsCard = nodeViewMode === 'cards' && (transform.k > (huge ? 1.4 : 0.55) || isSelected || isHovered || isNeighbor);

      if (drawAsCard) {
        // --- High-End Capsule Card Rendering (cards mode) ---
        const labelText = (n.label || n.id).slice(0, 32);
        ctx.font = '500 11px Inter, system-ui, sans-serif';
        let textWidth = labelWidthCacheRef.current.get(labelText);
        if (textWidth === undefined) {
          textWidth = ctx.measureText(labelText).width;
          labelWidthCacheRef.current.set(labelText, textWidth);
        }
        const cardW = Math.max(75, textWidth + 34);
        const cardH = 22;
        const cardX = n.x - cardW / 2;
        const cardY = n.y - cardH / 2;
        const r = 6; // rounded corners

        if (isSelected || isHovered || isSearchMatch) {
          ctx.shadowColor = isSelected ? '#ffffff' : isHovered ? commColor : '#f59e0b';
          ctx.shadowBlur = 12;
        } else {
          ctx.shadowBlur = 0;
        }

        ctx.beginPath();
        ctx.roundRect(cardX, cardY, cardW, cardH, r);
        ctx.fillStyle = alpha > 0.5 ? 'rgba(15, 23, 42, 0.94)' : 'rgba(15, 23, 42, 0.3)';
        ctx.fill();

        ctx.lineWidth = isSelected ? 2 : isHovered || isNeighbor || isSearchMatch ? 1.5 : 1;
        ctx.strokeStyle = isSelected ? '#ffffff' : isHovered ? '#38bdf8' : isNeighbor ? commColor : isSearchMatch ? '#f59e0b' : `${commColor}88`;
        ctx.stroke();
        ctx.shadowBlur = 0;

        if (alpha > 0.4) {
          ctx.beginPath();
          ctx.roundRect(cardX + 2, cardY + 2, 18, cardH - 4, 4);
          ctx.fillStyle = `${meta.color}25`;
          ctx.fill();
          ctx.font = 'bold 9px monospace';
          ctx.fillStyle = meta.color;
          ctx.textAlign = 'center';
          ctx.fillText(meta.glyph, cardX + 11, cardY + 14);

          ctx.font = '500 11px Inter, system-ui, sans-serif';
          ctx.fillStyle = isSelected ? '#ffffff' : '#f3f4f6';
          ctx.textAlign = 'left';
          ctx.fillText(labelText, cardX + 25, cardY + 15);
        }
      } else {
        // --- Obsidian-style dot rendering ---
        const deg = n.degree || 1;
        let radius = Math.max(2.2, Math.min(8, 1.8 + Math.sqrt(deg) * 0.9));
        if (isSelected || isHovered) radius += 1.6;
        ctx.globalAlpha = alpha;

        // soft halo only for significant nodes (hub, active, hovered, matched)
        const wantsGlow = isSelected || isHovered || isSelf || isNeighbor || isSearchMatch || deg >= 12;
        if (wantsGlow && !huge) {
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius * 2.4, 0, Math.PI * 2);
          ctx.fillStyle = commColor;
          ctx.globalAlpha = alpha * 0.14;
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = commColor;
        ctx.globalAlpha = alpha;
        ctx.fill();

        if (isSelected || isPathNode) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = Math.max(2 / transform.k, 1.8);
          ctx.stroke();
        } else if (isHovered || isNeighbor) {
          ctx.strokeStyle = commColor;
          ctx.lineWidth = Math.max(1.6 / transform.k, 1.5);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;

        // Obsidian labels: invisible at rest, fade in while hovering/zooming
        const showLabel = isSelected || isHovered || isSelf || isNeighbor || isSearchMatch
          || (obsidianMode && transform.k > 1.7 && deg >= 8 && labelsDrawn < labelBudget);
        if (showLabel && labelsDrawn < labelBudget) {
          labelsDrawn++;
          const text = (n.label || n.id).slice(0, 40);
          ctx.font = '10.5px Inter, system-ui, sans-serif';
          const tw = ctx.measureText(text).width;
          const lx = n.x + radius + 4;
          const ly = n.y - 9;
          ctx.globalAlpha = Math.max(alpha, isNeighbor ? 0.75 : alpha);
          ctx.fillStyle = 'rgba(10, 10, 16, 0.85)';
          ctx.fillRect(lx, ly, tw + 8, 17);
          ctx.fillStyle = isSelf || isSelected ? '#ffffff' : 'rgba(228, 228, 235, 0.92)';
          ctx.textAlign = 'left';
          ctx.fillText(text, lx + 4, ly + 12.5);
          ctx.globalAlpha = 1;
        }
      }
    });

    ctx.restore();
  }, [nodes, edges, selectedNode, hoveredNode, highlightedCommunity, activePath, communityColors, showArrows, showEdgeLabels, layoutMode, nodeViewMode, searchQuery, matchedIds]);

  useEffect(() => {
    drawRef.current = draw;
    draw();
  }, [draw]);

  // Wheel zoom attached directly to canvas with { passive: false } to prevent passive listener warning
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const t = transformRef.current;
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      t.k = Math.max(0.04, Math.min(8, t.k * zoomFactor));
      scheduleDraw();
    };

    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => {
      canvas.removeEventListener('wheel', onWheel);
    };
  }, [scheduleDraw]);

  // Screen to Graph coordinates
  const screenToGraph = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;
    const t = transformRef.current;
    return {
      x: (mouseX - rect.width / 2 - t.x) / t.k,
      y: (mouseY - rect.height / 2 - t.y) / t.k,
    };
  };

  // Spatial hash grid for fast hit tests (lazily rebuilt, 250ms TTL)
  const rebuildGrid = () => {
    const cell = gridRef.current.cell;
    const map = new Map<string, GraphNode[]>();
    for (const n of nodes) {
      if (n.x === undefined || n.y === undefined) continue;
      const key = `${Math.floor(n.x / cell)}:${Math.floor(n.y / cell)}`;
      const arr = map.get(key);
      if (arr) arr.push(n); else map.set(key, [n]);
    }
    gridRef.current.map = map;
    gridRef.current.builtAt = performance.now();
  };

  const findNodeAt = (x: number, y: number) => {
    if (performance.now() - gridRef.current.builtAt > 250 || gridRef.current.map.size === 0) {
      rebuildGrid();
    }
    const cell = gridRef.current.cell;
    const cx = Math.floor(x / cell);
    const cy = Math.floor(y / cell);
    const cards = nodeViewMode === 'cards' && transformRef.current.k > 0.55;
    let best: GraphNode | null = null;
    let bestD = Infinity;
    for (let gx = cx - 1; gx <= cx + 1; gx++) {
      for (let gy = cy - 1; gy <= cy + 1; gy++) {
        const arr = gridRef.current.map.get(`${gx}:${gy}`);
        if (!arr) continue;
        for (const n of arr) {
          const dx = n.x! - x;
          const dy = n.y! - y;
          const d = dx * dx + dy * dy;
          if (d >= bestD) continue;
          const hitRadius = cards ? 30 : Math.max(10, 5 + (n.degree || 1) * 0.45);
          if (d <= hitRadius * hitRadius) {
            bestD = d;
            best = n;
          }
        }
      }
    }
    return best;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    downPosRef.current = { x: e.clientX, y: e.clientY };
    dragMovedRef.current = false;
    const gPos = screenToGraph(e.clientX, e.clientY);
    const hit = findNodeAt(gPos.x, gPos.y);

    if (hit) {
      setDraggedNode(hit);
      hit.fx = hit.x;
      hit.fy = hit.y;
    } else {
      setIsDraggingCanvas(true);
      setDragStart({ x: e.clientX - transformRef.current.x, y: e.clientY - transformRef.current.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggedNode) {
      if (!dragMovedRef.current) {
        const dx = e.clientX - downPosRef.current.x;
        const dy = e.clientY - downPosRef.current.y;
        if (dx * dx + dy * dy > 9) {
          dragMovedRef.current = true;
          if (simulationRef.current) {
            simulationRef.current.alphaTarget(0.1).restart();
            setSimRunning(true);
          }
        }
      }
      const gPos = screenToGraph(e.clientX, e.clientY);
      draggedNode.fx = gPos.x;
      draggedNode.fy = gPos.y;
      draggedNode.x = gPos.x;
      draggedNode.y = gPos.y;
      scheduleDraw();
    } else if (isDraggingCanvas) {
      const dx = e.clientX - downPosRef.current.x;
      const dy = e.clientY - downPosRef.current.y;
      if (dx * dx + dy * dy > 9) dragMovedRef.current = true;
      const t = transformRef.current;
      t.x = e.clientX - dragStart.x;
      t.y = e.clientY - dragStart.y;
      scheduleDraw();
    } else {
      const { clientX, clientY } = e;
      if (hoverRafRef.current) return;
      hoverRafRef.current = requestAnimationFrame(() => {
        hoverRafRef.current = 0;
        const gPos = screenToGraph(clientX, clientY);
        const hit = findNodeAt(gPos.x, gPos.y);
        const id = hit ? hit.id : null;
        if (id !== lastHoverIdRef.current) {
          lastHoverIdRef.current = id;
          setHoveredNode(hit);
        }
      });
    }
  };

  const handleMouseUp = () => {
    if (draggedNode) {
      if (dragMovedRef.current) {
        // real drag: release the node back to the physics
        draggedNode.fx = null;
        draggedNode.fy = null;
        if (simulationRef.current) simulationRef.current.alphaTarget(0);
        if (pinnedRef.current === draggedNode) pinnedRef.current = null;
      } else {
        // keep the clicked node pinned in place; release the previously pinned one
        if (pinnedRef.current && pinnedRef.current !== draggedNode) {
          pinnedRef.current.fx = null;
          pinnedRef.current.fy = null;
        }
        pinnedRef.current = draggedNode;
      }
      // click or drag end: select it
      onSelectNode(draggedNode);
      setDraggedNode(null);
    } else if (isDraggingCanvas) {
      setIsDraggingCanvas(false);
      if (!dragMovedRef.current) {
        // plain click on empty canvas: deselect
        onSelectNode(null);
      }
    }
  };

  const resetView = () => {
    const t = transformRef.current;
    t.x = 0;
    t.y = 0;
    t.k = 0.85;
    scheduleDraw();
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
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: nodeViewMode === 'obsidian' ? '#0a0a10' : '#090d16' }}>
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

        {/* Obsidian vs Cards View Switcher */}
        <button
          onClick={() => setNodeViewMode(m => m === 'obsidian' ? 'cards' : 'obsidian')}
          title="Toggle Obsidian dot view vs capsule card view"
          style={{
            background: 'transparent',
            border: '1px solid transparent',
            color: 'var(--text-secondary)',
            padding: '5px 8px',
            borderRadius: 6,
            fontSize: 11,
          }}
        >
          {nodeViewMode === 'obsidian' ? 'Obsidian View' : 'Cards View'}
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
          onClick={() => { const t = transformRef.current; t.k = Math.min(8, t.k * 1.25); scheduleDraw(); }}
          title="Zoom In"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', padding: 6, borderRadius: 4, display: 'flex' }}
        >
          <ZoomIn size={16} />
        </button>
        <button
          onClick={() => { const t = transformRef.current; t.k = Math.max(0.04, t.k * 0.8); scheduleDraw(); }}
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
