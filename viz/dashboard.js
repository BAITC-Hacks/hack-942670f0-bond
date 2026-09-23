"use strict";
const $ = id => document.getElementById(id);
const LABELS = {coordinator:"Координирующий",consolidator:"Сборщик",distributor:"Распределитель",transit:"Транзит",terminal:"Терминал*",peripheral:"Периферия"};
const COLORS = {coordinator:"#f46c7c",consolidator:"#c69af5",distributor:"#68dac0",transit:"#f5ad64",terminal:"#699feb",peripheral:"#5c7085"};
try{document.documentElement.dataset.theme=localStorage.getItem("vertex_theme")||"light";}catch(e){document.documentElement.dataset.theme="light";}
const gv=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const GT={};function readGT(){GT.sel=gv("--g-sel")||"#ffffff";GT.dim=gv("--g-dim")||"#344452";GT.seed=gv("--g-seedring")||"#c9e4e0";GT.label=gv("--g-label")||"#e7f6f1";GT.link=gv("--g-link")||"rgba(113,145,170,.18)";GT.linksel=gv("--g-linksel")||"#89dac7";}readGT();
const fmt = value => Number(value).toLocaleString("ru-RU",{maximumFractionDigits:0});
const esc = value => String(value).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const nodes = GRAPH.nodes, links = GRAPH.links, byId = new Map(nodes.map(n=>[n.id,n]));
const rankedNodes = nodes.filter(n=>n.rank!==null).sort((a,b)=>a.rank-b.rank);
const adjacency = new Map(nodes.map(n=>[n.id,{in:[],out:[]}]));
links.forEach(l=>{adjacency.get(l.source).out.push(l);adjacency.get(l.target).in.push(l);});
for(const a of adjacency.values()) for(const dir of ["in","out"]) a[dir].sort((a,b)=>b.sum_kzt-a.sum_kzt || a.source.localeCompare(b.source));
const state = {roles:new Set(Object.keys(LABELS)),min:0,cluster:"all",threat:false,cycles:false,blocked:0,focus:null,selected:null};
let highlighted=new Set(),cycleEdges=new Set(),aiAvailable=false,shownNodes=[],shownLinks=[];
const edgeKey = (u,v) => u+":"+v;
const neighborSet = id => new Set([id,...adjacency.get(id).in.map(l=>l.source),...adjacency.get(id).out.map(l=>l.target)]);
function toast(message){$("toast").textContent=message;$("toast").hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$("toast").hidden=true,4200);}
$("m-nodes").textContent=fmt(SUMMARY.n_nodes);$("m-edges").textContent=fmt(SUMMARY.n_edges);$("m-clusters").textContent=fmt(SUMMARY.n_clusters);
$("blocking").max=GRAPH.resilience.length-1;
$("roles").innerHTML=Object.keys(LABELS).map(r=>'<label class="role"><input type="checkbox" checked data-role="'+r+'"><span class="dot" style="background:'+COLORS[r]+'"></span>'+LABELS[r]+'<small>'+SUMMARY.roles[r]+'</small></label>').join("");
$("roles").addEventListener("change",e=>{const r=e.target.dataset.role;if(!r)return;e.target.checked?state.roles.add(r):state.roles.delete(r);apply();});
$("cluster").innerHTML='<option value="all">Все сообщества · '+GRAPH.clusters.length+'</option>'+[...GRAPH.clusters].sort((a,b)=>a.cluster_id-b.cluster_id).map(c=>'<option value="'+c.cluster_id+'">Кластер '+c.cluster_id+' · '+c.n_nodes+' узлов</option>').join("");
function updateCluster(){
 const c=GRAPH.clusters.find(c=>String(c.cluster_id)===state.cluster);
 $("hypothesis").textContent=c?c.hypothesis:"Выберите кластер, чтобы увидеть гипотезу и состав сообщества.";
 $("cluster-ai").disabled=!c||!aiAvailable;
}
$("cluster").onchange=e=>{state.cluster=e.target.value;state.focus=null;clearSelection();updateCluster();apply(true);};
$("priority").oninput=e=>{state.min=+e.target.value;$("priority-value").textContent=state.min.toFixed(2);apply();};
$("threat").onchange=e=>{state.threat=e.target.checked;state.focus=null;apply(true);};
$("cycles").onchange=e=>{state.cycles=e.target.checked;apply();};
$("blocking").oninput=e=>{state.blocked=+e.target.value;$("blocking-value").textContent=state.blocked;apply(true);};
function resetFilters(resetSimulation=false){
 state.roles=new Set(Object.keys(LABELS));state.min=0;state.cluster="all";state.threat=false;state.focus=null;
 $("priority").value=0;$("priority-value").textContent="0.00";$("cluster").value="all";$("threat").checked=false;
 document.querySelectorAll("[data-role]").forEach(el=>{el.checked=true;});
 if(resetSimulation){state.blocked=0;$("blocking").value=0;$("blocking-value").textContent="0";state.cycles=false;$("cycles").checked=false;}
 updateCluster();
}
function resetAll(){resetFilters(true);clearSelection();$("search").value="";$("search-status").textContent="";apply(true);}
$("reset").onclick=resetAll;$("empty-reset").onclick=resetAll;
$("focus-top").onclick=()=>{resetFilters();state.focus=new Set();rankedNodes.forEach(n=>neighborSet(n.id).forEach(id=>state.focus.add(id)));clearSelection();apply(true);};
$("toplist").innerHTML=rankedNodes.map(n=>'<tr tabindex="0" role="button" data-id="'+n.id+'" aria-label="Открыть gid '+n.id+'"><td>'+n.rank+'</td><td class="gid">'+n.id+'</td><td title="'+LABELS[n.role]+'"><span class="dot" style="background:'+COLORS[n.role]+'"></span> '+LABELS[n.role]+'</td><td>'+n.priority.toFixed(3)+'</td></tr>').join("");
$("toplist").addEventListener("click",e=>{const row=e.target.closest("[data-id]");if(row)selectNode(row.dataset.id,true);});
$("toplist").addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){const row=e.target.closest("[data-id]");if(row){e.preventDefault();selectNode(row.dataset.id,true);}}});
$("search").oninput=()=>{
 const id=$("search").value.trim();
 if(!id){$("search-status").textContent="";return;}
 if(byId.has(id)){selectNode(id,false);$("search-status").textContent="Участник найден. Фильтры сброшены.";}
 else $("search-status").textContent="Введите полный gid из выгрузки.";
};
function clearSelection(){state.selected=null;highlighted=new Set();$("detail").hidden=true;document.querySelectorAll("#toplist tr").forEach(r=>r.classList.remove("active"));}
$("detail-close").onclick=()=>{clearSelection();apply();};

