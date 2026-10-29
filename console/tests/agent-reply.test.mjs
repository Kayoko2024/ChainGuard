import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AgentReply} from '../src/AgentReply.mjs';

const render=text=>renderToStaticMarkup(React.createElement(AgentReply,{text}));

test('model headings, emphasis and lists render as elements instead of literal markers',()=>{
 const html=render('# 处理结果\n\n这是**重点**和*补充*。\n\n## 下一步\n\n- 阅读\n- 总结\n\n1. 核验\n2. 下载');
 assert.match(html,/<h1>处理结果<\/h1>/);assert.match(html,/<h2>下一步<\/h2>/);
 assert.match(html,/<strong>重点<\/strong>/);assert.match(html,/<em>补充<\/em>/);
 assert.match(html,/<ul>/);assert.match(html,/<ol>/);assert.match(html,/<li>核验<\/li>/);
 assert.ok(!html.includes('**'));assert.ok(!html.includes('# 处理结果'));
});
test('GFM tables, quotes and ordinary paragraphs remain readable',()=>{
 const html=render('第一段。\n\n第二段。\n\n> 引用来源 page:1\n\n| 字段 | 值 |\n| --- | --- |\n| 状态 | 待核验 |');
 assert.match(html,/<p>第一段。<\/p>/);assert.match(html,/<p>第二段。<\/p>/);
 assert.match(html,/<blockquote>/);assert.match(html,/<th>字段<\/th>/);
 assert.match(html,/<td>待核验<\/td>/);assert.match(html,/class="reply-table-scroll"/);
});
test('code and literal hash/asterisk characters are preserved, never removed globally',()=>{
 const html=render('Issue #123，计算 2 * 3。\n\n`**原样**`\n\n```python\n# 保留代码注释\nvalue = "**内容**"\n```');
 assert.match(html,/Issue #123，计算 2 \* 3。/);
 assert.match(html,/<code>\*\*原样\*\*<\/code>/);
 assert.match(html,/<pre><code class="language-python"># 保留代码注释/);
 assert.ok(html.includes('**内容**'));
});
test('untrusted HTML, images and active embeds cannot become browser resources',()=>{
 const html=render('<script>alert(1)</script>\n\n<img src="https://attacker.invalid/pixel" onerror="alert(2)">\n\n![跟踪图片](https://attacker.invalid/pixel)\n\n<iframe src="https://attacker.invalid"></iframe>\n\n正文');
 for(const forbidden of ['<script','<img','<iframe','onerror=','attacker.invalid'])assert.ok(!html.includes(forbidden));
 assert.match(html,/<p>正文<\/p>/);
});
test('only explicit HTTP(S) links are clickable and open with an isolated referrer-free tab',()=>{
 const html=render('[来源](https://example.com/path) [脚本](javascript:alert%281%29) [接口](/ops/v1/tasks) [文件](file:///D:/CCF) [邮件](mailto:test@example.com) [凭据](https://user:secret@example.com) [相对](//example.com) [数据](data:text/html,evil)');
 assert.equal((html.match(/<a /g)||[]).length,1);
 assert.match(html,/href="https:\/\/example.com\/path" target="_blank" rel="noopener noreferrer nofollow"/);
 assert.match(html,/<span>脚本<\/span>/);assert.match(html,/<span>接口<\/span>/);
 assert.ok(!html.includes('user:secret'));assert.ok(!html.includes('javascript:'));
});
