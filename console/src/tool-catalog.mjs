// Presentation only: filtering never changes the task's explicit selection.
export const toolCategories=[
 {id:'all',label:'全部工具'}, {id:'default',label:'默认工具'},
 {id:'data',label:'个人数据'}, {id:'api',label:'外部 API'},
];
export function toolCategory(tool){
 if(tool.adapter==='dataset.lookup')return 'data';
 return tool.custom||tool.adapter==='http.request'||tool.adapter==='github.read'?'api':'default';
}
export function toolIcon(tool){
 if(toolCategory(tool)==='data')return 'grid';
 if(toolCategory(tool)==='api')return 'external';
 return tool.name.startsWith('mail.')?'mail':'file';
}
export function matchesTool(tool,query,category='all'){
 return(category==='all'||toolCategory(tool)===category)&&
  [tool.name,tool.label,tool.description,tool.adapter].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
}
export function groupToolVersions(items){
 const groups=new Map();
 for(const item of items){if(!groups.has(item.name))groups.set(item.name,[]);groups.get(item.name).push(item);}
 return [...groups.values()].map(versions=>{
  versions=[...versions].sort((a,b)=>b.version-a.version);
  return {...versions[0],custom:true,versions,active:versions.find(v=>v.state==='ACTIVE')};
 });
}
export const catalogState={ACTIVE:'已启用',DRAFT:'待审核',ENABLING:'启用中',DISABLING:'停用中',DISABLED:'已停用'};
export function matchesState(tool,state){
 if(state==='all')return true;
 const versions=tool.versions||[tool];
 return versions.some(v=>state==='pending'?['DRAFT','ENABLING','DISABLING'].includes(v.state):v.state===state);
}
