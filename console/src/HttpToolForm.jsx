import React,{useEffect,useState} from 'react';
import {httpRegistration} from './http-tools.mjs';
const newKey=()=> '0x'+Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
const initial={name:'custom.image_recognize',label:'图片识别',description:'调用已授权的图片识别 API，依据实际返回的 JSON 回答。',url:'',method:'POST',profile:'default',query:'{}',body:'{}'};
const nameHint='请使用 custom.weather_check 这样的名称：以 custom. 开头，后接 3–32 位小写字母、数字或下划线，并以字母开头。';

export function HttpToolForm({api,action,onRegistered,source,onCancel}){
 const [form,F]=useState(initial),[open,O]=useState(false),[key,K]=useState(newKey);
 useEffect(()=>{if(source){const m=source.manifest,r=source.records[0];F({name:m.name,label:m.label,description:m.description,url:m.http.url,method:m.http.method,profile:r.profile,query:JSON.stringify(r.query,null,2),body:JSON.stringify(r.body||{},null,2)});O(true);K(newKey());}},[source]);
 const input=(field,value)=>{F({...form,[field]:value});K(newKey());};
 async function submit(){
  const value=httpRegistration(form);
  const result=await api(source?`/ops/v1/custom-tools/${source.manifest.revision}/versions`:'/ops/v1/custom-tools','POST',value,{'Idempotency-Key':key});
  await onRegistered(result);O(false);K(newKey());onCancel();
 }
 return <details className="http-registration" open={open} onToggle={e=>O(e.currentTarget.open)}><summary>接入通用 API 工具</summary>
 <form className="custom-form" aria-label="通用 API 工具接入" onSubmit={e=>{e.preventDefault();action(submit);}}>
 <p className="wide">填写自己的查询或识别 API。服务端实际发起请求，浏览器和 Agent 不持有服务凭据。提交后须 OrgB 审核，再选本请求配置创建任务。</p>
 {source&&<p className="wide">正在创建 v{source.manifest.version+1}：修改地址、Method 或参数都须重新审核，原任务不变。{source.records.length>1&&'本表单只保留所显示的一份请求配置，请核对差异。'}</p>}
 <label>工具名称<input aria-label="API 工具名称" aria-describedby="http-tool-name-help" title={nameHint} placeholder="custom.weather_check" value={form.name} readOnly={!!source} onInvalid={e=>e.currentTarget.setCustomValidity(nameHint)} onChange={e=>{e.currentTarget.setCustomValidity('');input('name',e.target.value);}} required pattern="custom\.[a-z][a-z0-9_]{2,31}"/><small id="http-tool-name-help">例如 <code>custom.weather_check</code>。必须保留 <code>custom.</code> 前缀，其后为 3–32 位小写字母、数字或下划线，以字母开头。</small></label>
 <label>显示名称<input aria-label="API 工具显示名称" value={form.label} onChange={e=>input('label',e.target.value)} required maxLength={60}/></label>
 <label className="wide">用途描述<textarea aria-label="API 工具描述" value={form.description} onChange={e=>input('description',e.target.value)} required maxLength={500}/></label>
 <label>API 地址<input type="url" aria-label="API 地址" value={form.url} onChange={e=>input('url',e.target.value)} placeholder="https://vision.example.com/v1/recognize" required/></label>
 <label>Method<select aria-label="API Method" value={form.method} onChange={e=>input('method',e.target.value)}><option>GET</option><option>POST</option></select></label>
 <label>请求配置名<input aria-label="API 请求配置名" value={form.profile} onChange={e=>input('profile',e.target.value)} pattern="[a-zA-Z0-9_-]{1,64}" required/></label>
 <label className="wide">URL 参数 JSON<textarea aria-label="API URL 参数" rows={3} value={form.query} onChange={e=>input('query',e.target.value)} required spellCheck={false}/></label>
 {form.method==='POST'&&<label className="wide">请求 Body JSON<textarea aria-label="API 请求 Body" rows={5} value={form.body} onChange={e=>input('body',e.target.value)} placeholder='{"image_url":"https://公开测试图片地址"}' required spellCheck={false}/></label>}
 <div className="settings-note wide"><span>R1 外部查询／推理：只调用审核时绑定的地址和参数，Agent 不能临时换地址或扩参。POST 的用途须由安全身份核实，不允许发送邮件、删除、付款等敏感写操作。不填写 API Key；首版支持无需凭据的 JSON API，不支持文件二进制上传。</span></div>
 <div className="buttons wide"><button type="button" onClick={()=>{F({...initial,name:'custom.http_echo',label:'HTTP 连通性回显',description:'调用授权的 HTTP 回显 API，报告真实请求参数和 JSON 返回；这是连通性测试，不是图片识别。',url:'https://httpbin.org/anything',body:'{"message":"ChainGuard connectivity test"}'});K(newKey());}}>填入 HTTP 回显示例</button><button className="primary" type="submit">{source?'提交 API 新版本':'提交 API 工具待审版本'}</button>{source&&<button type="button" onClick={()=>{onCancel();F(initial);}}>取消版本修改</button>}</div>
 </form></details>;
}
