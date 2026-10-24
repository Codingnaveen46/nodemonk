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
const id2i = new Map(N.map((n,i)=>[n.id,i]));
// initial layout: communities in a ring, members packed in a circle
const comms = {};
N.forEach(n=>{ const c = n.com ?? -1; (comms[c] = comms[c]||[]).push(n); });
const ckeys = Object.keys(comms);
const R0 = Math.max(400*Math.sqrt(ckeys.length), 900);
ckeys.forEach((k,ki)=>{
  const arr = comms[k];
  const ang0 = 2*Math.PI*ki/ckeys.length, r0 = R0*(ki===0?0:1);
  const cx = Math.cos(ang0)*r0, cy = Math.sin(ang0)*r0;
  const rin = 30+8*Math.sqrt(arr.length);
  arr.forEach((n,ni)=>{
    const ang = 2*Math.PI*ni/arr.length;
    n.x = cx + Math.cos(ang)*rin; n.y = cy + Math.sin(ang)*rin;
    n.vx=0; n.vy=0; n.deg = n.deg||0;
    n.col = PALETTE[(k|0)%PALETTE.length];
  });
});
// edge arrays once
const EL = L.map(l=>[id2i.get(l.s), id2i.get(l.t), l.r||"", l.c||"EXTRACTED", l.w??1]).filter(e=>e[0]!==undefined&&e[1]!==undefined);

const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");
let W=0,H=0,DPR=1, tX=0,tY=0, scale=1, dragging=false, moved=false, hoverI=-1, selI=-1;
let physics=true, showLabels=false,CommFilter=null, bigDegree=1;
N.forEach(n=>{ if(n.deg>bigDegree) bigDegree=n.deg; });
function resize(){ const r=canvas.getBoundingClientRect(); DPR=window.devicePixelRatio||1; W=r.width; H=r.height; canvas.width=W*DPR; canvas.height=H*DPR; ctx.setTransform(DPR,0,0,DPR,0,0);}
window.addEventListener("resize", resize);

