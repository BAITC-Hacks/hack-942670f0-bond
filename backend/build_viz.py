#!/usr/bin/env python3
"""
Собирает самодостаточный интерактивный дашборд out/vertex.html:
движок графа + данные + логика инлайнятся в один файл (offline, без сервера).

    python build_viz.py --out ../out --vendor ../viz/vendor
"""
import argparse, json
from pathlib import Path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вершина — граф денег</title>
<style>
  :root{
    --bg:#0e1117; --panel:#161b26; --panel2:#1e2432; --line:#2a3140;
    --tx:#e6e9ef; --mut:#8a93a6;
    --coordinator:#ff5470; --consolidator:#ffd166; --distributor:#4ea8de;
    --transit:#c77dff; --terminal:#06d6a0; --peripheral:#6b7280;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
  #app{display:flex;height:100vh;overflow:hidden}
  /* ---- sidebar ---- */
  #side{width:320px;flex:0 0 320px;background:var(--panel);border-right:1px solid var(--line);
    display:flex;flex-direction:column;overflow-y:auto}
  #side h1{font-size:20px;margin:16px 16px 2px;letter-spacing:.5px}
  #side .sub{font-size:12px;color:var(--mut);margin:0 16px 12px}
  .box{margin:0 16px 14px;padding:12px;background:var(--panel2);border:1px solid var(--line);border-radius:10px}
  .box h3{margin:0 0 8px;font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--mut)}
  .legend-row{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:13px;cursor:pointer;user-select:none}
  .legend-row.off{opacity:.35}
  .dot{width:11px;height:11px;border-radius:50%;flex:0 0 11px}
  .legend-row .cnt{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums}
  label.rng{display:block;font-size:12px;color:var(--mut);margin-bottom:4px}
  input[type=range]{width:100%}
  input[type=text],select{width:100%;background:#0e131c;border:1px solid var(--line);color:var(--tx);
    border-radius:8px;padding:7px 9px;font-size:13px;margin-top:4px}
  .btn{display:block;width:100%;margin-top:8px;padding:9px;border:1px solid var(--line);border-radius:8px;
    background:#222c3d;color:var(--tx);font-size:13px;cursor:pointer}
  .btn:hover{background:#2b3750}
  .btn.primary{background:#2f6df6;border-color:#2f6df6}
  .btn.primary:hover{background:#4a82ff}
  #toplist{margin:0 16px 16px}
  .top-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:12.5px}
  .top-item:hover{background:var(--panel2)}
  .top-item .rk{color:var(--mut);width:22px;font-variant-numeric:tabular-nums}
  .top-item .gid{font-family:ui-monospace,Menlo,monospace;font-size:11px}
  .top-item .pr{margin-left:auto;color:var(--mut)}
  /* ---- graph ---- */
  #main{flex:1;position:relative;min-width:0}
  #graph{position:absolute;inset:0}
  #stats{position:absolute;left:12px;bottom:12px;font-size:12px;color:var(--mut);
    background:rgba(14,17,23,.7);padding:6px 10px;border-radius:8px;border:1px solid var(--line)}
  #hint{position:absolute;left:50%;top:14px;transform:translateX(-50%);font-size:12px;color:var(--mut);
    background:rgba(14,17,23,.75);padding:6px 12px;border-radius:20px;border:1px solid var(--line)}
  /* ---- detail ---- */
  #detail{position:absolute;top:0;right:0;width:340px;height:100%;background:var(--panel);
    border-left:1px solid var(--line);transform:translateX(100%);transition:transform .18s;
    overflow-y:auto;padding:16px}
  #detail.open{transform:none}
  #detail .close{float:right;cursor:pointer;color:var(--mut);font-size:20px;line-height:1}
  #detail .rolechip{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;color:#0e1117}
  #detail .gidbig{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:var(--mut);margin:8px 0}
  #detail .kv{display:flex;justify-content:space-between;font-size:13px;padding:5px 0;border-bottom:1px solid var(--line)}
  #detail .kv .k{color:var(--mut)}
  #detail .ev{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px;
    font-size:12.5px;line-height:1.5;margin:10px 0}
  #detail h4{font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.6px;margin:14px 0 6px}
  .nb{display:flex;align-items:center;gap:7px;font-size:12px;padding:4px 6px;border-radius:6px;cursor:pointer}
  .nb:hover{background:var(--panel2)}
  .nb .gid{font-family:ui-monospace,Menlo,monospace;font-size:11px}
  .nb .amt{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums}
