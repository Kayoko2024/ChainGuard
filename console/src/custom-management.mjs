// Form preparation only; registration, admission and execution remain explicit.
export function registrationFrom(item){
 const {name,label,description,adapter,risk,key_field,output_fields}=item.manifest;
 return {name,label,description,adapter,risk,key_field,output_fields,records:item.records,...(item.manifest.http?{http:item.manifest.http}:{})};
}
export function prepareReadTask(tool,keys){
 if(!tool.enabled||tool.state!=='ACTIVE'||!keys.length||new Set(keys).size!==keys.length||keys.some(k=>!tool.resources.includes(k)))throw Error('请选择已启用版本中的记录键');
 const githubKey=keys.includes('microsoft/vscode#1')?'microsoft/vscode#1':keys.find(k=>k.includes('#'))||keys[0];
 return {tools:[tool.name],documents:[],mailboxes:[],recipients:[],custom:[{name:tool.name,revision:tool.revision,allowed_keys:[...keys]}],
  text:tool.adapter==='http.request'?`请实际调用 ${tool.name}，query 为 ${keys[0]}，使用已审核的 API 请求配置，依据真实返回回答并列出来源和 HTTP 状态。不要改变请求地址或参数，不发送邮件。`:tool.adapter==='github.read'?`请实际调用 ${tool.name}，query 精确为 ${githubKey}，总结实际返回的标题、状态与内容，列出来源。只查询这一条，不发送邮件。`:`请调用 ${tool.name} 查询 ${keys.join('、')}，依据实际返回资料回答。只查询授权记录，不发送邮件。`};
}
export function importBody(format,content,types){return {format,content,column_types:format==='csv'?JSON.parse(types||'{}'):{}};}
export async function readImportFile(file){
 if(!file||file.size>65536)throw Error('请选择不超过 64 KiB 的 UTF-8 CSV/JSON 文件');
 const extension=file.name.split('.').at(-1).toLowerCase();
 if(!['csv','json'].includes(extension))throw Error('仅支持 CSV 或 JSON 文件');
 return {format:extension,content:new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer())};
}