// grid-accelerated repulsion + springs, chunked per frame so giant graphs never freeze
const TARGET_K = 55; // ideal link length
function stepPhysics(iter){
  for(let it=0; it<iter; it++){
    // springs
    for(const [a,b] of EL){
      const na=N[a], nb=N[b];
      if(!na||!nb) continue;
      const dx=nb.x-na.x, dy=nb.y-na.y; const d=Math.hypot(dx,dy)||0.01;
      const f = (d-TARGET_K)/d*0.06;
      const fx=dx*f, fy=dy*f;
      na.vx+=fx; nb.vx-=fx; na.vy+=fy; nb.vy-=fy;
    }
    // grid repulsion
    const cell = TARGET_K*2.4;
    const grid = new Map();
    for(let i=0;i<N.length;i++){
      const n=N[i]; const key=((n.x/cell)|0)+","+((n.y/cell)|0);
      let arr=grid.get(key); if(!arr){arr=[];grid.set(key,arr);} arr.push(i);
    }
    for(let i=0;i<N.length;i++){
      const n=N[i];
      const gx=((n.x/cell)|0), gy=((n.y/cell)|0);
      for(let ox=-1;ox<=1;ox++) for(let oy=-1;oy<=1;oy++){
        const arr=grid.get((gx+ox)+","+(gy+oy)); if(!arr) continue;
        for(const j of arr){ if(j<=i) continue;
          const o=N[j];
          let dx=n.x-o.x, dy=n.y-o.y; let d2=dx*dx+dy*dy;
          if(d2<1) { dx=(Math.random()-0.5); dy=(Math.random()-0.5); d2=dx*dx+dy*dy; }
          if(d2 > cell*cell) continue;
          const f=1200/d2;
          const d=Math.sqrt(d2);
          n.vx+=dx/d*f; n.vy+=dy/d*f; o.vx-=dx/d*f; o.vy-=dy/d*f;
        }
      }
      // centering
      n.vx+=-n.x*0.0006; n.vy+=-n.y*0.0006;
    }
    for(let i=0;i<N.length;i++){
      const n=N[i];
      n.vx*=0.86; n.vy*=0.86;
      n.x+=Math.max(-14,Math.min(14,n.vx)); n.y+=Math.max(-14,Math.min(14,n.vy));
    }
  }
}
function render(){
  ctx.save();
  ctx.clearRect(0,0,W,H);
  ctx.translate(W/2,H/2); ctx.scale(scale,scale); ctx.translate(tX,tY);
  const inv = 1/scale;
  // edges
  ctx.lineWidth = 1*inv;
  for(const [a,b,rel,conf] of EL){
    const na=N[a], nb=N[b];
    if(!na||!nb) continue;
    if(CommFilter!=null && na.com!=CommFilter && nb.com!=CommFilter) continue;
    const isSel = selI>=0 && !(a===selI||b===selI);
    const dimmed = selI>=0 && isSel;
    ctx.strokeStyle = dimmed ? "rgba(31,41,55,.35)" :
      conf==="EXTRACTED" ? "rgba(99,179,237,.5)" :
      conf==="AMBIGUOUS" ? "rgba(217,119,6,.35)" : "rgba(74,124,246,.3)";
    ctx.beginPath(); ctx.moveTo(na.x,na.y); ctx.lineTo(nb.x,nb.y); ctx.stroke();
  }
  // nodes
  for(let i=0;i<N.length;i++){
    const n=N[i];
    let r = 2 + Math.pow(n.deg/bigDegree, 0.5)*7;
    const dimmed = selI>=0 && i!==selI && !nbrSet.has(i);
    ctx.fillStyle = dimmed? "rgba(75,85,99,.4)" : n.col;
    ctx.beginPath(); ctx.arc(n.x,n.y,r,0,6.2832); ctx.fill();
    if(n===hoverN || i===selI){ ctx.strokeStyle="#fff"; ctx.lineWidth=1.6*inv; ctx.stroke(); }
  }
  // labels (LOD: only big nodes when dense)
  if(showLabels || scale>0.6 || hoverN){
    ctx.save(); ctx.scale(inv,inv);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = "rgba(229,231,235,.92)";
    for(let i=0;i<N.length;i++){
      const n=N[i];
      const limit = scale>0.6 ? n.deg >= bigDegree*0.22 : n.deg >= bigDegree*0.55;
      if(!(n===hoverN || i===selI || limit)) continue;
      ctx.fillText((n.l||"").slice(0,42), n.x*inv+6, n.y*inv+4);
    }
    ctx.restore();
  }
  ctx.restore();
  status.textContent = N.length.toLocaleString()+" nodes · "+L.length.toLocaleString()+" edges · zoom "+(scale).toFixed(2)+"x";
}
let nbrSet = new Set(), hoverN=null, selN=null;
function neighbors(i){ const out=new Set(); for(const [a,b] of EL){ if(a===i) out.add(b); if(b===i) out.add(a);} return out; }
function toGraph(x,y){ const wx=(x-W/2)/scale-tX, wy=(y-H/2)/scale-tY; return [wx,wy]; }
let mX=0,mY=0;
canvas.addEventListener("pointermove", ev=>{
  const rect=canvas.getBoundingClientRect();
  const px=ev.clientX-rect.left, py=ev.clientY-rect.top;
  if(dragging && ev.buttons){ tX+=(px-mX)/scale; tY+=(py-mY)/scale; moved=true; }
  else { const [wx,wy]=toGraph(px,py); let best=-1, bestD=12/scale; for(let i=0;i<N.length;i++){ const n=N[i]; const d=Math.hypot(n.x-wx,n.y-wy); if(d<bestD+4){bestD=d;best=i;} } hoverI=best; hoverN=best>=0?N[best]:null; }
  mX=px; mY=py;
});
canvas.addEventListener("pointerdown", ev=>{ dragging=true; moved=false; });
canvas.addEventListener("pointerup", ev=>{
  dragging=false;
  if(!moved){
    if(hoverI>=0){ select(hoverI); } else { deselect(); }
  }
});
canvas.addEventListener("wheel", ev=>{
  ev.preventDefault();
  const f = ev.deltaY<0 ? 1.12 : 0.89;
  const rect=canvas.getBoundingClientRect();
  const px=ev.clientX-rect.left, py=ev.clientY-rect.top;
  const [wx,wy]=toGraph(px,py);
  scale=Math.max(0.03, Math.min(6, scale*f));
  tX = px - W/2 - wx*scale;
  tY = py - H/2 - wy*scale;
}, {passive:false});

