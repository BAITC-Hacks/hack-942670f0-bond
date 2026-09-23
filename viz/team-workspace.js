"use strict";
const caseItems=GRAPH.cases||[], caseIds=caseItems.map(c=>c.id);
const analysisId=GRAPH.analysis_id, storageKey="vertex-cases-v3:"+analysisId;
let caseStates={},caseFilter="all",storageAvailable=true;
const stateNames={new:"Новый",review:"В работе",closed:"Закрыт"};
const resolutionNames={escalate:"Эскалация ответственному",false_positive:"Ложное срабатывание",monitor:"Мониторинг"};
const baseState=()=>({status:"new",note:"",resolution:null,updated_at:new Date().toISOString()});
function caseBundle(){return {version:1,analysis_id:analysisId,states:caseStates};}
function caseStateFor(id){return caseStates[id]||baseState();}
function storageMessage(text){$("case-storage").textContent=text;}
try{
 const saved=localStorage.getItem(storageKey);
 if(saved)caseStates=VertexCaseState.validate(JSON.parse(saved),analysisId,caseIds);
 if(localStorage.getItem("vertex_cases_v2"))
  storageMessage("Найдены заметки старой версии. Они сохранены отдельно и не привязаны автоматически к новым кейсам.");
}catch(error){storageAvailable=false;storageMessage("Хранилище недоступно или повреждено. Изменения останутся в памяти; используйте экспорт. "+error.message);}
function saveCases(){
 try{localStorage.setItem(storageKey,JSON.stringify(caseBundle()));storageAvailable=true;storageMessage("Сохранено в этом браузере. Для напарника экспортируйте JSON; Git не переносит localStorage.");}
 catch(error){storageAvailable=false;storageMessage("Не удалось сохранить в браузере. Экспортируйте заметки, прежде чем закрывать страницу.");}
}
function updateCase(id,patch,render=true){
 caseStates[id]={...caseStateFor(id),...patch,updated_at:new Date().toISOString()};
 saveCases();if(render)renderCases();
}
function showWorkspace(name){
 for(const n of ["graph","cases","resilience","assistant"])$("view-"+n).hidden=n!==name;
 document.querySelectorAll("#workspace-tabs [data-view]").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
 const chat=$("chat");
 if(name==="assistant"){$("assistant-dock").append(chat);chat.hidden=false;}
 else{if(chat.parentElement.id==="assistant-dock")$("canvas-pane").append(chat);chat.hidden=true;}
 if(name==="graph"){Graph.width(pane.clientWidth).height(pane.clientHeight);}
}
document.querySelectorAll("#workspace-tabs [data-view]").forEach(b=>b.onclick=()=>showWorkspace(b.dataset.view));
$("analysis-id").textContent="Анализ "+analysisId.slice(0,10);
function renderCases(){
 const counts={new:0,review:0,closed:0};
 caseItems.forEach(c=>counts[caseStateFor(c.id).status]++);
 $("case-count").textContent=caseItems.length;
 $("case-status").textContent="Новые: "+counts.new+" · В работе: "+counts.review+" · Закрытые: "+counts.closed+". Приоритет кейса — гипотеза, не установленное нарушение.";
 const visible=caseItems.filter(c=>caseFilter==="all"||caseStateFor(c.id).status===caseFilter);
 $("case-board").innerHTML=visible.map(c=>{
  const s=caseStateFor(c.id);
  const actions=s.status==="closed"?'<button data-action="reopen">Переоткрыть</button>':
   (s.status==="new"?'<button data-action="review" class="primary">Взять в работу</button>':"")+
   Object.entries(resolutionNames).map(([r,label])=>'<button data-action="'+r+'">'+label+'</button>').join("");
  return '<article class="case-card" data-case="'+c.id+'"><div class="case-title"><h2>'+esc(c.title)+'</h2><span class="badge">'+stateNames[s.status]+'</span></div>'+
   '<p class="muted">'+esc(c.id)+' · приоритет '+c.priority.toFixed(4)+' · '+c.n_nodes+' узлов · '+fmt(c.turnover_kzt)+' KZT</p>'+
   '<p class="muted">'+esc(c.hypothesis)+'</p><p class="muted">'+esc(c.recommended_action)+'</p>'+
   '<div class="case-keys">'+c.key_nodes.map(n=>'<button data-gid="'+n.gid+'">'+n.gid+'</button>').join("")+'</div>'+
   '<details><summary>Наблюдаемые переводы: '+c.logs.length+' из '+c.log_total+'</summary>'+
   c.logs.map(r=>'<div class="case-log">'+esc(r.tx_id)+' · '+esc(r.date.slice(0,10))+'<br>'+r.src+' → '+r.dst+' · '+fmt(r.sum_kzt)+' KZT</div>').join("")+'</details>'+
   '<label class="muted">Заметка аналитика<textarea maxlength="5000" aria-label="Заметка '+c.id+'">'+esc(s.note)+'</textarea></label>'+
   (s.resolution?'<p class="muted">Результат: '+resolutionNames[s.resolution]+'</p>':"")+
   '<div class="case-actions">'+actions+'</div></article>';
 }).join("")||'<p class="muted">Нет кейсов с выбранным статусом.</p>';
}
$("case-filter").onchange=e=>{caseFilter=e.target.value;renderCases();};
$("case-board").addEventListener("input",e=>{
 if(e.target.tagName==="TEXTAREA"){const id=e.target.closest("[data-case]").dataset.case;updateCase(id,{note:e.target.value},false);}
});
$("case-board").addEventListener("click",e=>{
 const b=e.target.closest("button");if(!b)return;
 if(b.dataset.gid){selectNode(b.dataset.gid,true);return;}
 const id=b.closest("[data-case]").dataset.case,action=b.dataset.action;
 if(action==="review")updateCase(id,{status:"review",resolution:null});
 else if(action==="reopen")updateCase(id,{status:"new",resolution:null});
 else if(resolutionNames[action])updateCase(id,{status:"closed",resolution:action});
});
$("case-export").onclick=()=>{
 const blob=new Blob([JSON.stringify(caseBundle(),null,2)],{type:"application/json"});
 const url=URL.createObjectURL(blob),a=document.createElement("a");
 a.href=url;a.download="case-notes-"+analysisId+".json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 storageMessage("Экспортированы заметки текущей версии анализа. Передайте JSON напарнику вне репозитория.");
};
$("case-import").onchange=async e=>{
 const file=e.target.files[0];if(!file)return;
 try{
  if(file.size>2*1024*1024)throw new Error("Размер файла превышает 2 МБ.");
  const incoming=VertexCaseState.validate(JSON.parse(await file.text()),analysisId,caseIds);
  const result=VertexCaseState.merge(caseStates,incoming,$("case-replace").checked);
  caseStates=result.states;saveCases();renderCases();
  storageMessage("Импорт: новых "+result.added+", конфликтов "+result.conflicts+", заменено "+result.replaced+
   (storageAvailable?". Сохранено в браузере.":". В памяти: экспортируйте результат."));
 }catch(error){storageMessage("Импорт отклонён: "+error.message);}
 e.target.value="";
};
const scenarios=GRAPH.resilience,baseline=scenarios[0];
$("resilience-chart").innerHTML=scenarios.filter(r=>[0,5,10,20,30].includes(r.n_removed)).map(r=>
 '<div class="res-bar"><b>'+r.largest_component+'</b><div style="height:'+Math.max(1,Math.round(r.largest_component/Math.max(1,baseline.largest_component)*165))+'px"></div>топ-'+r.n_removed+'</div>').join("");
$("resilience-rows").innerHTML=scenarios.map(r=>'<tr><td>'+r.n_removed+'</td><td>'+r.n_nodes+'</td><td>'+r.n_edges+'</td><td>'+r.components+'</td><td>'+r.largest_component+'</td><td>'+r.isolated+'</td><td><button data-remove="'+r.n_removed+'">Показать на графе</button></td></tr>').join("");
$("resilience-rows").addEventListener("click",e=>{
 const b=e.target.closest("[data-remove]");if(!b)return;
 showWorkspace("graph");resetFilters(true);clearSelection();
 state.blocked=+b.dataset.remove;$("blocking").value=state.blocked;$("blocking-value").textContent=state.blocked;apply(true);
});
renderCases();