// Stable starting positions by cluster, independent of Math.random.
nodes.forEach((n,i)=>{
 const angle=n.cluster*2.39996322973,r=65*Math.sqrt(n.cluster+1);
 const jitter=(i*137.508)*Math.PI/180;
 n.x=Math.cos(angle)*r+Math.cos(jitter)*(8+Math.sqrt(i%90)*5);
 n.y=Math.sin(angle)*r+Math.sin(jitter)*(8+Math.sqrt(i%90)*5);
 n._val=1+n.priority*16;
});
const pane=$("canvas-pane"),canvas=$("graph");
const Graph=ForceGraph()(canvas).width(pane.clientWidth).height(pane.clientHeight)
 .backgroundColor("rgba(0,0,0,0)").nodeId("id").nodeVal("_val").nodeRelSize(2.7)
 .nodeColor(n=>state.selected===n.id?GT.sel:state.selected&&!highlighted.has(n.id)?GT.dim:COLORS[n.role])
 .nodeLabel(n=>esc(n.id)+" · "+LABELS[n.role]+" · "+n.priority.toFixed(3))
 .linkColor(l=>state.cycles&&cycleEdges.has(edgeKey(endpoint(l.source),endpoint(l.target)))?"#ff617d":
   state.selected&&(endpoint(l.source)===state.selected||endpoint(l.target)===state.selected)?GT.linksel:GT.link)
 .linkWidth(l=>Math.max(.35,Math.log10(l.sum_kzt+1)/5)*(state.cycles&&cycleEdges.has(edgeKey(endpoint(l.source),endpoint(l.target)))?2.5:1))
 .linkDirectionalArrowLength(l=>state.cycles&&cycleEdges.has(edgeKey(endpoint(l.source),endpoint(l.target)))?5:3)
 .linkDirectionalArrowRelPos(.96)
 .nodeCanvasObjectMode(()=>"after").nodeCanvasObject((n,ctx,scale)=>{
   const radius=Math.sqrt(n._val)*2.7;
   if(n.is_seed||n.truncated){ctx.save();ctx.beginPath();ctx.arc(n.x,n.y,radius+2,0,Math.PI*2);
     ctx.strokeStyle=n.truncated?"#f3c675":GT.seed;ctx.lineWidth=1;
     if(n.truncated)ctx.setLineDash([2.5,2.5]);ctx.stroke();ctx.restore();}
   if(n.id===state.selected){ctx.beginPath();ctx.arc(n.x,n.y,radius+5,0,Math.PI*2);ctx.strokeStyle=GT.sel;ctx.lineWidth=1.2;ctx.stroke();}
   if(n.id===state.selected||(n.rank&&n.rank<=8&&scale>1.2)){ctx.font=(10/scale)+"px Consolas";ctx.fillStyle=GT.label;ctx.textAlign="center";ctx.fillText("…"+n.id.slice(-7),n.x,n.y-radius-5);}
 }).onNodeClick(n=>{state.selected=n.id;highlighted=neighborSet(n.id);renderCard(n);apply();})
 .onBackgroundClick(()=>{clearSelection();apply();}).cooldownTicks(100).d3VelocityDecay(.35);
