export function httpRegistration({name,label,description,url,method,profile='default',query='{}',body='{}'}){
 const p=new URL(url);
 if(p.protocol!=='https:'||p.username||p.password||p.search||p.hash||p.port||/[\\%?#\s]/.test(url))throw Error('填写公开 HTTPS API 地址；URL 参数请放入参数 JSON，不填写密钥');
 if(!['GET','POST'].includes(method))throw Error('首版只支持 GET 查询和 POST 查询／识别');
 const q=JSON.parse(query),b=method==='POST'?JSON.parse(body):null;
 if(!q||Array.isArray(q)||typeof q!=='object'||Object.values(q).some(v=>!['string','number','boolean'].includes(typeof v)))throw Error('URL 参数必须是平铺 JSON 对象');
 if(method==='POST'&&(!b||Array.isArray(b)||typeof b!=='object'))throw Error('POST Body 必须是 JSON 对象');
 return {name,label,description,adapter:'http.request',risk:1,key_field:'profile',output_fields:['profile','response'],
  http:{url,method,purpose:'query_or_inference'},records:[{profile,query:q,body:b}]};
}
