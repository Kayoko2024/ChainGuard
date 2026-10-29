import React,{useState} from 'react';
import {importBody,readImportFile} from './custom-management.mjs';

export function ImportData({api,action,onUse}){
 const [format,S]=useState('csv'),[content,C]=useState(''),[types,T]=useState('{}'),[preview,P]=useState(null);
 return <div className="custom-import wide" aria-label="资料导入"><h3>导入 CSV / JSON</h3>
 <label>选择本地 UTF-8 文件<input type="file" accept=".csv,.json" aria-label="导入资料文件" onChange={e=>{const file=e.target.files[0];P(null);action(async()=>{const v=await readImportFile(file);S(v.format);C(v.content);T('{}');});e.target.value='';}}/></label>
 <label>资料格式<select aria-label="导入格式" value={format} onChange={e=>{S(e.target.value);P(null);}}><option value="csv">CSV</option><option value="json">JSON 数组</option></select></label>
 <label>文件内容（仅预览，不注册）<textarea aria-label="导入原文" rows={4} value={content} onChange={e=>{C(e.target.value);P(null);}}/></label>
 {format==='csv'&&<label>CSV 列类型 JSON<textarea aria-label="CSV 列类型" rows={2} value={types} onChange={e=>{T(e.target.value);P(null);}} placeholder='{"quantity":"integer","enabled":"boolean"}'/><small>默认全部按字符串读取，保留 001 等编号。整数/布尔须显式指定。</small></label>}
 <button type="button" disabled={!content} onClick={()=>action(async()=>P(await api('/ops/v1/custom-tools/import-preview','POST',importBody(format,content,types))))}>校验并预览导入</button>
 {preview&&<div aria-label="导入预览"><p>{preview.row_count} 条 · {preview.columns.length} 列 · 尚未持久化</p><div className="import-table"><table><thead><tr>{preview.columns.map(c=><th key={c}>{c}<small>{preview.column_types[c]}</small></th>)}</tr></thead><tbody>{preview.records.slice(0,10).map((r,i)=><tr key={i}>{preview.columns.map(c=><td key={c}>{String(r[c])}</td>)}</tr>)}</tbody></table></div><small>最多展示前 10 行；提交包含全部已校验数据。</small><button type="button" onClick={()=>onUse(preview)}>将预览数据填入待审版本</button></div>}
 </div>;
}
