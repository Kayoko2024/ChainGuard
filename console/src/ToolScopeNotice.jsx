import React from 'react';
import {Icon} from '../../shared/ui.jsx';

export function ToolScopeNotice({issues,compact=false,onReview}){
 if(!issues.length)return null;
 return <div id={compact?'composer-scope-issues':'settings-scope-issues'} className={'tool-scope-notice '+(compact?'composer-scope-notice':'settings-scope-notice')} role="status">
  <Icon name="info"/><div><strong>还需补全工具授权</strong>{(compact?issues.slice(0,1):issues).map(issue=><p key={issue.code+(issue.tool||'')}>{issue.message}</p>)}{compact&&issues.length>1&&<small>另有 {issues.length-1} 项待补全</small>}</div>
  {onReview&&<button type="button" onClick={onReview}>补全授权</button>}
 </div>;
}
