/* Portable validation for local case notes; shared by browser and Node tests. */
const VertexCaseState = (() => {
 const statuses=new Set(["new","review","closed"]);
 const resolutions=new Set(["escalate","false_positive","monitor"]);
 function validate(bundle,analysisId,caseIds){
  if(!bundle||bundle.version!==1||bundle.analysis_id!==analysisId)
   throw new Error("Файл относится к другой версии анализа. Автоматическое сопоставление запрещено.");
  if(!bundle.states||typeof bundle.states!=="object"||Array.isArray(bundle.states))
   throw new Error("Некорректный формат заметок.");
  const allowed=new Set(caseIds),clean={};
  for(const [id,s] of Object.entries(bundle.states)){
   if(!allowed.has(id))throw new Error("Неизвестный кейс: "+id);
   if(!s||!statuses.has(s.status)||typeof s.note!=="string"||s.note.length>5000)
    throw new Error("Некорректный статус или заметка.");
   if((s.status==="closed"&&!resolutions.has(s.resolution)) ||
      (s.status!=="closed"&&s.resolution!==null))throw new Error("Некорректный результат разбора.");
   if(typeof s.updated_at!=="string"||!Number.isFinite(Date.parse(s.updated_at)))
    throw new Error("Некорректное время изменения.");
   clean[id]={status:s.status,note:s.note,resolution:s.resolution,updated_at:s.updated_at};
  }
  return clean;
 }
 function merge(local,incoming,replace=false){
  const result={...local};let added=0,conflicts=0,replaced=0;
  for(const [id,s] of Object.entries(incoming)){
   if(!result[id]){result[id]=s;added++;}
   else if(JSON.stringify(result[id])!==JSON.stringify(s)){conflicts++;if(replace){result[id]=s;replaced++;}}
  }
  return {states:result,added,conflicts,replaced};
 }
 return {validate,merge};
})();
if(typeof module!=="undefined"&&module.exports)module.exports=VertexCaseState;
