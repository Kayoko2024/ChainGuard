import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Model text is untrusted. Render Markdown without executable HTML, embedded
// resources or links into local application endpoints.
const allowedElements = [
 'p','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em','del',
 'blockquote','pre','code','a','table','thead','tbody','tr','th','td','hr','br',
];
function ReplyLink({href,children}){
 let url;
 try { url=new URL(href); } catch { /* Relative/internal links remain text. */ }
 if(!url||!['http:','https:'].includes(url.protocol)||url.username||url.password){
  return React.createElement('span',null,children);
 }
 return React.createElement('a',{
  href:url.href,target:'_blank',rel:'noopener noreferrer nofollow',
 },children);
}
function ReplyTable({children}){
 return React.createElement('div',{
  className:'reply-table-scroll',role:'region','aria-label':'回复表格',tabIndex:0,
 },React.createElement('table',null,children));
}
const components={a:ReplyLink,table:ReplyTable};
const plugins=[remarkGfm];

export function AgentReply({text}){
 return React.createElement('div',{className:'agent-reply'},
  React.createElement(ReactMarkdown,{
   remarkPlugins:plugins,allowedElements,skipHtml:true,components,
  },text),
 );
}