function endpoint(x){return typeof x==="object"?x.id:x;}
Graph.d3Force("charge").strength(-35);
Graph.d3Force("link").distance(45);
function centerSelected(){
 const n=byId.get(state.selected);
 if(n&&shownNodes.includes(n))Graph.centerAt(n.x+$("detail").clientWidth/(2*Graph.zoom()),n.y,350);
}
Graph.onEngineStop(()=>{if(state.selected)centerSelected();});
function selectNode(id,isolate=false){
 if(typeof showWorkspace==="function")showWorkspace("graph");
 const n=byId.get(id);if(!n)return;
 resetFilters();
 const removed=new Set(GRAPH.resilience[state.blocked].removed);
 if(removed.has(id)){state.blocked=0;$("blocking").value=0;$("blocking-value").textContent="0";toast("Симуляция сброшена: выбранный узел был исключён.");}
 if(isolate)state.focus=neighborSet(id);
 state.selected=id;highlighted=neighborSet(id);apply();
 renderCard(n);
 Graph.zoom(isolate?2.2:2.7,350);centerSelected();
 document.querySelectorAll("#toplist tr").forEach(r=>r.classList.toggle("active",r.dataset.id===id));
}
function apply(recenter=false){
 const simulation=GRAPH.resilience[state.blocked],removed=new Set(simulation.removed);
 shownNodes=nodes.filter(n=>!removed.has(n.id)&&state.roles.has(n.role)&&n.priority>=state.min
   &&(state.cluster==="all"||String(n.cluster)===state.cluster)
   &&(!state.threat||["coordinator","consolidator","transit"].includes(n.role))
   &&(!state.focus||state.focus.has(n.id)));
 const visible=new Set(shownNodes.map(n=>n.id));
 cycleEdges=new Set();let nCycles=0;
 for(const cycle of GRAPH.cycles){if(cycle.every(id=>visible.has(id))){nCycles++;for(let i=0;i<cycle.length;i++)cycleEdges.add(edgeKey(cycle[i],cycle[(i+1)%cycle.length]));}}
 shownLinks=links.filter(l=>visible.has(l.source)&&visible.has(l.target));
 if(state.selected&&!visible.has(state.selected))clearSelection();
 Graph.graphData({nodes:shownNodes,links:shownLinks.map(l=>({...l}))});
 $("empty").style.display=shownNodes.length?"none":"block";
 $("status").textContent=fmt(shownNodes.length)+" / "+fmt(nodes.length)+" узлов · "+fmt(shownLinks.length)+" связей"+(state.cycles?" · "+nCycles+" полных циклов":"");
 $("view-title").textContent=state.focus?"Фокус: выбранные узлы и окружение":state.cluster!=="all"?"Кластер "+state.cluster:state.threat?"Изоляция: ключевые роли":"Все наблюдаемые связи";
 const base=GRAPH.resilience[0];
 $("resilience").innerHTML='<div><b>'+simulation.components+'</b><small>компонент</small></div><div><b>'+simulation.largest_component+'</b><small>крупнейшая</small></div><div><b>'+simulation.isolated+'</b><small>одиночных узлов</small></div>';
 $("resilience-note").textContent="До удаления: "+base.components+" компонент, крупнейшая "+base.largest_component+". Осталось "+simulation.n_nodes+" узлов / "+simulation.n_edges+" связей.";
 if(recenter&&shownNodes.length){clearTimeout(apply.timer);apply.timer=setTimeout(()=>Graph.zoomToFit(400,65),250);}
}
function renderCard(n){
 const a=adjacency.get(n.id);
 const kv=(k,v)=>'<div class="kv"><span>'+esc(k)+'</span><span>'+esc(v)+'</span></div>';
 const neighbors=(arr,dir)=>arr.map(l=>{const id=dir==="in"?l.source:l.target;return '<button class="neighbor" data-neighbor="'+id+'"><span class="dot" style="background:'+COLORS[byId.get(id).role]+'"></span> '+id+'<small>'+fmt(l.sum_kzt)+' KZT · '+l.n_tx+' переводов</small></button>';}).join("")||'<p class="muted">Не наблюдаются</p>';
 $("detail-body").innerHTML='<div class="detail-id">GID '+n.id+'</div><h2 style="color:'+COLORS[n.role]+'">'+LABELS[n.role]+'</h2><p class="muted small">Гипотеза роли; не вывод о виновности.</p>'+
 (n.truncated?'<div class="warning">◌ Данные обрываются на 4-м колене. Необходим запрос на выгрузку 5-го колена. Статус терминала не подтверждён.</div>':"")+
 (n.is_seed?'<div class="warning">Seed: входящие извне выборки не видны. Приход неполон; pass_through не используется для роли.</div>':"")+
 kv("Приоритет",n.priority.toFixed(4))+kv("Поддержка правила",n.role_score.toFixed(3)+" · не вероятность")+
 kv("Кластер / глубина",n.cluster+" / "+n.depth)+kv("Наблюдаемый приход",fmt(n.in_kzt)+" KZT")+
 kv("Наблюдаемый уход",fmt(n.out_kzt)+" KZT")+kv("Контрагенты · вход / выход",n.in_deg+" / "+n.out_deg)+
 kv("Переводы · вход / выход",n.in_tx+" / "+n.out_tx)+kv("Прямые seed-плательщики",n.n_seed_in)+
 kv("Out / in",n.pass_through===null?"Не применяется":n.pass_through.toFixed(3))+
 kv("Медианный лаг",n.turnover_days===null?"Не наблюдается":n.turnover_days.toFixed(1)+" дн.")+
 '<div class="evidence"><h3>Обоснование</h3>'+esc(n.evidence)+'</div>'+
 '<details open><summary>От кого получает · '+a.in.length+'</summary>'+neighbors(a.in,"in")+'</details>'+
 '<details><summary>Кому переводит · '+a.out.length+'</summary>'+neighbors(a.out,"out")+'</details>';
 $("detail").hidden=false;
}
$("detail-body").addEventListener("click",e=>{const b=e.target.closest("[data-neighbor]");if(b)selectNode(b.dataset.neighbor,true);});
$("zoom-in").onclick=()=>Graph.zoom(Graph.zoom()*1.4,250);
$("zoom-out").onclick=()=>Graph.zoom(Graph.zoom()/1.4,250);
$("fit").onclick=()=>Graph.zoomToFit(400,70);
new ResizeObserver(()=>{Graph.width(pane.clientWidth).height(pane.clientHeight);}).observe(pane);
apply();setTimeout(()=>Graph.zoomToFit(600,75),1000);
const themeBtn=$("theme-btn");function themeLabel(){if(themeBtn)themeBtn.textContent=document.documentElement.dataset.theme==="light"?"☾ Тёмная":"☀ Светлая";}themeLabel();
if(themeBtn)themeBtn.onclick=()=>{const t=document.documentElement.dataset.theme==="light"?"dark":"light";document.documentElement.dataset.theme=t;try{localStorage.setItem("vertex_theme",t)}catch(e){}readGT();themeLabel();Graph.nodeColor(Graph.nodeColor()).linkColor(Graph.linkColor());};

