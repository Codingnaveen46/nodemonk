"""nodemonk.viz - single-file canvas knowledge-graph visualizer.

One self-contained HTML file: the entire graph plus the viewer. Engine notes:
- unlimited nodes by design (canvas points, grid-accelerated repulsion,
  progressive physics) - no 5,000-node cap like today's tools biggest gap
- community-colored halos, LOD labels, search, community filters, inspector
- static double-file output: fully offline, no CDN, no server needed
"""

from __future__ import annotations

import json
from typing import Any

from .fsutil import atomic_write
from .graph import Graph

_PALETTE = [
    "#4f8cff", "#22c55e", "#f97316", "#a855f7", "#06b6d4", "#e11d48",
    "#84cc16", "#f59e0b", "#8b5cf6", "#14b8a6", "#ef4444", "#0ea5e9",
    "#84e1bc", "#d946ef", "#f472b6", "#38bdf8", "#fb923c", "#34d399",
    "#c084fc", "#facc15",
]

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>nodemonk graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#0b0f19; --panel:#111827; --line:#1f2937; --text:#e5e7eb; --dim:#9ca3af; --accent:#4f8cff; }
* { box-sizing: border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--text); font: 14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif; }
#app { display:flex; height:100vh; }
#side { width:290px; min-width:290px; background:var(--panel); border-right:1px solid var(--line); overflow-y:auto; padding:14px; }
#canvasWrap { position:relative; flex:1; min-width:0; }
canvas { width:100%; height:100%; display:block; cursor:grab; }
canvas:active { cursor:grabbing; }
h1 { font-size:16px; margin:0 0 4px; }
.sub { color:var(--dim); font-size:12px; margin-bottom:10px; }
.search { width:100%; padding:7px 10px; border:1px solid var(--line); border-radius:8px; background:#0b0f19; color:var(--text); outline:none; }
.legend { margin-top:12px; font-size:12px; }
.crow { display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; }
.dot { width:10px;height:10px;border-radius:50%; flex:none; }
.dimmed { opacity:.25; }
.controls { margin-top:14px; display:flex; gap:6px; flex-wrap:wrap;}
button { background:#0b0f19; color:var(--text); border:1px solid var(--line); padding:6px 10px; border-radius:8px; cursor:pointer; font-size:12px;}
button.active { border-color:var(--accent); color:var(--accent); }
#inspector { position:absolute; right:12px; top:12px; width:300px; max-height:70vh; overflow-y:auto; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; font-size:13px; display:none; box-shadow:0 10px 30px rgba(0,0,0,.4);}
#inspector h3 { margin:0 0 6px; font-size:14px; word-break:break-all;}
#inspector .meta { color:var(--dim); font-size:12px; margin-bottom:8px;}
#inspector ul { margin:4px 0; padding-left:16px; }
#inspector li { margin:2px 0; word-break:break-all; }
.conf { font-size:11px; padding:0 4px; border-radius:4px;}
.conf.EXTRACTED { background:#14532d; color:#bbf7d0;}
.conf.INFERRED { background:#1e3a8a; color:#bfdbfe;}
.conf.AMBIGUOUS { background:#713f12; color:#fde68a;}
#status { position:absolute; left:12px; bottom:10px; color:var(--dim); font-size:12px; background:rgba(11,15,25,.8); padding:2px 8px; border-radius:6px;}
#hits { margin-top:6px; font-size:12px; }
.hit { padding:3px 6px; border-radius:6px; cursor:pointer; }
.hit:hover, .hit.active { background:#1f2937; }
.tag { display:inline-block; background:#1f2937; color:var(--dim); border-radius:4px; padding:0 5px; font-size:11px; margin-left:4px;}
</style>
</head>
<body>
<div id="app">
  <div id="side">
    <h1>nodemonk</h1>
    <div class="sub">__STATS__</div>
    <input id="q" class="search" placeholder="search nodes... (unlimited results)" autocomplete="off">
    <div id="hits"></div>
    <div class="legend" id="legend"></div>
    <div class="controls">
      <button id="btnRelax" class="active">physics</button>
      <button id="btnLabels">labels</button>
      <button id="btnReset">reset view</button>
      <button id="btnExport">export png</button>
    </div>
    <div class="legend" style="margin-top:14px">
      edge trust:
      <div><span class="conf EXTRACTED">EXTRACTED</span> in the source</div>
      <div><span class="conf INFERRED">INFERRED</span> resolved by nodemonk</div>
      <div><span class="conf AMBIGUOUS">AMBIGUOUS</span> low trust</div>
    </div>
  </div>
  <div id="canvasWrap">
    <canvas id="c"></canvas>
    <div id="inspector"></div>
    <div id="status"></div>
  </div>
</div>
<script>
const DATA = __DATA__;
const PALETTE = __PALETTE__;
const N = DATA.nodes, L = DATA.links;
const COM_LABELS = __LABELS__;
const id2i = new Map(N.map((n,i)=>[n.id,i]));

// 1. Group nodes by community
const comms = {};
N.forEach(n=>{
  const c = n.com ?? -1;
  (comms[c] = comms[c]||[]).push(n);
  n.deg = n.deg || 0;
});

const ckeys = Object.keys(comms).sort((a,b)=>comms[b].length - comms[a].length);
let bigDegree = 1;
N.forEach(n => { if (n.deg > bigDegree) bigDegree = n.deg; });

// 2. Compute spacious, non-overlapping community centers
const commCenters = {};
const numComms = Math.max(1, ckeys.length);
const baseDist = Math.max(850, 180 * Math.sqrt(numComms));

ckeys.forEach((k, ki) => {
  const angle = (2 * Math.PI * ki) / numComms;
  const radius = (ki === 0 && comms[k].length > 30) ? 0 : baseDist * (0.4 + 0.6 * Math.sqrt((ki + 1) / numComms));
  commCenters[k] = {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius,
    label: COM_LABELS[k] || ("Community " + k)
  };
});

// 3. Seed nodes within their community clusters
ckeys.forEach(k => {
  const arr = comms[k];
  const center = commCenters[k];
  const ringRadius = 25 + 16 * Math.sqrt(arr.length);
  arr.forEach((n, ni) => {
    const ang = (2 * Math.PI * ni) / arr.length;
    const r = (ni === 0 && arr.length > 3) ? 0 : (ringRadius * (0.3 + 0.7 * ((ni % 3 + 1) / 3)));
    n.x = center.x + Math.cos(ang) * r;
    n.y = center.y + Math.sin(ang) * r;
    n.vx = 0;
    n.vy = 0;
    n.col = PALETTE[(k | 0) % PALETTE.length];
    n.r = Math.max(3.5, Math.min(14, 3 + Math.pow(n.deg / bigDegree, 0.5) * 8));
  });
});

// 4. Resolve edge endpoints correctly
const EL = L.map(l => {
  const s = typeof l.s === "number" ? l.s : id2i.get(l.s);
  const t = typeof l.t === "number" ? l.t : id2i.get(l.t);
  return [s, t, l.r || "", l.c || "EXTRACTED", l.w ?? 1];
}).filter(e => e[0] !== undefined && e[1] !== undefined && e[0] >= 0 && e[1] >= 0);

const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
let W = 0, H = 0, DPR = 1, tX = 0, tY = 0, scale = 0.85;
let draggingCanvas = false, draggedNode = null, moved = false;
let hoverI = -1, selI = -1;
let physics = true, showLabels = false, CommFilter = null;
let alpha = 1.0;
const ALPHA_DECAY = 0.982;
const MIN_ALPHA = 0.003;

function resize() {
  const r = canvas.getBoundingClientRect();
  DPR = window.devicePixelRatio || 1;
  W = r.width;
  H = r.height;
  canvas.width = W * DPR;
  canvas.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener("resize", resize);

// 5. Stable, Cooling Physics with Community Clustered Gravity (No Vibration/Dancing)
function stepPhysics() {
  if (!physics || alpha < MIN_ALPHA) return;

  // A. Intra & Inter Community Springs
  for (const [a, b, rel, conf, w] of EL) {
    const na = N[a], nb = N[b];
    if (!na || !nb) continue;
    const dx = nb.x - na.x;
    const dy = nb.y - na.y;
    const d = Math.hypot(dx, dy) || 1;

    // Same community nodes stay cozy (45px); cross-community bridges are relaxed (140px)
    const isSameComm = na.com === nb.com;
    const targetDist = isSameComm ? 45 : 140;
    const strength = (isSameComm ? 0.05 : 0.015) * alpha;
    const force = (d - targetDist) * strength;
    const fx = (dx / d) * force;
    const fy = (dy / d) * force;

    na.vx += fx; na.vy += fy;
    nb.vx -= fx; nb.vy -= fy;
  }

  // B. Community Cluster Gravity (keep each module grouped)
  for (let i = 0; i < N.length; i++) {
    const n = N[i];
    const center = commCenters[n.com];
    if (center) {
      n.vx += (center.x - n.x) * 0.035 * alpha;
      n.vy += (center.y - n.y) * 0.035 * alpha;
    }
    // Very gentle global centering
    n.vx += -n.x * 0.0003 * alpha;
    n.vy += -n.y * 0.0003 * alpha;
  }

  // C. Anti-Collision & Local Repulsion (prevents overlapping)
  const cell = 120;
  const grid = new Map();
  for (let i = 0; i < N.length; i++) {
    const n = N[i];
    const key = ((n.x / cell) | 0) + "," + ((n.y / cell) | 0);
    let arr = grid.get(key);
    if (!arr) { arr = []; grid.set(key, arr); }
    arr.push(i);
  }

  for (let i = 0; i < N.length; i++) {
    const na = N[i];
    const gx = (na.x / cell) | 0;
    const gy = (na.y / cell) | 0;

    for (let ox = -1; ox <= 1; ox++) {
      for (let oy = -1; oy <= 1; oy++) {
        const arr = grid.get((gx + ox) + "," + (gy + oy));
        if (!arr) continue;
        for (const j of arr) {
          if (j <= i) continue;
          const nb = N[j];
          let dx = na.x - nb.x;
          let dy = na.y - nb.y;
          let d2 = dx * dx + dy * dy;
          const minDist = na.r + nb.r + 10;
          if (d2 < 1) {
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
            d2 = dx * dx + dy * dy;
          }
          if (d2 < minDist * minDist) {
            // Strong push apart if overlapping
            const d = Math.sqrt(d2);
            const push = (minDist - d) * 0.35 * alpha;
            const px = (dx / d) * push;
            const py = (dy / d) * push;
            na.vx += px; na.vy += py;
            nb.vx -= px; nb.vy -= py;
          } else if (d2 < cell * cell) {
            // Gentle local repulsion
            const d = Math.sqrt(d2);
            const rep = (na.com === nb.com ? 25 : 60) / d2 * alpha * 8;
            na.vx += (dx / d) * rep; na.vy += (dy / d) * rep;
            nb.vx -= (dx / d) * rep; nb.vy -= (dy / d) * rep;
          }
        }
      }
    }
  }

  // D. Velocity Damping & Position Update
  const damping = 0.72;
  for (let i = 0; i < N.length; i++) {
    const n = N[i];
    if (n === draggedNode) {
      n.vx = 0;
      n.vy = 0;
      continue;
    }
    n.vx *= damping;
    n.vy *= damping;
    const speed = Math.hypot(n.vx, n.vy);
    const maxSpeed = 12 * alpha;
    if (speed > maxSpeed && speed > 0) {
      n.vx = (n.vx / speed) * maxSpeed;
      n.vy = (n.vy / speed) * maxSpeed;
    }
    n.x += n.vx;
    n.y += n.vy;
  }

  alpha *= ALPHA_DECAY;
}

// 6. Crisp, Readable Rendering (No Text Stack/Overlap)
function render() {
  ctx.save();
  ctx.clearRect(0, 0, W, H);
  ctx.translate(W / 2, H / 2);
  ctx.scale(scale, scale);
  ctx.translate(tX, tY);
  const inv = 1 / scale;

  // A. Draw Community Cluster Halos & Badges
  if (scale < 1.4) {
    for (const k of ckeys) {
      const center = commCenters[k];
      const arr = comms[k];
      if (!center || !arr || !arr.length) continue;
      if (CommFilter != null && (k | 0) !== CommFilter) continue;

      ctx.beginPath();
      const clusterR = 35 + 16 * Math.sqrt(arr.length);
      ctx.arc(center.x, center.y, clusterR + 25, 0, Math.PI * 2);
      ctx.fillStyle = (PALETTE[(k | 0) % PALETTE.length]) + "0d"; // 5% opacity
      ctx.fill();

      // Community Title Label
      ctx.font = `bold ${Math.max(12, 13 * inv)}px system-ui, sans-serif`;
      ctx.fillStyle = PALETTE[(k | 0) % PALETTE.length];
      const title = center.label || ("Community " + k);
      ctx.fillText(title, center.x - (title.length * 3.5 * inv), center.y - clusterR - 12);
    }
  }

  // B. Draw Edges
  for (const [a, b, rel, conf] of EL) {
    const na = N[a], nb = N[b];
    if (!na || !nb) continue;
    if (CommFilter != null && na.com !== CommFilter && nb.com !== CommFilter) continue;

    const isConn = (selI >= 0 && (a === selI || b === selI)) || (hoverI >= 0 && (a === hoverI || b === hoverI));
    const isDimmed = (selI >= 0 || hoverI >= 0) && !isConn;

    if (isConn) {
      ctx.lineWidth = Math.max(2.8 * inv, 2.5);
      const isOutgoing = (selI >= 0 && a === selI) || (hoverI >= 0 && a === hoverI);
      ctx.strokeStyle = isOutgoing ? "#10b981" : "#38bdf8";
      ctx.setLineDash([]);
    } else if (isDimmed) {
      ctx.lineWidth = 0.7 * inv;
      ctx.strokeStyle = "rgba(75, 85, 99, 0.12)";
      ctx.setLineDash([]);
    } else {
      ctx.lineWidth = Math.max(1.1 * inv, 1.1);
      ctx.strokeStyle = conf === "EXTRACTED" ? "rgba(148, 163, 184, 0.45)" :
                        conf === "AMBIGUOUS" ? "rgba(245, 158, 11, 0.5)" : "rgba(96, 165, 250, 0.4)";
      if (conf === "INFERRED") ctx.setLineDash([4 * inv, 3 * inv]);
      else ctx.setLineDash([]);
    }

    ctx.beginPath();
    ctx.moveTo(na.x, na.y);
    ctx.lineTo(nb.x, nb.y);
    ctx.stroke();

    // Directional Arrowheads
    if (isConn || (scale > 1.2 && !isDimmed)) {
      const angle = Math.atan2(nb.y - na.y, nb.x - na.x);
      const headlen = isConn ? Math.max(8 * inv, 7) : Math.max(5 * inv, 5);
      const arrowX = nb.x - Math.cos(angle) * (nb.r + 3);
      const arrowY = nb.y - Math.sin(angle) * (nb.r + 3);
      ctx.fillStyle = isConn ? ((selI >= 0 && a === selI) || (hoverI >= 0 && a === hoverI) ? "#10b981" : "#38bdf8") : "rgba(148, 163, 184, 0.7)";
      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(arrowX - headlen * Math.cos(angle - Math.PI / 6), arrowY - headlen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(arrowX - headlen * Math.cos(angle + Math.PI / 6), arrowY - headlen * Math.sin(angle + Math.PI / 6));
      ctx.closePath();
      ctx.fill();
    }
  }
  ctx.setLineDash([]);

  // C. Draw Nodes
  for (let i = 0; i < N.length; i++) {
    const n = N[i];
    if (CommFilter != null && n.com !== CommFilter) continue;

    const isSel = i === selI;
    const isHover = i === hoverI;
    const isNbr = nbrSet.has(i);
    const dimmed = (selI >= 0 || hoverI >= 0) && !isSel && !isHover && !isNbr;

    ctx.fillStyle = dimmed ? "rgba(55, 65, 81, 0.3)" : n.col;
    ctx.beginPath();
    ctx.arc(n.x, n.y, isSel || isHover ? n.r + 3 : n.r, 0, Math.PI * 2);
    ctx.fill();

    if (isSel) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = Math.max(2.5 * inv, 2.5);
      ctx.stroke();
    } else if (isHover || isNbr) {
      ctx.strokeStyle = isHover ? "#38bdf8" : (n.col || "#ffffff");
      ctx.lineWidth = Math.max(2 * inv, 1.8);
      ctx.stroke();
    }
  }

  // D. Draw Labels - Clean & Non-Overlapping
  const activeI = hoverI >= 0 ? hoverI : selI;
  ctx.font = `${Math.max(10, 11 * inv)}px system-ui, sans-serif`;

  for (let i = 0; i < N.length; i++) {
    const n = N[i];
    if (CommFilter != null && n.com !== CommFilter) continue;

    const isPrimary = (i === activeI);
    const isAdjacent = (activeI >= 0 && nbrSet.has(i));
    const isTopHub = (scale > 0.8 && n.deg >= bigDegree * 0.45);
    const shouldShow = isPrimary || isAdjacent || showLabels || (scale > 1.6) || isTopHub;

    if (!shouldShow) continue;

    const text = (n.l || n.id).slice(0, 40);
    const tx = n.x + n.r + 5;
    const ty = n.y + 4;

    // Draw pill background for active/neighbor labels for perfect contrast
    if (isPrimary || isAdjacent) {
      const metrics = ctx.measureText(text);
      ctx.fillStyle = "rgba(17, 24, 39, 0.88)";
      ctx.fillRect(tx - 3, ty - 11, metrics.width + 6, 15);
      ctx.strokeStyle = isPrimary ? "#38bdf8" : "rgba(75, 85, 99, 0.6)";
      ctx.lineWidth = 1;
      ctx.strokeRect(tx - 3, ty - 11, metrics.width + 6, 15);
    }

    ctx.fillStyle = isPrimary ? "#ffffff" : isAdjacent ? "#e5e7eb" : "rgba(209, 213, 219, 0.8)";
    ctx.fillText(text, tx, ty);
  }

  ctx.restore();

  // Status indicator
  const stateStr = alpha < MIN_ALPHA ? "stable (frozen)" : `settling (${Math.round((1 - alpha) * 100)}%)`;
  status.textContent = `${N.length.toLocaleString()} nodes · ${L.length.toLocaleString()} edges · ${stateStr} · zoom ${scale.toFixed(2)}x`;
}

let nbrSet = new Set(), hoverN = null, selN = null;

function neighbors(i) {
  const out = new Set();
  for (const [a, b] of EL) {
    if (a === i) out.add(b);
    if (b === i) out.add(a);
  }
  return out;
}

function toGraph(x, y) {
  const wx = (x - W / 2) / scale - tX;
  const wy = (y - H / 2) / scale - tY;
  return [wx, wy];
}

let mX = 0, mY = 0;

// Mouse & Touch Interactions with Smooth Dragging
canvas.addEventListener("pointerdown", ev => {
  const rect = canvas.getBoundingClientRect();
  const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
  const [wx, wy] = toGraph(px, py);

  // Check if clicked directly on a node
  let hit = -1, bestD = 15;
  for (let i = 0; i < N.length; i++) {
    const d = Math.hypot(N[i].x - wx, N[i].y - wy);
    if (d < N[i].r + 4 && d < bestD) {
      bestD = d;
      hit = i;
    }
  }

  if (hit >= 0) {
    draggedNode = N[hit];
    alpha = Math.max(alpha, 0.08); // wake up physics slightly
  } else {
    draggingCanvas = true;
  }

  moved = false;
  mX = px;
  mY = py;
});

canvas.addEventListener("pointermove", ev => {
  const rect = canvas.getBoundingClientRect();
  const px = ev.clientX - rect.left, py = ev.clientY - rect.top;

  if (draggedNode) {
    const [wx, wy] = toGraph(px, py);
    draggedNode.x = wx;
    draggedNode.y = wy;
    draggedNode.vx = 0;
    draggedNode.vy = 0;
    moved = true;
    alpha = Math.max(alpha, 0.05);
  } else if (draggingCanvas && ev.buttons) {
    tX += (px - mX) / scale;
    tY += (py - mY) / scale;
    moved = true;
  } else {
    const [wx, wy] = toGraph(px, py);
    let best = -1, bestD = 14;
    for (let i = 0; i < N.length; i++) {
      const d = Math.hypot(N[i].x - wx, N[i].y - wy);
      if (d < N[i].r + 5 && d < bestD) {
        bestD = d;
        best = i;
      }
    }
    hoverI = best;
    hoverN = best >= 0 ? N[best] : null;
    nbrSet = best >= 0 ? neighbors(best) : (selI >= 0 ? neighbors(selI) : new Set());
  }

  mX = px;
  mY = py;
});

canvas.addEventListener("pointerup", ev => {
  if (!moved) {
    if (hoverI >= 0) {
      select(hoverI);
    } else {
      deselect();
    }
  }
  draggedNode = null;
  draggingCanvas = false;
});

canvas.addEventListener("wheel", ev => {
  ev.preventDefault();
  const f = ev.deltaY < 0 ? 1.15 : 0.87;
  const rect = canvas.getBoundingClientRect();
  const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
  const [wx, wy] = toGraph(px, py);
  scale = Math.max(0.04, Math.min(8, scale * f));
  tX = px - W / 2 - wx * scale;
  tY = py - H / 2 - wy * scale;
}, { passive: false });

function select(i) {
  selI = i;
  selN = N[i];
  nbrSet = neighbors(i);
  showInspector(i);
}

function deselect() {
  selI = -1;
  selN = null;
  nbrSet = hoverI >= 0 ? neighbors(hoverI) : new Set();
  document.getElementById("inspector").style.display = "none";
}

function showInspector(i) {
  const n = N[i];
  const el = document.getElementById("inspector");
  const links = [];
  for (const [a, b, rel, conf] of EL) {
    if (a === i) links.push([b, rel, conf, false]);
    if (b === i) links.push([a, rel, conf, true]);
  }
  const src = n.f ? `<div class="meta">file: ${esc(n.f)}</div>` : "";
  const commName = COM_LABELS[n.com] || ("Community " + n.com);

  el.innerHTML = `<h3>${esc(n.l || n.id)}</h3>
    <div class="meta">${esc(n.t || "code")} · ${esc(commName)} · degree ${n.deg || 0}</div>
    ${src}
    <div style="font-weight:600;font-size:11px;color:var(--dim);margin:8px 0 4px">CONNECTIONS (${links.length}):</div>
    <ul>${links.slice(0, 100).map(([o, rel, conf, back]) =>
      `<li>${back ? "&larr;" : "&rarr;"} <b>${esc(rel || "links")}</b> ${conf ? `<span class="conf ${conf}">${conf}</span>` : ""} <a href="#" data-n="${o}" class="jump">${esc(N[o].l || N[o].id)}</a></li>`
    ).join("")}
    ${links.length > 100 ? `<li>… ${links.length - 100} more</li>` : ""}</ul>`;
  el.style.display = "block";
  el.querySelectorAll(".jump").forEach(a => a.onclick = (e) => {
    e.preventDefault();
    select(+e.currentTarget.dataset.n);
    focusNode(+e.currentTarget.dataset.n);
  });
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Search
const qEl = document.getElementById("q"), hitsEl = document.getElementById("hits");
qEl.addEventListener("input", () => {
  const term = qEl.value.trim().toLowerCase();
  hitsEl.innerHTML = "";
  if (!term) return;
  let count = 0;
  for (let i = 0; i < N.length; i++) {
    const l = (N[i].l || "").toLowerCase();
    if (l.includes(term)) {
      if (count < 30) {
        const d = document.createElement("div");
        d.className = "hit";
        d.textContent = (N[i].l || N[i].id).slice(0, 60) + (N[i].t ? ` (${N[i].t})` : "");
        d.onclick = () => { focusNode(i); };
        hitsEl.appendChild(d);
      }
      count++;
    }
  }
  if (count > 30) {
    const more = document.createElement("div");
    more.className = "hit dimmed";
    more.textContent = `+${count - 30} more matches`;
    hitsEl.appendChild(more);
  }
  if (!count) { hitsEl.innerHTML = "<div class='hit dimmed'>no match</div>"; }
});

function focusNode(i) {
  select(i);
  const n = N[i];
  tX = -n.x;
  tY = -n.y;
  scale = Math.max(scale, 1.2);
}

// Legend
const legendEl = document.getElementById("legend");
function buildLegend() {
  const rows = [];
  rows.push(`<div class="crow" data-c="-1"><span class="dot" style="background:#555"></span>All communities <span class="tag">${N.length.toLocaleString()}</span></div>`);
  for (const k of ckeys) {
    const lblk = COM_LABELS[k] || ("Community " + k);
    rows.push(`<div class="crow" data-c="${k}"><span class="dot" style="background:${PALETTE[(k | 0) % PALETTE.length]}"></span>${esc(lblk)} <span class="tag">${comms[k].length.toLocaleString()}</span></div>`);
  }
  legendEl.innerHTML = rows.join("");
  legendEl.querySelectorAll(".crow").forEach(r => r.onclick = () => {
    const val = r.dataset.c === "-1" ? null : (r.dataset.c | 0);
    CommFilter = CommFilter === val ? null : val;
    legendEl.querySelectorAll(".crow").forEach(x => x.classList.toggle("dimmed", CommFilter != null && x.dataset.c !== (CommFilter + "")));
  });
}

// Control Buttons
const btnRelax = document.getElementById("btnRelax");
btnRelax.onclick = (e) => {
  if (alpha < MIN_ALPHA) {
    // Settle again
    alpha = 0.35;
    physics = true;
    btnRelax.textContent = "settling...";
  } else {
    // Freeze now
    alpha = 0;
    btnRelax.textContent = "settle";
  }
};

document.getElementById("btnLabels").onclick = (e) => {
  showLabels = !showLabels;
  e.target.classList.toggle("active", showLabels);
};

document.getElementById("btnReset").onclick = () => {
  scale = 0.85;
  tX = 0;
  tY = 0;
  deselect();
};

document.getElementById("btnExport").onclick = () => {
  const tmp = document.createElement("canvas");
  tmp.width = canvas.width;
  tmp.height = canvas.height;
  tmp.getContext("2d").drawImage(canvas, 0, 0);
  const a = document.createElement("a");
  a.download = "nodemonk-graph.png";
  a.href = tmp.toDataURL("image/png");
  a.click();
};

const status = document.getElementById("status");
resize();
buildLegend();

function animate() {
  stepPhysics();
  render();
  requestAnimationFrame(animate);
}
animate();
</script>
</body>
</html>
"""


def write_viz_html(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    out_path,
    top_pagerank: dict[str, float] | None = None,
) -> str:
    node_comm: dict[str, int] = {}
    for cid, ms in communities.items():
        for m in ms:
            node_comm[m] = cid
    degrees = G.degree_map()
    max_deg = max(degrees.values(), default=1) or 1
    nodes_payload: list[dict[str, Any]] = []
    idset = set(G.nodes())
    for nid, nd in G.nodes_data():
        label = str(nd.get("label", nid))
        com = node_comm.get(nid, -1)
        entry = {
            "id": nid,
            "l": label,
            "t": nd.get("file_type", "code"),
            "com": com,
            "deg": degrees.get(nid, 0),
        }
        if nd.get("source_file"):
            entry["f"] = str(nd.get("source_file"))
        if nid.startswith(("hyperedge::", "url::", "cite::")):
            entry["t"] = "hyperedge" if "hyperedge" in nid else "reference"
        if top_pagerank:
            pr = top_pagerank.get(nid)
            if pr:
                entry["pr"] = round(pr, 6)
        # keep only giant labels as tooltip fallback beyond 20 chars
        if len(label) > 120:
            entry["l"] = label[:117] + "..."
        nodes_payload.append(entry)

    id2i = {n["id"]: i for i, n in enumerate(nodes_payload)}
    links_payload = []
    for u, v in G.edges_view():
        if u not in idset or v not in idset:
            continue
        d = G.get_edge_data(u, v, {}) or {}
        links_payload.append(
            {
                "s": id2i.get(u, -1),
                "t": id2i.get(v, -1),
                "r": str(d.get("relation", ""))[:40],
                "c": str(d.get("confidence", "EXTRACTED")),
                "w": float(d.get("weight", 1.0) or 1.0),
            }
        )
    # deterministic order to make output stable run-to-run
    links_payload.sort(key=lambda l: (l["s"], l["t"], l["r"]))
    data = {"nodes": nodes_payload, "links": links_payload, "directed": G.is_directed()}
    html = (
        _TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__PALETTE__", json.dumps(_PALETTE))
        .replace(
            "__STATS__",
            f"{G.number_of_nodes():,} nodes · {G.number_of_edges():,} edges · {len(communities)} communities",
        )
        .replace("__LABELS__", json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False))
    )
    atomic_write(out_path, html)
    return str(out_path)