function select(i){ selI=i; selN=N[i]; nbrSet=neighbors(i); showInspector(i); }
function deselect(){ selI=-1; selN=null; nbrSet=new Set(); document.getElementById("inspector").style.display="none"; }
function showInspector(i){
  const n = N[i]; const el = document.getElementById("inspector");
  const links = [];
  for(const [a,b,rel,conf] of EL){
    if(a===i) links.push([b,rel,conf,false]);
    if(b===i) links.push([a,rel,conf,true]);
  }
  const src = n.f? `<a class="meta" href="#">${n.f}</a>`:"";
  el.innerHTML = `<h3>${esc(n.l||n.id)}</h3>
    <div class="meta">${esc(n.t||"")} ${n.com!=null?`· community ${COM_LABELS[n.com]!=null?esc(COM_LABELS[n.com]):n.com}`:""} ${n.deg?`· degree ${n.deg}`:""}</div>
    ${src}
    <ul>${links.slice(0,80).map(([o,rel,conf,back])=>`<li>${back?"&larr;":"&rarr;"} ${esc(rel||"rel")} ${conf?`<span class="conf ${conf}">${conf}</span>`:""} <a href="#" data-n="${o}" class="jump">${esc(N[o].l||N[o].id)}</a></li>`).join("")}
    ${links.length>80?`<li>… ${links.length-80} more</li>`:""}</ul>`;
  el.style.display="block";
  el.querySelectorAll(".jump").forEach(a=>a.onclick=(e)=>{e.preventDefault(); select(+e.currentTarget.dataset.n);});
}
const COM_LABELS = __LABELS__;
function esc(s){ return String(s).replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]); }

// search
const qEl = document.getElementById("q"), hitsEl = document.getElementById("hits");
qEl.addEventListener("input", ()=>{
  const term = qEl.value.trim().toLowerCase();
  hitsEl.innerHTML = ""; if(!term) { return; }
  let count=0;
  for(let i=0;i<N.length;i++){
    const l=(N[i].l||"").toLowerCase();
    if(l.includes(term)){
      if(count<30){ const d=document.createElement("div"); d.className="hit"; d.textContent=(N[i].l||N[i].id).slice(0,60)+(N[i].t?`  (${N[i].t})`:""); d.onclick=()=>{ focusNode(i); }; hitsEl.appendChild(d);}
      count++;
    }
  }
  if(count>30){ const more=document.createElement("div"); more.className="hit dimmed"; more.textContent= "+"+(count-30)+" more matches (all nodes searched)"; hitsEl.appendChild(more);}
  if(!count){ hitsEl.innerHTML="<div class='hit dimmed'>no match</div>"; }
});
function focusNode(i){ select(i); const n=N[i]; tX=-n.x; tY=-n.y; }
const legendEl = document.getElementById("legend");
function buildLegend(){
  const rows = [];
  rows.push(`<div class="crow" data-c="-1"><span class="dot" style="background:#555"></span>All communities <span class="tag">${N.length.toLocaleString()}</span></div>`);
  for(const k of Object.keys(comms).sort((a,b)=>(a|0)-(b|0))){
    const lblk = COM_LABELS[k]!=null ? COM_LABELS[k] : ("Community "+k);
    rows.push(`<div class="crow" data-c="${k}"><span class="dot" style="background:${PALETTE[(k|0)%PALETTE.length]}"></span>${esc(lblk)} <span class="tag">${comms[k].length.toLocaleString()}</span></div>`);
  }
  legendEl.innerHTML = rows.join("");
  legendEl.querySelectorAll(".crow").forEach(r=>r.onclick=()=>{
    const val = r.dataset.c==="-1"?null:(r.dataset.c|0);
    CommFilter = CommFilter===val?null:val;
    legendEl.querySelectorAll(".crow").forEach(x=>x.classList.toggle("dimmed", CommFilter!=null&&x.dataset.c!==(CommFilter+"")));
  });
}
document.getElementById("btnRelax").onclick = (e)=>{ physics=!physics; e.target.classList.toggle("active", physics); };
document.getElementById("btnLabels").onclick = (e)=>{ showLabels=!showLabels; e.target.classList.toggle("active", showLabels); };
document.getElementById("btnReset").onclick = ()=>{ scale=1; tX=0; tY=0; deselect(); };
document.getElementById("btnExport").onclick = ()=>{
  const tmp=document.createElement("canvas"); tmp.width=canvas.width; tmp.height=canvas.height;
  tmp.getContext("2d").drawImage(canvas,0,0);
  const a=document.createElement("a"); a.download="nodemonk-graph.png"; a.href=tmp.toDataURL("image/png"); a.click();
};
const status = document.getElementById("status");
resize(); buildLegend();
let frame=0;
function animate(){
  if(physics) stepPhysics(2);
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
