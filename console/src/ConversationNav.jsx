import React from 'react';
import {Icon} from '../../shared/ui.jsx';

export function ConversationNav({session,roles,view,onNew,onLogout,historyOpen,onHistory,children,busy=false}){
 return <aside className={'sidebar conversation-sidebar '+(historyOpen?'history-open':'')}>
  <a className="brand" href="#tasks" aria-label="ChainGuard 首页"><span className="brand-mark"><Icon name="file"/></span><div>Chain<span className="brand-accent">Guard</span><small>你的安全工作空间</small></div></a>
  {session&&<>{session.role==='requester'&&<button className="new-conversation" aria-label="新建会话" onClick={onNew}><Icon name="plus"/>新建会话<span aria-hidden="true">＋</span></button>}
   <nav aria-label="工作空间导航"><a className={'side-link '+(view==='chat'?'active':'')} aria-current={view==='chat'?'page':undefined} href="#tasks"><Icon name="activity"/>Agent 对话</a><a className={'side-link '+(view==='tools'?'active':'')} aria-current={view==='tools'?'page':undefined} href="#tools"><Icon name="grid"/>工具与设置</a><a className="side-link" href={session.audit_url||'http://127.0.0.1:8091/'} target="_blank" rel="noreferrer"><Icon name="layers"/>只读审计<Icon name="external"/></a></nav>
   <button className="mobile-history" aria-expanded={historyOpen} onClick={onHistory}><Icon name="clock"/>历史任务</button>
   {children}
   <div className="identity"><div><span className="avatar"><Icon name="user"/></span><div><strong>{roles[session.role]}</strong><small>{session.organization}</small></div></div><button className="logout icon-button" aria-label="退出" title="退出身份" disabled={busy} onClick={onLogout}><Icon name="logout"/></button></div>
  </>}
  {!session&&<div className="sidebar-bottom"><Icon name="lock"/>本地安全工作空间<p>真实模型 · 受控工具<br/>跨组织审批 · 可验证审计</p></div>}
 </aside>;
}
