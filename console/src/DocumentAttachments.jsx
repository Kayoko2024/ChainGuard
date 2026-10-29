import React from 'react';
import {Icon} from '../../shared/ui.jsx';

export function DocumentAttachments({files,setFiles,allowCreate,setAllowCreate,busy,locked=false,upload}){
 return <div className="document-composer">
  <div className="document-controls"><label className={'attach-file '+(busy||locked?'disabled':'')}><Icon name="file"/><span>{locked?`会话附件 ${files.length}`:busy?'处理中…':'添加文件'}</span><input type="file" aria-label="添加文档附件" accept=".doc,.docx,.pdf,.txt,.md" multiple disabled={busy||locked||files.length>=4} onChange={async e=>{const chosen=Array.from(e.target.files||[]);e.target.value='';await upload(chosen);}}/></label>
   <label className="document-permission"><input type="checkbox" aria-label="允许生成 / 修改 Word、PDF 副本" disabled={locked||busy} checked={allowCreate} onChange={e=>setAllowCreate(e.target.checked)}/><span>生成 Word / PDF</span></label>
   <details className="document-info"><summary>文件说明</summary><p className="document-help">最多 4 个，每个 5 MB；支持 DOC/DOCX、文字型 PDF、TXT/MD。授权文本会交给当前 DeepSeek 模型。原件保留；修改时只生成新副本，PDF 为重排文字版，扫描件暂不支持。{locked&&'附件及文档权限已随会话固定，修改范围请新建会话。'}</p></details>
  </div>
  {files.length>0&&<ul className="attachment-chips" aria-label="本次任务附件">{files.map(file=><li key={file.id}><Icon name="file"/><span title={file.name}>{file.name}<small>{(file.size/1024).toFixed(1)} KB</small></span>{!locked&&<button type="button" aria-label={`移除附件 ${file.name}`} disabled={busy} onClick={()=>setFiles(files.filter(f=>f.id!==file.id))}>×</button>}</li>)}</ul>}
 </div>;
}

export function DocumentFiles({job}){
 const attachments=job?.documents?.attachments||[],artifacts=job?.documents?.artifacts||[];
 if(!attachments.length&&!artifacts.length)return null;
 return <section className="document-files" aria-label="任务文档与下载">
  {[['原始附件',attachments],['生成的文件',artifacts]].map(([title,files])=>files.length>0&&<div key={title}><h3>{title}</h3>{files.map(file=><div className="document-file" key={file.id}><Icon name="file"/><div><a href={`/ops/v1/tasks/${job.id}/documents/${file.id}`} download>{file.name}</a><small>{(file.size/1024).toFixed(1)} KB · SHA-256 {file.sha256}</small>{file.note&&<small>{file.note.startsWith('REFLOWED')?'重排文字版：未保留原图、版式、表单或数字签名；原件未修改。':'修改副本：未改段落保留；改动段落采用纯文字格式，原件未修改。'}</small>}<code>{file.id}</code></div></div>)}</div>)}
  <p className="document-help">本地文档结果有文件摘要与持久执行记录；不代表 R2 链上预约或邮件已发送。</p>
 </section>;
}