</style>
</head>
<body>
<div id="app">
  <aside id="side">
    <h1>ВЕРШИНА</h1>
    <p class="sub">от дропа до организатора за 4 колена</p>

    <div class="box" id="legend"><h3>Роли · клик = фильтр</h3></div>

    <div class="box">
      <h3>Фильтры</h3>
      <label class="rng">Мин. приоритет: <b id="prv">0.00</b></label>
      <input type="range" id="prio" min="0" max="1" step="0.01" value="0">
      <select id="cluster"></select>
      <input type="text" id="search" placeholder="Поиск по gid…">
      <button class="btn primary" id="focus">🎯 Фокус: топ-30 + окружение</button>
      <button class="btn" id="reset">Сбросить вид</button>
    </div>

    <h3 style="margin:0 16px 6px;font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--mut)">Кого проверять первым</h3>
    <div id="toplist"></div>
  </aside>

  <div id="main">
    <div id="graph"></div>
    <div id="hint">Размер узла = приоритет · цвет = роль · стрелка = направление денег · клик = детали</div>
    <div id="stats"></div>
    <div id="detail"><span class="close" onclick="closeDetail()">×</span><div id="dbody"></div></div>
  </div>
</div>

<script>/*__LIB__*/</script>
<script>
const GRAPH = /*__DATA__*/;
const SUMMARY = /*__SUMMARY__*/;
const ROLES = ["coordinator","consolidator","distributor","transit","terminal","peripheral"];
const RU = {coordinator:"Координатор (организатор)",consolidator:"Сборщик",distributor:"Распределитель",
            transit:"Транзит (мул)",terminal:"Терминал (осело)",peripheral:"Периферия"};
const css = getComputedStyle(document.documentElement);
const COL = {}; ROLES.forEach(r=> COL[r]=css.getPropertyValue('--'+r).trim());

// precompute
const NODES = GRAPH.nodes;
NODES.forEach(n=> n._val = 1 + n.priority*22);
const LINKS_RAW = GRAPH.links.map(l=>{
  const w = Math.max(0.4, Math.log10(l.sum_kzt+10)/3.2);
  return {source:l.source, target:l.target, sum_kzt:l.sum_kzt, n_tx:l.n_tx, _w:w};
});
const byId = {}; NODES.forEach(n=> byId[n.id]=n);
const adj = {}; NODES.forEach(n=> adj[n.id]={in:[],out:[]});
LINKS_RAW.forEach(l=>{ adj[l.target].in.push(l); adj[l.source].out.push(l); });
const TOP = [...NODES].sort((a,b)=>b.priority-a.priority).slice(0,30);
const TOPSET = new Set(TOP.map(n=>n.id));
const fmt = x=> Math.round(x).toLocaleString('ru-RU');

// ---- state ----
const roleOn = {}; ROLES.forEach(r=> roleOn[r]=true);
let minPrio=0, clusterSel='all', focusSet=null, selected=null;

// ---- legend ----
const leg = document.getElementById('legend');
ROLES.forEach(r=>{
  const c = (SUMMARY.roles[r]||0);
  const row=document.createElement('div'); row.className='legend-row'; row.dataset.role=r;
  row.innerHTML=`<span class="dot" style="background:${COL[r]}"></span>${RU[r]}<span class="cnt">${c}</span>`;
  row.onclick=()=>{ roleOn[r]=!roleOn[r]; row.classList.toggle('off',!roleOn[r]); apply(); };
  leg.appendChild(row);
});

// ---- cluster select ----
const csel=document.getElementById('cluster');
const clusters=[...new Set(NODES.map(n=>n.cluster))].sort((a,b)=>a-b);
csel.innerHTML=`<option value="all">Все кластеры (${clusters.length})</option>`+
  clusters.map(c=>`<option value="${c}">Кластер ${c} (${NODES.filter(n=>n.cluster===c).length})</option>`).join('');