// Offline queries are explicit deterministic filters; OpenAI interprets a query on the server.
function localQuery(question){
 const q=question.toLowerCase(),id=(question.match(/\d{12,}/)||[])[0];
 let result=id&&byId.has(id)?[byId.get(id)]:[...nodes],recognized=!!id;
 if(id&&!byId.has(id))return {answer:"Такого gid нет в выгрузке.",gids:[]};
 const clusterMatch=q.match(/кластер\s*(\d+)/);
 if(clusterMatch){result=result.filter(n=>n.cluster===Number(clusterMatch[1]));recognized=true;}
 const mapping=[["сбор","consolidator"],["консол","consolidator"],["транз","transit"],["координ","coordinator"],["распредел","distributor"],["термин","terminal"]];
 for(const [word,role] of mapping)if(q.includes(word)){result=result.filter(n=>n.role===role);recognized=true;break;}
 if(q.includes("seed")){result=result.filter(n=>n.n_seed_in>0);recognized=true;}
 if(q.includes("цикл")){result=result.filter(n=>n.in_cycle);recognized=true;}
 if(q.includes("слеп")||q.includes("обрез")){result=result.filter(n=>n.truncated);recognized=true;}
 if(q.includes("топ")||q.includes("приоритет"))recognized=true;
 if(!recognized)return {answer:"Локальный режим понимает gid, роли, seed, циклы и слепые зоны. Например: «Крупные транзиты» или «Сборщики от seed».",gids:[]};
 const metric=q.includes("seed")?"n_seed_in":q.includes("круп")?(q.includes("транз")?"out_kzt":"in_kzt"):"priority";
 result.sort((a,b)=>b[metric]-a[metric]||b.priority-a.priority||a.id.localeCompare(b.id));
 result=result.slice(0,5);
 return {answer:"Локальная выборка по "+metric+". Найдено для показа: "+result.length+". Роли — гипотезы, суммы — только внутри выгрузки.",gids:result.map(n=>n.id)};
}
function message(text,user=false,gids=[]){
 const box=document.createElement("div");box.className="chat-message"+(user?" user":"");box.textContent=text;
 for(const id of gids){if(!byId.has(id))continue;const b=document.createElement("button");b.className="chat-node";b.textContent=id;b.onclick=()=>selectNode(id,true);box.append(document.createElement("br"),b);}
 $("chatlog").append(box);$("chatlog").scrollTop=$("chatlog").scrollHeight;
}
function toggleChat(open){$("chat").hidden=!open;$("chat-toggle").setAttribute("aria-expanded",String(open));if(open)$("chat-question").focus();}
$("chat-toggle").onclick=()=>toggleChat($("chat").hidden);$("chat-close").onclick=()=>toggleChat(false);
$("chat-form").onsubmit=async e=>{
 e.preventDefault();const q=$("chat-question").value.trim();if(!q)return;
 $("chat-question").value="";message(q,true);$("chat-send").disabled=true;
 try{
  let result;
  if($("chat-mode").value==="openai"){
   const response=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q})});
   result=await response.json();if(!response.ok)throw new Error(result.error||"Ошибка API");
  } else result=localQuery(q);
  message(result.answer,false,result.gids);
 }catch(err){message("Запрос не выполнен: "+err.message+". Можно переключиться на локальный поиск.");}
 finally{$("chat-send").disabled=false;}
};
$("chat-mode").onchange=()=>{$("ai-status").textContent=$("chat-mode").value==="openai"?"Вопрос и ограниченные метаданные будут отправлены OpenAI. Ключ остаётся на сервере.":"Локальные фильтры, без внешних запросов.";};
$("cluster-ai").onclick=async()=>{
 const cluster=state.cluster;if(cluster==="all")return;
 $("cluster-ai").disabled=true;
 try{
  const response=await fetch("/api/hypothesis",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({cluster_id:Number(cluster)})});
  const result=await response.json();if(!response.ok)throw new Error(result.error);
  if(state.cluster===cluster)$("hypothesis").textContent=result.hypothesis;
 }catch(err){toast("OpenAI: "+err.message);}
 finally{updateAIButton();}
};
function updateAIButton(){$("cluster-ai").disabled=!aiAvailable||state.cluster==="all";}
if(location.protocol==="http:"||location.protocol==="https:"){
 fetch("/api/status").then(r=>r.ok?r.json():Promise.reject()).then(s=>{
  aiAvailable=!!s.available;const option=$("chat-mode").querySelector('[value="openai"]');option.disabled=!aiAvailable;
  option.textContent=aiAvailable?"OpenAI · сервер подключён":"OpenAI · задайте OPENAI_API_KEY и OPENAI_MODEL";
  if(aiAvailable)$("cluster-ai").title="Метаданные выбранного кластера будут отправлены OpenAI";
  updateAIButton();
 }).catch(()=>{});
}
