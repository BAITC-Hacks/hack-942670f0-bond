#!/usr/bin/env python3
"""
Собирает самодостаточный интерактивный дашборд out/vertex.html (минимализм, офлайн):
движок графа + данные + логика инлайнятся в один файл. 4 вкладки:
Граф · Кейсы · Устойчивость · Ассистент.

    python build_viz.py --out ../out --vendor ../viz/vendor
"""
import argparse, json, sys
from pathlib import Path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Вершина — граф денег</title>
<style>
  :root{
    --bg:#0d0f13; --panel:#14171d; --panel2:#1a1e26; --line:#242a34; --line2:#2f3746;
    --tx:#e8ebf0; --mut:#8b93a3; --accent:#3b82f6; --accent2:#2563eb;
    --coordinator:#f6465d; --consolidator:#f0b429; --distributor:#3b82f6;
    --transit:#a855f7; --terminal:#10b981; --peripheral:#5b6472;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,Arial,sans-serif;
    font-size:14px;-webkit-font-smoothing:antialiased}
  body{display:flex;flex-direction:column;height:100vh;overflow:hidden}
  button{font-family:inherit}
  ::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:#2a313d;border-radius:6px}

  /* ---- topbar ---- */
  #top{display:flex;align-items:center;gap:22px;flex:0 0 56px;height:56px;padding:0 20px;
    background:var(--bg);border-bottom:1px solid var(--line)}
  #brand{display:flex;align-items:baseline;gap:9px}
  #brand .logo{font-size:16px;color:var(--accent)}
  #brand b{font-size:15px;letter-spacing:2px;font-weight:600}
  #brand span{font-size:11px;color:var(--mut);letter-spacing:.5px}
  #tabs{display:flex;gap:2px}
  #tabs .tab{background:none;border:none;color:var(--mut);font-size:13.5px;padding:8px 14px;
    cursor:pointer;border-radius:8px;display:flex;align-items:center;gap:7px}
  #tabs .tab:hover{color:var(--tx)}
  #tabs .tab.active{color:var(--tx);background:var(--panel2)}
  #tabs .tab .badge{min-width:18px;padding:0 6px;background:var(--accent);color:#fff;border-radius:10px;
    font-size:11px;line-height:17px;text-align:center}
  #topstats{margin-left:auto;font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}

  #views{flex:1;min-height:0;position:relative}
  .view{position:absolute;inset:0;display:none}
  .view.active{display:flex}

  /* ---- graph view ---- */
  #side{width:300px;flex:0 0 300px;background:var(--panel);border-right:1px solid var(--line);
    display:flex;flex-direction:column;overflow-y:auto;padding:16px}
  .grp{margin-bottom:18px}
  .grp h3{margin:0 0 9px;font-size:11px;text-transform:uppercase;letter-spacing:.9px;color:var(--mut);font-weight:600}
  .lrow{display:flex;align-items:center;gap:9px;padding:5px 6px;border-radius:7px;cursor:pointer;font-size:13px}
  .lrow:hover{background:var(--panel2)}.lrow.off{opacity:.32}
  .dot{width:10px;height:10px;border-radius:50%;flex:0 0 10px}
  .lrow .cnt{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums;font-size:12px}
  label.rng{display:block;font-size:12px;color:var(--mut);margin:10px 0 3px}
  input[type=range]{width:100%;accent-color:var(--accent)}
  input[type=text],select{width:100%;background:#0e131b;border:1px solid var(--line);color:var(--tx);
    border-radius:8px;padding:8px 10px;font-size:13px;margin-top:6px;outline:none}
  input[type=text]:focus,select:focus{border-color:var(--accent)}
  .btn{display:block;width:100%;margin-top:8px;padding:9px;border:1px solid var(--line);border-radius:8px;
    background:var(--panel2);color:var(--tx);font-size:13px;cursor:pointer}
  .btn:hover{background:#222836}
  .btn.primary{background:var(--accent);border-color:var(--accent)}.btn.primary:hover{background:var(--accent2)}
  .toggle{display:flex;align-items:center;gap:9px;font-size:13px;cursor:pointer;padding:7px 6px;border-radius:7px}
  .toggle:hover{background:var(--panel2)}
  .sw{width:34px;height:19px;border-radius:12px;background:#2a313d;position:relative;flex:0 0 34px;transition:.15s}
  .sw::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;background:#8b93a3;transition:.15s}
  .toggle.on .sw{background:var(--accent)}.toggle.on .sw::after{left:17px;background:#fff}
  .titem{display:flex;align-items:center;gap:8px;padding:6px 7px;border-radius:7px;cursor:pointer;font-size:12.5px}
  .titem:hover{background:var(--panel2)}
  .titem .rk{color:var(--mut);width:20px;font-variant-numeric:tabular-nums}
  .titem .gid{font-family:ui-monospace,Menlo,monospace;font-size:11px}
  .titem .pr{margin-left:auto;color:var(--mut)}

  #main{flex:1;position:relative;min-width:0}
  #graph{position:absolute;inset:0}
  #hint{position:absolute;left:50%;top:12px;transform:translateX(-50%);font-size:11.5px;color:var(--mut);
    background:rgba(13,15,19,.82);padding:6px 13px;border-radius:20px;border:1px solid var(--line)}
  #gstats{position:absolute;left:12px;bottom:12px;font-size:11.5px;color:var(--mut);
    background:rgba(13,15,19,.82);padding:5px 10px;border-radius:8px;border:1px solid var(--line)}
  /* detail */
  #detail{position:absolute;top:0;right:0;width:330px;height:100%;background:var(--panel);
    border-left:1px solid var(--line);transform:translateX(100%);transition:transform .18s;overflow-y:auto;padding:18px}
  #detail.open{transform:none}
  #detail .x{float:right;cursor:pointer;color:var(--mut);font-size:22px;line-height:1}
  .chip{display:inline-block;padding:3px 11px;border-radius:20px;font-size:12px;font-weight:600;color:#0d0f13}
  .gidm{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--mut);margin:9px 0}
  .kv{display:flex;justify-content:space-between;font-size:13px;padding:6px 0;border-bottom:1px solid var(--line)}
  .kv .k{color:var(--mut)} .kv .warn{color:var(--consolidator)}
  .evbox{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12.5px;line-height:1.55;margin:11px 0}
  #detail h4{font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.6px;margin:15px 0 6px}
  .nb{display:flex;align-items:center;gap:7px;font-size:12px;padding:4px 6px;border-radius:6px;cursor:pointer}
  .nb:hover{background:var(--panel2)} .nb .gid{font-family:ui-monospace,Menlo,monospace;font-size:11px}
  .nb .amt{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums}

  /* ---- generic scroll page (cases/resilience/assistant) ---- */
  .page{flex:1;overflow-y:auto;padding:22px 26px}
  .page h2{font-size:18px;margin:0 0 4px;font-weight:600}
  .page .lead{font-size:13px;color:var(--mut);margin:0 0 18px;max-width:760px;line-height:1.55}

  /* ---- cases ---- */
  #chead{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:16px}
  .chip2{background:var(--panel2);border:1px solid var(--line);color:var(--tx);font-size:12.5px;padding:6px 13px;border-radius:20px;cursor:pointer}
  .chip2.active{background:var(--accent);border-color:var(--accent)}
  #cstats{font-size:12.5px;color:var(--mut);margin-left:6px}
  .cboard{display:grid;grid-template-columns:repeat(auto-fill,minmax(365px,1fr));gap:14px;align-items:start}
  .ccard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px;border-left:3px solid var(--line)}
  .ccard.sev-high{border-left-color:var(--coordinator)}.ccard.sev-medium{border-left-color:var(--consolidator)}
  .ccard.sev-low{border-left-color:var(--peripheral)} .ccard.st-closed{opacity:.6}
  .chd{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:7px}
  .chd .cid{font-family:ui-monospace,Menlo,monospace;color:var(--mut)}
  .bsev{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700}
  .b-high{background:var(--coordinator);color:#fff}.b-medium{background:var(--consolidator);color:#241a00}.b-low{background:var(--peripheral);color:#0d0f13}
  .cstt{margin-left:auto;padding:2px 10px;border-radius:20px;font-size:11px;border:1px solid var(--line)}
  .cstt.new{color:#60a5fa;border-color:#28405f}.cstt.review{color:var(--consolidator);border-color:#5a4a1e}.cstt.closed{color:var(--terminal);border-color:#1c5343}
  .ctl{font-size:14px;font-weight:600;line-height:1.35;margin:2px 0 7px}
  .cmt{font-size:12px;color:var(--mut);margin-bottom:9px;font-variant-numeric:tabular-nums}
  .cact{font-size:12.5px;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:9px 11px;margin-bottom:9px;line-height:1.45}
  .ccard details{margin:5px 0;font-size:12px}.ccard summary{cursor:pointer;color:var(--mut)}
  .ccard details .bd{margin-top:6px;max-height:180px;overflow-y:auto}
  .lg{font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:2px 0;border-bottom:1px solid #1b2130}
  .kn{display:flex;align-items:center;gap:7px;padding:4px 6px;border-radius:6px;cursor:pointer}.kn:hover{background:var(--panel2)}
  .kn .gid{font-family:ui-monospace,Menlo,monospace;font-size:11px}
  .cnote{width:100%;min-height:44px;background:#0e131b;border:1px solid var(--line);color:var(--tx);border-radius:8px;
    padding:8px 10px;font-size:12px;margin:9px 0;resize:vertical;font-family:inherit;outline:none}
  .cbtns{display:flex;flex-wrap:wrap;gap:6px}
  .cbtns button{border:1px solid var(--line);background:var(--panel2);color:var(--tx);font-size:12px;padding:7px 11px;border-radius:7px;cursor:pointer}
  .cbtns button:hover{filter:brightness(1.15)}
  .cbtns .work{background:var(--accent);border-color:var(--accent)}
  .cbtns .esc{background:var(--coordinator);border-color:var(--coordinator)}
  .cbtns .fp{background:#334155;border-color:#334155}
  .cbtns .mon{background:var(--terminal);border-color:var(--terminal);color:#052e22}
  .cwhen{font-size:10.5px;color:var(--mut);margin-top:7px}

  /* ---- resilience ---- */
  .rtable{border-collapse:collapse;font-size:13px;margin:8px 0 20px}
  .rtable th,.rtable td{padding:9px 15px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
  .rtable th{color:var(--mut);font-weight:600;text-align:right}.rtable td:first-child,.rtable th:first-child{text-align:left}
  .rtable .go{color:var(--accent);cursor:pointer}
  .rbars{display:flex;align-items:flex-end;gap:18px;height:210px;padding:14px 8px;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;margin-bottom:8px;max-width:640px}
  .rbar{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;height:100%;justify-content:flex-end}
  .rbar .bar{width:100%;max-width:52px;background:linear-gradient(180deg,var(--accent),#1e3a8a);border-radius:6px 6px 0 0}
  .rbar .lab{font-size:11px;color:var(--mut)}.rbar .val{font-size:11.5px;font-variant-numeric:tabular-nums}

  /* ---- assistant ---- */
  #asuggest{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
  #arow{display:flex;gap:8px;max-width:760px;margin-bottom:16px}
  #ain{flex:1}
  #alog{max-width:820px}
  .amsg{border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:12px;background:var(--panel)}
  .amsg .q{color:var(--mut);font-size:12px;margin-bottom:7px}
  .amsg .a{font-size:13.5px;line-height:1.5}
  .ares{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
  .ares button{border:1px solid var(--line);background:var(--panel2);color:var(--tx);font-size:12px;
    padding:6px 10px;border-radius:7px;cursor:pointer;display:flex;align-items:center;gap:6px}
  .ares button:hover{background:#222836}
  @media(max-width:820px){#side{width:230px;flex-basis:230px}}
</style>
</head>
<body>
<div id="top">
  <div id="brand"><span class="logo">▲</span><b>ВЕРШИНА</b><span>AML · граф денег</span></div>
  <div id="tabs">
    <button class="tab active" data-view="graph">🕸 Граф</button>
    <button class="tab" data-view="cases">📁 Кейсы <span class="badge" id="caseBadge">0</span></button>
    <button class="tab" data-view="resil">🛡 Устойчивость</button>
    <button class="tab" data-view="assist">💬 Ассистент</button>
  </div>
  <div id="topstats"></div>
</div>

<div id="views">
  <!-- ГРАФ -->
  <div id="view-graph" class="view active">
    <aside id="side">
      <div class="grp"><h3>Роли · клик = фильтр</h3><div id="legend"></div></div>
      <div class="grp"><h3>Фильтры</h3>
        <label class="rng">Мин. приоритет: <b id="prv">0.00</b></label>
        <input type="range" id="prio" min="0" max="1" step="0.01" value="0">
        <select id="cluster"></select>
        <input type="text" id="search" placeholder="Поиск по gid…">
      </div>
      <div class="grp"><h3>Вид</h3>
        <div class="toggle" id="tgCyc"><span class="sw"></span><span>Подсветить циклы (layering)</span></div>
        <button class="btn primary" id="focus">Фокус: топ-30 + окружение</button>
        <button class="btn" id="reset">Сбросить вид</button>
      </div>
      <div class="grp"><h3>Кого проверять первым</h3><div id="toplist"></div></div>
    </aside>
    <div id="main">
      <div id="graph"></div>
      <div id="hint">Размер = приоритет · цвет = роль · стрелка = направление денег · клик = детали</div>
      <div id="gstats"></div>
      <div id="detail"><span class="x" onclick="closeDetail()">×</span><div id="dbody"></div></div>
    </div>
  </div>

  <!-- КЕЙСЫ -->
  <div id="view-cases" class="view">
    <div class="page">
      <h2>Кейсы</h2>
      <p class="lead">Система автоматически собрала «логи» (переводы между ключевыми узлами) и завела кейсы
        по подозрительным кластерам. Возьмите кейс в работу и закройте с решением. Статусы сохраняются в браузере.</p>
      <div id="chead">
        <button class="chip2 active" data-f="all">Все</button>
        <button class="chip2" data-f="new">Новые</button>
        <button class="chip2" data-f="review">В работе</button>
        <button class="chip2" data-f="closed">Закрытые</button>
        <span id="cstats"></span>
      </div>
      <div class="cboard" id="cboard"></div>
    </div>
  </div>

  <!-- УСТОЙЧИВОСТЬ -->
  <div id="view-resil" class="view">
    <div class="page">
      <h2>Устойчивость сети</h2>
      <p class="lead">Что произойдёт с сетью, если изъять топ-N узлов рейтинга. Показаны метрики слабой связности
        всей оставшейся сети. Рейтинг не переобучается после удаления; исходные данные не меняются.</p>
      <div class="rbars" id="rbars"></div>
      <div style="font-size:11.5px;color:var(--mut);margin-bottom:18px">Высота столбца — размер крупнейшей компоненты после удаления топ-N.</div>
      <table class="rtable" id="rtable"></table>
    </div>
  </div>

  <!-- АССИСТЕНТ -->
  <div id="view-assist" class="view">
    <div class="page">
      <h2>Ассистент аналитика</h2>
      <p class="lead">Локальный помощник (офлайн, по правилам — без интернета и внешних API). Отвечает по графу
        и даёт кнопки перехода к узлам. Спросите про роли, конкретный gid, кластер, циклы или приоритет.</p>
      <div id="asuggest"></div>
      <div id="arow">
        <input type="text" id="ain" placeholder="Например: кто координаторы? / кластер 2 / циклы / gid 100000003684369100">
        <button class="btn primary" style="width:auto;margin:0;padding:9px 18px" id="aask">Спросить</button>
      </div>
      <div id="alog"></div>
    </div>
  </div>
</div>

<script>/*__LIB__*/</script>
<script>
const GRAPH=/*__DATA__*/, SUMMARY=/*__SUMMARY__*/, CASES=/*__CASES__*/, RESIL=/*__RESIL__*/;
const ROLES=["coordinator","consolidator","distributor","transit","terminal","peripheral"];
const RU={coordinator:"Координатор (организатор)",consolidator:"Сборщик",distributor:"Распределитель",
          transit:"Транзит (мул)",terminal:"Терминал (осело)",peripheral:"Периферия"};
const RUS={coordinator:"координатор",consolidator:"сборщик",distributor:"распределитель",transit:"транзит",terminal:"терминал",peripheral:"периферия"};
const css=getComputedStyle(document.documentElement);
const COL={}; ROLES.forEach(r=>COL[r]=css.getPropertyValue('--'+r).trim());
const fmt=x=>Math.round(x).toLocaleString('ru-RU');
const esc=s=>String(s==null?'':s).replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));

const NODES=GRAPH.nodes; NODES.forEach(n=>n._val=1+n.priority*22);
const LINKS=GRAPH.links.map(l=>({source:l.source,target:l.target,sum_kzt:l.sum_kzt,n_tx:l.n_tx,cyc:l.cyc,
  _w:Math.max(0.4,Math.log10(l.sum_kzt+10)/3.2)}));
const byId={}; NODES.forEach(n=>byId[n.id]=n);
const adj={}; NODES.forEach(n=>adj[n.id]={in:[],out:[]});
LINKS.forEach(l=>{adj[l.target].in.push(l);adj[l.source].out.push(l);});
const RANKED=[...NODES].sort((a,b)=>b.priority-a.priority||a.id.localeCompare(b.id));
const TOP=RANKED.slice(0,30), TOPSET=new Set(TOP.map(n=>n.id));

document.getElementById('topstats').textContent=
  `${SUMMARY.n_nodes} узлов · ${SUMMARY.n_edges} связей · ${SUMMARY.n_clusters} кластеров`;

// ===== state =====
const roleOn={}; ROLES.forEach(r=>roleOn[r]=true);
let minPrio=0, clusterSel='all', focusSet=null, removeN=0, showCyc=false, selected=null;

// ===== legend =====
const leg=document.getElementById('legend');
ROLES.forEach(r=>{
  const row=document.createElement('div'); row.className='lrow'; row.dataset.role=r;
  row.innerHTML=`<span class="dot" style="background:${COL[r]}"></span>${RU[r]}<span class="cnt">${SUMMARY.roles[r]||0}</span>`;
  row.onclick=()=>{roleOn[r]=!roleOn[r];row.classList.toggle('off',!roleOn[r]);apply();};
  leg.appendChild(row);
});
// ===== cluster select =====
const csel=document.getElementById('cluster');
const clusters=[...new Set(NODES.map(n=>n.cluster))].sort((a,b)=>a-b);
csel.innerHTML=`<option value="all">Все кластеры (${clusters.length})</option>`+
  clusters.map(c=>`<option value="${c}">Кластер ${c} (${NODES.filter(n=>n.cluster===c).length})</option>`).join('');
csel.onchange=e=>{clusterSel=e.target.value;apply();};
// ===== filters =====
const prio=document.getElementById('prio'),prv=document.getElementById('prv');
prio.oninput=e=>{minPrio=+e.target.value;prv.textContent=minPrio.toFixed(2);apply();};
const tgCyc=document.getElementById('tgCyc');
tgCyc.onclick=()=>{showCyc=!showCyc;tgCyc.classList.toggle('on',showCyc);Graph.linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());};
document.getElementById('focus').onclick=()=>{
  focusSet=new Set(TOPSET);
  TOP.forEach(n=>{adj[n.id].in.forEach(l=>focusSet.add(l.source));adj[n.id].out.forEach(l=>focusSet.add(l.target));});
  apply(true);
};
document.getElementById('reset').onclick=()=>{
  focusSet=null;minPrio=0;prio.value=0;prv.textContent='0.00';clusterSel='all';csel.value='all';removeN=0;
  ROLES.forEach(r=>roleOn[r]=true);document.querySelectorAll('.lrow').forEach(el=>el.classList.remove('off'));
  apply(true);
};
const search=document.getElementById('search');
search.onchange=()=>{const n=byId[search.value.trim()];
  if(n){focusSet=null;roleOn[n.role]=true;document.querySelector('.lrow[data-role="'+n.role+'"]').classList.remove('off');
    apply();setTimeout(()=>{Graph.centerAt(n.x,n.y,600);Graph.zoom(4,600);showDetail(n);},60);}};
// ===== top list =====
const tl=document.getElementById('toplist');
TOP.forEach((n,i)=>{const d=document.createElement('div');d.className='titem';
  d.innerHTML=`<span class="rk">${i+1}</span><span class="dot" style="background:${COL[n.role]}"></span>`+
    `<span class="gid">${n.id}</span><span class="pr">${n.priority.toFixed(2)}</span>`;
  d.onclick=()=>{focusSet=null;roleOn[n.role]=true;document.querySelector('.lrow[data-role="'+n.role+'"]').classList.remove('off');
    apply();setTimeout(()=>{Graph.centerAt(n.x,n.y,600);Graph.zoom(4,600);showDetail(n);},60);};
  tl.appendChild(d);});

// ===== graph =====
const el=document.getElementById('graph');
const Graph=ForceGraph()(el).backgroundColor('#0d0f13')
  .nodeId('id').nodeVal('_val').nodeRelSize(2.3)
  .nodeColor(n=>n===selected?'#fff':COL[n.role])
  .nodeLabel(n=>`<div style="font-family:monospace;font-size:11px">gid ${n.id}</div><b style="color:${COL[n.role]}">${RU[n.role]}</b> · приоритет ${n.priority.toFixed(2)}`)
  .linkColor(l=> (showCyc&&l.cyc)?'rgba(246,70,93,0.85)':'rgba(130,142,166,0.12)')
  .linkWidth(l=> (showCyc&&l.cyc)?2:l._w)
  .linkDirectionalArrowLength(3).linkDirectionalArrowRelPos(1)
  .nodeCanvasObjectMode(()=> 'after')
  .nodeCanvasObject((n,ctx,scale)=>{
    const r=Math.sqrt(n._val)*2.3;
    if(n.truncated){ctx.beginPath();ctx.arc(n.x,n.y,r+1.7,0,2*Math.PI);ctx.setLineDash([2,2]);
      ctx.strokeStyle=COL.consolidator;ctx.lineWidth=0.7;ctx.stroke();ctx.setLineDash([]);}
    else if(n.is_seed){ctx.beginPath();ctx.arc(n.x,n.y,r+1.6,0,2*Math.PI);ctx.strokeStyle='rgba(255,255,255,.85)';ctx.lineWidth=0.7;ctx.stroke();}
    if(n===selected){ctx.beginPath();ctx.arc(n.x,n.y,r+3,0,2*Math.PI);ctx.strokeStyle=COL[n.role];ctx.lineWidth=1.6;ctx.stroke();}
    if(n===selected||(n.priority>0.8&&scale>1.4)){ctx.font='4px monospace';ctx.fillStyle='#e8ebf0';ctx.textAlign='center';ctx.fillText(n.id.slice(-6),n.x,n.y-r-3);}
  })
  .onNodeClick(showDetail).onBackgroundClick(closeDetail).cooldownTicks(120);
Graph.d3Force('charge').strength(-42);

function apply(recenter){
  const rem=removeN>0?new Set(RANKED.slice(0,removeN).map(n=>n.id)):null;
  const nodes=NODES.filter(n=>{
    if(!roleOn[n.role])return false;
    if(n.priority<minPrio)return false;
    if(clusterSel!=='all'&&n.cluster!=+clusterSel)return false;
    if(focusSet&&!focusSet.has(n.id))return false;
    if(rem&&rem.has(n.id))return false;
    return true;});
  const shown=new Set(nodes.map(n=>n.id));
  const links=LINKS.filter(l=>shown.has(l.source)&&shown.has(l.target)).map(l=>({...l}));
  Graph.graphData({nodes,links});
  document.getElementById('gstats').textContent=
    `Показано ${nodes.length} из ${NODES.length} узлов · ${links.length} связей`+(removeN?` · удалён топ-${removeN}`:'');
  if(recenter)setTimeout(()=>Graph.zoomToFit(500,60),400);
}
function showDetail(n){selected=n;
  const inN=adj[n.id].in,outN=adj[n.id].out;
  const kv=(k,v,w)=>`<div class="kv"><span class="k">${k}</span><span class="${w?'warn':''}">${v}</span></div>`;
  const nb=(l,dir)=>{const o=dir==='in'?l.source:l.target;
    return `<div class="nb" onclick="jump('${o}')"><span class="dot" style="background:${COL[byId[o].role]}"></span><span class="gid">${o}</span><span class="amt">${fmt(l.sum_kzt)}₸·${l.n_tx}</span></div>`;};
  document.getElementById('dbody').innerHTML=
    `<span class="chip" style="background:${COL[n.role]}">${RU[n.role]}</span><div class="gidm">gid ${n.id}</div>`+
    kv('Приоритет проверки',`<b>${n.priority.toFixed(3)}</b>`)+kv('Уверенность роли',n.role_score.toFixed(3))+
    kv('Кластер',n.cluster)+kv('Колено (depth)',n.depth+(n.is_seed?' · SEED':''))+
    kv('Получил',fmt(n.in_kzt)+'₸ от '+n.in_deg)+kv('Отправил',fmt(n.out_kzt)+'₸ на '+n.out_deg)+
    kv('В цикле (layering)',n.cycle?'да':'нет')+(n.truncated?kv('⚠ Обрезан 4-м коленом','исход не наблюдаем',true):'')+
    `<h4>Обоснование</h4><div class="evbox">${esc(n.evidence)}</div>`+
    `<h4>Платят ему (${inN.length})</h4>`+(inN.slice(0,12).map(l=>nb(l,'in')).join('')||'<span class="k">—</span>')+
    `<h4>Платит он (${outN.length})</h4>`+(outN.slice(0,12).map(l=>nb(l,'out')).join('')||'<span class="k">—</span>');
  document.getElementById('detail').classList.add('open');Graph.nodeColor(Graph.nodeColor());
}
function jump(id){const n=byId[id];if(!n)return;if(focusSet&&!focusSet.has(id)){focusSet.add(id);apply();}
  setTimeout(()=>{if(n.x!=null){Graph.centerAt(n.x,n.y,500);Graph.zoom(4,500);}showDetail(n);},50);}
function closeDetail(){selected=null;document.getElementById('detail').classList.remove('open');Graph.nodeColor(Graph.nodeColor());}
window.jump=jump;window.closeDetail=closeDetail;window.showDetail=showDetail;
apply();setTimeout(()=>Graph.zoomToFit(600,70),600);
addEventListener('resize',()=>Graph.width(el.clientWidth).height(el.clientHeight));

// ===== tabs =====
document.querySelectorAll('#tabs .tab').forEach(t=>{t.onclick=()=>{
  document.querySelectorAll('#tabs .tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');document.getElementById('view-'+t.dataset.view).classList.add('active');
  if(t.dataset.view==='graph')setTimeout(()=>Graph.width(el.clientWidth).height(el.clientHeight),0);
};});
function openInGraph(gid){document.querySelector('#tabs .tab[data-view="graph"]').click();setTimeout(()=>jump(gid),80);}
window.openInGraph=openInGraph;

// ===== cases =====
const ST={new:'Новый',review:'В работе',closed:'Закрыт'};
const SEV={high:'HIGH',medium:'MED',low:'LOW'};
const RES={escalate:'Эскалация в ПО',false_positive:'Ложное срабатывание',monitor:'На мониторинге'};
const LSK='vertex_cases_v2';let cstate={};try{cstate=JSON.parse(localStorage.getItem(LSK)||'{}')}catch(e){}
function csave(){try{localStorage.setItem(LSK,JSON.stringify(cstate))}catch(e){}}
function cg(id){return cstate[id]||{status:'new'}}
function cset(id,p){cstate[id]=Object.assign(cg(id),p,{updated_at:new Date().toISOString()});csave();renderCases();}
window.cset=cset;let cfilter='all';
function renderCases(){
  const b=document.getElementById('cboard');b.innerHTML='';
  const cnt={new:0,review:0,closed:0};CASES.forEach(c=>cnt[cg(c.id).status]++);
  document.getElementById('cstats').textContent=`Открытых: ${cnt.new} · В работе: ${cnt.review} · Закрыто: ${cnt.closed} из ${CASES.length}`;
  document.querySelectorAll('#chead .chip2').forEach(f=>f.classList.toggle('active',f.dataset.f===cfilter));
  CASES.filter(c=>cfilter==='all'||cg(c.id).status===cfilter).forEach(c=>{
    const s=cg(c.id),st=s.status;
    const logs=c.logs.map(l=>`<div class="lg">${esc(l)}</div>`).join('')||'<div class="lg">—</div>';
    const kns=c.key_nodes.map(n=>`<div class="kn" onclick="openInGraph('${n.gid}')"><span class="dot" style="background:${COL[n.role]}"></span><span class="gid">…${n.gid.slice(-6)}</span> <span style="color:var(--mut)">${RUS[n.role]} · ${n.priority}</span></div>`).join('');
    const cb=`<button class="esc" onclick="cset('${c.id}',{status:'closed',resolution:'escalate'})">Эскалация в ПО</button><button class="fp" onclick="cset('${c.id}',{status:'closed',resolution:'false_positive'})">Ложное</button><button class="mon" onclick="cset('${c.id}',{status:'closed',resolution:'monitor'})">Мониторинг</button>`;
    let btns;
    if(st==='new')btns=`<button class="work" onclick="cset('${c.id}',{status:'review'})">▶ Взять в работу</button>`+cb;
    else if(st==='review')btns=cb+`<button onclick="cset('${c.id}',{status:'new'})">↩ В новые</button>`;
    else btns=`<button onclick="cset('${c.id}',{status:'new',resolution:null})">↩ Переоткрыть</button>`;
    const res=(st==='closed'&&s.resolution)?`<div class="cwhen">Решение: <b>${RES[s.resolution]||s.resolution}</b></div>`:'';
    const wh=s.updated_at?`<div class="cwhen">обновлено ${new Date(s.updated_at).toLocaleString('ru-RU')}</div>`:'';
    const card=document.createElement('div');card.className=`ccard sev-${c.severity} st-${st}`;
    card.innerHTML=`<div class="chd"><span class="cid">${c.id}</span><span class="bsev b-${c.severity}">${SEV[c.severity]}</span><span class="cstt ${st}">${ST[st]}</span></div>`+
      `<div class="ctl">${esc(c.title)}</div>`+
      `<div class="cmt">приоритет ${c.priority} · ${c.n_nodes} узлов · ${c.n_seed} seed · ${fmt(c.turnover_kzt)}₸</div>`+
      `<div class="cact">▶ ${esc(c.recommended_action)}</div>`+
      `<details><summary>Ключевые узлы (${c.key_nodes.length})</summary><div class="bd">${kns}</div></details>`+
      `<details><summary>Логи активности (${c.logs.length})</summary><div class="bd">${logs}</div></details>`+
      `<textarea class="cnote" placeholder="Заметка аналитика…" onchange="cset('${c.id}',{note:this.value})">${esc(s.note)}</textarea>`+
      `<div class="cbtns">${btns}</div>${res}${wh}`;
    b.appendChild(card);});
  document.getElementById('caseBadge').textContent=CASES.filter(c=>cg(c.id).status!=='closed').length;
}
document.querySelectorAll('#chead .chip2').forEach(f=>f.onclick=()=>{cfilter=f.dataset.f;renderCases();});
renderCases();

// ===== resilience =====
(function(){
  const max=Math.max(...RESIL.map(r=>r.largest))||1;
  document.getElementById('rbars').innerHTML=RESIL.map(r=>
    `<div class="rbar"><div class="val">${r.largest}</div><div class="bar" style="height:${Math.round(r.largest/max*150)}px"></div><div class="lab">топ-${r.removed}</div></div>`).join('');
  document.getElementById('rtable').innerHTML=
    `<tr><th>Удалено топ-N</th><th>Узлы</th><th>Рёбра</th><th>Компоненты</th><th>Крупнейшая</th><th>Одиночные</th><th></th></tr>`+
    RESIL.map(r=>`<tr><td>${r.removed}</td><td>${r.nodes}</td><td>${r.edges}</td><td>${r.components}</td><td>${r.largest}</td><td>${r.singletons}</td>`+
      `<td class="go" onclick="applyRemove(${r.removed})">${r.removed?'показать на графе →':''}</td></tr>`).join('');
})();
function applyRemove(n){removeN=n;focusSet=null;document.querySelector('#tabs .tab[data-view="graph"]').click();apply(true);}
window.applyRemove=applyRemove;

// ===== assistant (локальный, по правилам) =====
function topBy(pred,n){return RANKED.filter(pred).slice(0,n||8);}
function answer(q){
  q=q.toLowerCase().trim();
  const gidm=q.match(/\d{6,}/);
  if(gidm){const n=byId[gidm[0]];
    if(n)return{text:`gid ${n.id} — <b>${RU[n.role]}</b>, приоритет ${n.priority.toFixed(3)}. ${esc(n.evidence)}`,nodes:[n]};
    return{text:`Узел gid ${gidm[0]} не найден в графе.`,nodes:[]};}
  const cm=q.match(/кластер\s*(\d+)/);
  if(cm){const c=+cm[1];const ns=RANKED.filter(n=>n.cluster===c).slice(0,10);
    return{text:`В кластере ${c}: ${NODES.filter(n=>n.cluster===c).length} узлов. Ключевые по приоритету:`,nodes:ns};}
  if(/координатор|организатор|вершин|глав/.test(q))return{text:`Координаторы (кандидаты в организаторы), ${SUMMARY.roles.coordinator} шт. — проверять первыми:`,nodes:topBy(n=>n.role==='coordinator',10)};
  if(/сборщик|консолид|собира/.test(q))return{text:`Сборщики (точки консолидации), ${SUMMARY.roles.consolidator} шт.:`,nodes:topBy(n=>n.role==='consolidator')};
  if(/распредел|веер|рассыл/.test(q))return{text:`Распределители (веерная рассылка), ${SUMMARY.roles.distributor} шт.:`,nodes:topBy(n=>n.role==='distributor')};
  if(/транзит|мул|насквозь|layering/.test(q))return{text:`Транзитные узлы (мулы), ${SUMMARY.roles.transit} шт.:`,nodes:topBy(n=>n.role==='transit')};
  if(/терминал|осел|сток|конечн/.test(q))return{text:`Терминалы (деньги осели), ${SUMMARY.roles.terminal} шт. — топ по входу:`,nodes:topBy(n=>n.role==='terminal')};
  if(/seed|сид/.test(q))return{text:`Seed-клиенты (исходные), ${SUMMARY.n_seed} шт. — топ по приоритету:`,nodes:topBy(n=>n.is_seed)};
  if(/цикл|возврат/.test(q))return{text:`Узлы в возвратных циклах (признак layering), ${SUMMARY.in_cycle} шт.:`,nodes:topBy(n=>n.cycle)};
  if(/провер|перв|приоритет|важн|топ/.test(q))return{text:`Кого проверять первым (топ по приоритету):`,nodes:TOP.slice(0,10)};
  return{text:`Не понял вопрос. Попробуйте: «координаторы», «сборщики», «кластер 2», «циклы», «кого проверять первым» или введите gid.`,nodes:[]};
}
const SUGG=['Кто координаторы?','Сборщики','Кого проверять первым','Циклы (layering)','Кластер 2','Seed-клиенты'];
const asg=document.getElementById('asuggest');
SUGG.forEach(s=>{const b=document.createElement('button');b.className='chip2';b.textContent=s;b.onclick=()=>{document.getElementById('ain').value=s;ask();};asg.appendChild(b);});
function ask(){const q=document.getElementById('ain').value;if(!q.trim())return;
  const r=answer(q);
  const btns=r.nodes.map(n=>`<button onclick="openInGraph('${n.id}')"><span class="dot" style="background:${COL[n.role]}"></span>…${n.id.slice(-6)} · ${n.priority.toFixed(2)}</button>`).join('');
  const div=document.createElement('div');div.className='amsg';
  div.innerHTML=`<div class="q">Вопрос: ${esc(q)}</div><div class="a">${r.text}</div>`+(btns?`<div class="ares">${btns}</div>`:'');
  const log=document.getElementById('alog');log.prepend(div);}
document.getElementById('aask').onclick=ask;
document.getElementById('ain').addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
</script>
</body>
</html>
"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../out")
    ap.add_argument("--vendor", default="../viz/vendor")
    a = ap.parse_args()
    out = Path(a.out)
    lib = (Path(a.vendor) / "force-graph.min.js").read_text(encoding="utf-8")
    data = (out / "graph.json").read_text(encoding="utf-8")
    summary = (out / "summary.json").read_text(encoding="utf-8")
    cases = (out / "cases.json").read_text(encoding="utf-8") if (out / "cases.json").exists() else "[]"
    resil = (out / "resilience.json").read_text(encoding="utf-8") if (out / "resilience.json").exists() else "[]"
    html = (TEMPLATE
            .replace("/*__LIB__*/", lib)
            .replace("/*__DATA__*/", data)
            .replace("/*__SUMMARY__*/", summary)
            .replace("/*__CASES__*/", cases)
            .replace("/*__RESIL__*/", resil))
    (out / "vertex.html").write_text(html, encoding="utf-8")
    print(f"Собрано: {out/'vertex.html'}  ({len(html.encode())/1024:.0f} КБ, минимализм, offline)")


if __name__ == "__main__":
    main()