csel.onchange=e=>{ clusterSel=e.target.value; apply(); };

// ---- filters ----
const prio=document.getElementById('prio'), prv=document.getElementById('prv');
prio.oninput=e=>{ minPrio=+e.target.value; prv.textContent=minPrio.toFixed(2); apply(); };
document.getElementById('focus').onclick=()=>{
  focusSet=new Set(TOPSET);
  TOP.forEach(n=>{ adj[n.id].in.forEach(l=>focusSet.add(l.source)); adj[n.id].out.forEach(l=>focusSet.add(l.target)); });
  apply(true);
};
document.getElementById('reset').onclick=()=>{
  focusSet=null; minPrio=0; prio.value=0; prv.textContent='0.00'; clusterSel='all'; csel.value='all';
  ROLES.forEach(r=>roleOn[r]=true); document.querySelectorAll('.legend-row').forEach(el=>el.classList.remove('off'));
  apply(true);
};
const search=document.getElementById('search');
search.onchange=()=>{
  const n=byId[search.value.trim()];
  if(n){ if(focusSet && !focusSet.has(n.id)) focusSet=null; roleOn[n.role]=true;
    document.querySelector('.legend-row[data-role="'+n.role+'"]').classList.remove('off');
    apply(); setTimeout(()=>{ Graph.centerAt(n.x,n.y,600); Graph.zoom(4,600); showDetail(n); },60); }
};

// ---- top list ----
const tl=document.getElementById('toplist');
TOP.forEach((n,i)=>{
  const d=document.createElement('div'); d.className='top-item';
  d.innerHTML=`<span class="rk">${i+1}</span><span class="dot" style="background:${COL[n.role]}"></span>`+
              `<span class="gid">${n.id}</span><span class="pr">${n.priority.toFixed(2)}</span>`;
  d.onclick=()=>{ if(focusSet&&!focusSet.has(n.id))focusSet=null; roleOn[n.role]=true;
    document.querySelector('.legend-row[data-role="'+n.role+'"]').classList.remove('off'); apply();
    setTimeout(()=>{ Graph.centerAt(n.x,n.y,600); Graph.zoom(4,600); showDetail(n); },60); };
  tl.appendChild(d);
});

// ---- graph ----
const el=document.getElementById('graph');
const Graph=ForceGraph()(el)
  .backgroundColor('#0e1117')
  .nodeId('id').nodeVal('_val')
  .nodeRelSize(2.4)
  .nodeColor(n=> n===selected ? '#ffffff' : COL[n.role])
  .nodeLabel(n=> `<div style="font-family:monospace;font-size:11px">gid ${n.id}</div>`+
    `<b style="color:${COL[n.role]}">${RU[n.role]}</b> · приоритет ${n.priority.toFixed(2)}`)
  .linkColor(()=> 'rgba(140,152,176,0.13)')
  .linkWidth('_w')
  .linkDirectionalArrowLength(3.2).linkDirectionalArrowRelPos(1)
  .nodeCanvasObjectMode(()=> 'after')
  .nodeCanvasObject((n,ctx,scale)=>{
    const r=Math.sqrt(n._val)*2.4;
    if(n.is_seed){ ctx.beginPath(); ctx.arc(n.x,n.y,r+1.6,0,2*Math.PI);
      ctx.strokeStyle='rgba(255,255,255,.8)'; ctx.lineWidth=0.7; ctx.stroke(); }
    if(n===selected){ ctx.beginPath(); ctx.arc(n.x,n.y,r+3,0,2*Math.PI);
      ctx.strokeStyle=COL[n.role]; ctx.lineWidth=1.6; ctx.stroke(); }
    if(n===selected || (n.priority>0.8 && scale>1.4)){
      ctx.font=`${Math.max(3.5,4.5/scale*scale)}px monospace`; ctx.fillStyle='#e6e9ef';
      ctx.textAlign='center'; ctx.fillText(n.id.slice(-6), n.x, n.y-r-3); }
  })
  .onNodeClick(showDetail)
  .onBackgroundClick(closeDetail)
  .cooldownTicks(120);
Graph.d3Force('charge').strength(-42);

