import React from 'react';
import {icons,stateLabel,stateTone,executionStages} from './presentation.mjs';
export function Icon({name,className=''}){return <svg className={'icon '+className} viewBox="0 0 24 24" aria-hidden="true"><path d={icons[name]||icons.shield}/></svg>;}
export function PaperLayers(){return <><div className="paper-layer paper-layer-back" aria-hidden="true"/><div className="paper-layer paper-layer-front" aria-hidden="true"/></>;}
export function PaperEmblem(){return <div className="paper-emblem paper-stack" aria-hidden="true"><PaperLayers/><span className="paper-emblem-face"><Icon name="shield"/></span></div>;}
// Original CSS/SVG illustration. Decorative workflow labels never represent live evidence.
export function CraftIllustration(){return <div className="craft-collage" aria-hidden="true">
 <span className="craft-scrap scrap-yellow"/><span className="craft-scrap scrap-teal"/><span className="craft-scrap scrap-pink"/>
 <svg className="craft-orbit" viewBox="0 0 340 290"><path d="M24 215C-10 145 84 112 129 155S266 234 299 137"/><path d="m286 143 15-10 3 18"/></svg>
 <div className="craft-sheet sheet-blue"/><div className="craft-sheet sheet-yellow"/>
 <div className="craft-sheet sheet-white"><span className="craft-tape"/><div className="craft-sheet-heading"><Icon name="file"/><span>从一个想法开始</span><i>01</i></div><span className="craft-rule rule-long"/><span className="craft-rule"/><span className="craft-rule rule-short"/><div className="craft-sheet-footer"><span>你的 Agent 工作空间</span><Icon name="arrow"/></div></div>
 <div className="craft-seal"><Icon name="shield"/><span>执行有边界</span></div>
 <div className="craft-note"><Icon name="layers"/><span>每一步<br/><b>都有依据</b></span></div>
 <svg className="craft-spark" viewBox="0 0 36 36"><path d="M18 2v10m0 12v10M2 18h10m12 0h10M7 7l6 6m10 10 6 6M7 29l6-6m10-10 6-6"/></svg>
 </div>;}
export function StateBadge({value}){return <span className={'badge '+stateTone(value)} title={value}>{stateLabel(value)}</span>;}
export function Sidebar({active,auditUrl='http://127.0.0.1:8091/',children}){
 return <aside className="sidebar"><a className="brand" href="/" aria-label="ChainGuard 首页"><span className="brand-mark"><Icon name="file"/></span><div>Chain<span className="brand-accent">Guard</span><small>每个动作，都有依据</small></div></a><div className="workspace-label"><span className="workspace-symbol">CG</span><div>本地演示空间<small>四节点 · 本地沙箱</small></div><Icon name="chevron"/></div><div className="nav-label">工作空间</div><nav aria-label="工作空间导航"><a className={'side-link '+(active==='operations'?'active':'')} aria-current={active==='operations'?'page':undefined} href={active==='operations'?'#tasks':'http://127.0.0.1:8090/'}><Icon name="grid"/>业务操作台{active==='operations'&&<span className="nav-tag">R2</span>}</a><a className={'side-link '+(active==='audit'?'active':'')} aria-current={active==='audit'?'page':undefined} href={active==='audit'?'#actions':auditUrl}><Icon name="layers"/>动作审计{active==='audit'&&<span className="nav-tag">只读</span>}</a></nav><div className="sidebar-bottom">{children||<><Icon name="lock"/> 本地隔离环境<p>仅本地测试邮件<br/>四节点同机 · QBFT</p></>}</div></aside>;
}
export function Stages({record}){return <div className="protocol-strip" aria-label="执行证据进度">{executionStages(record).map((s,i)=><div key={s.label} className={'protocol-stage '+(s.done?'done':'')}><span className="stage-mark">{s.done?<Icon name="check"/>:i+1}</span><span>{s.label}</span></div>)}</div>;}
