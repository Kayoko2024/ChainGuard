import test from 'node:test';
import assert from 'node:assert/strict';
import {toolCategory,groupToolVersions,matchesTool,matchesState} from '../src/tool-catalog.mjs';

test('catalog filtering classifies data and API adapters without changing selected scopes',()=>{
 const tools=[{name:'doc.read',label:'读取文档'},{name:'custom.contacts',label:'联系人',custom:true,adapter:'dataset.lookup'},{name:'custom.weather',label:'天气查询',custom:true,adapter:'http.request'}];
 const saved=JSON.stringify(tools),selection=['doc.read','custom.contacts'];
 assert.deepEqual(tools.map(toolCategory),['default','data','api']);
 assert.deepEqual(tools.filter(t=>matchesTool(t,'WEATHER','api')).map(t=>t.name),['custom.weather']);
 assert.equal(matchesTool(tools[1],'联系人','api'),false);
 assert.deepEqual(selection,['doc.read','custom.contacts']);assert.equal(JSON.stringify(tools),saved);
});

test('tool list groups immutable revisions and preserves active older versions for review',()=>{
 const items=[{name:'custom.stock',version:1,state:'ACTIVE',revision:'first',adapter:'dataset.lookup'},{name:'custom.stock',version:3,state:'DRAFT',revision:'third',adapter:'dataset.lookup'},{name:'custom.stock',version:2,state:'DISABLED',revision:'second',adapter:'dataset.lookup'},{name:'custom.repo',version:1,state:'ACTIVE',revision:'repo',adapter:'github.read'}];
 const saved=JSON.stringify(items),groups=groupToolVersions(items);
 assert.equal(groups.length,2);assert.equal(groups[0].revision,'third');assert.equal(groups[0].active.revision,'first');
 assert.deepEqual(groups[0].versions.map(v=>v.revision),['third','second','first']);
 assert.equal(matchesState(groups[0],'ACTIVE'),true);assert.equal(matchesState(groups[0],'DISABLED'),true);assert.equal(matchesState(groups[0],'pending'),true);
 assert.equal(matchesState(groups[1],'pending'),false);assert.equal(toolCategory(groups[0]),'data');assert.equal(JSON.stringify(items),saved);
});

test('empty or unmatched catalogs remain empty without fabricating tools',()=>{
 assert.deepEqual(groupToolVersions([]),[]);
 assert.equal(matchesTool({name:'mail.send',label:'发送邮件'},'不存在'),false);
 assert.equal(matchesState({state:'DISABLED'},'ACTIVE'),false);
});