function apply(recenter){
  const nodes=NODES.filter(n=>{
    if(!roleOn[n.role]) return false;
    if(n.priority<minPrio) return false;
    if(clusterSel!=='all' && n.cluster!=+clusterSel) return false;
    if(focusSet && !focusSet.has(n.id)) return false;
    return true;
  });
  const shown=new Set(nodes.map(n=>n.id));
  const links=LINKS_RAW.filter(l=> shown.has(l.source)&&shown.has(l.target)).map(l=>({...l}));
  Graph.graphData({nodes,links});
  document.getElementById('stats').textContent=
    `Показано ${nodes.length} из ${NODES.length} узлов · ${links.length} связей`;
  if(recenter) setTimeout(()=>Graph.zoomToFit(500,60),400);
}

function showDetail(n){
  selected=n;
  const inN=adj[n.id].in, outN=adj[n.id].out;
  const chip=`<span class="rolechip" style="background:${COL[n.role]}">${RU[n.role]}</span>`;
  const kv=(k,v)=>`<div class="kv"><span class="k">${k}</span><span>${v}</span></div>`;
  const nb=(l,dir)=>{ const other=dir==='in'?l.source:l.target;
    return `<div class="nb" onclick="jump('${other}')"><span class="dot" style="background:${COL[byId[other].role]}"></span>`+
      `<span class="gid">${other}</span><span class="amt">${fmt(l.sum_kzt)}₸ · ${l.n_tx}</span></div>`; };
  document.getElementById('dbody').innerHTML=
    chip+`<div class="gidbig">gid ${n.id}</div>`+
    kv('Приоритет проверки', `<b>${n.priority.toFixed(3)}</b>`)+
    kv('Уверенность роли', n.role_score.toFixed(3))+
    kv('Кластер', n.cluster)+ kv('Колено (depth)', n.depth+(n.is_seed?' · SEED':''))+
    kv('Получил', fmt(n.in_kzt)+'₸ от '+n.in_deg)+ kv('Отправил', fmt(n.out_kzt)+'₸ на '+n.out_deg)+
    (n.truncated?kv('⚠︎ Обрезан 4-м коленом','да'):'')+
    `<h4>Обоснование (evidence)</h4><div class="ev">${n.evidence}</div>`+
    `<h4>Платят ему (${inN.length})</h4>`+ (inN.slice(0,12).map(l=>nb(l,'in')).join('')||'<span class="k" style="font-size:12px;color:var(--mut)">—</span>')+
    `<h4>Платит он (${outN.length})</h4>`+ (outN.slice(0,12).map(l=>nb(l,'out')).join('')||'<span class="k" style="font-size:12px;color:var(--mut)">—</span>');
  document.getElementById('detail').classList.add('open');
  Graph.nodeColor(Graph.nodeColor());
}
function jump(id){ const n=byId[id]; if(!n)return;
  if(focusSet&&!focusSet.has(id)){ focusSet.add(id); apply(); }
  setTimeout(()=>{ if(n.x!=null){Graph.centerAt(n.x,n.y,500);Graph.zoom(4,500);} showDetail(n); },50); }
function closeDetail(){ selected=null; document.getElementById('detail').classList.remove('open'); Graph.nodeColor(Graph.nodeColor()); }
window.jump=jump; window.closeDetail=closeDetail; window.showDetail=showDetail;

apply(); setTimeout(()=>Graph.zoomToFit(600,70),600);
addEventListener('resize',()=>{ Graph.width(el.clientWidth).height(el.clientHeight); });
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../out")
    ap.add_argument("--vendor", default="../viz/vendor")
    a = ap.parse_args()
    out = Path(a.out)
    lib = (Path(a.vendor) / "force-graph.min.js").read_text()
    data = (out / "graph.json").read_text()
    summary = (out / "summary.json").read_text()
    html = (TEMPLATE
            .replace("/*__LIB__*/", lib)
            .replace("/*__DATA__*/", data)
            .replace("/*__SUMMARY__*/", summary))
    (out / "vertex.html").write_text(html)
    kb = len(html.encode()) / 1024
    print(f"Собрано: {out/'vertex.html'}  ({kb:.0f} КБ, самодостаточный, offline)")


if __name__ == "__main__":
    main()
