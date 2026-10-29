import test from 'node:test';
import assert from 'node:assert/strict';
import {registrationFrom,prepareReadTask,readImportFile,importBody} from '../src/custom-management.mjs';
import {taskBody} from '../src/tool-selection.mjs';
test('task preparation binds enabled revision and exact keys and clears send authority',()=>{
 const tool={name:'custom.stock',state:'ACTIVE',enabled:true,revision:'0x'+'12'.repeat(32),resources:['001','002']};
 const p=prepareReadTask(tool,['001']);
 assert.deepEqual(taskBody(p.text,p.tools,p.documents,p.mailboxes,p.recipients,p.custom).custom_tools,[{name:tool.name,revision:tool.revision,allowed_keys:['001']}]);
 assert.deepEqual(p.recipients,[]);assert.deepEqual(p.documents,[]);
 for(const [t,keys] of [[{...tool,enabled:false},['001']],[{...tool,state:'DRAFT'},['001']],[tool,[]],[tool,['003']],[tool,['001','001']]])assert.throws(()=>prepareReadTask(t,keys));
});
test('version form omits generated manifest metadata',()=>{
 const item={manifest:{name:'custom.stock',label:'stock',description:'query',adapter:'dataset.lookup',risk:0,key_field:'sku',output_fields:['sku'],version:2,revision:'old'},records:[{sku:'001'}]};
 assert.deepEqual(Object.keys(registrationFrom(item)).sort(),['name','label','description','adapter','risk','key_field','output_fields','records'].sort());
 assert.equal(registrationFrom(item).records[0].sku,'001');
});
test('file loader accepts bounded UTF-8 without evaluating contents',async()=>{
 assert.deepEqual(await readImportFile(new File(['sku,n\n001,2'],'stock.csv')),{format:'csv',content:'sku,n\n001,2'});
 for(const file of [new File(['x'],'a.exe'),new File(['a'.repeat(65537)],'a.csv'),new File([new Uint8Array([0xff])],'a.json')])await assert.rejects(()=>readImportFile(file));
 assert.deepEqual(importBody('csv','sku,n\n001,2','{"n":"integer"}').column_types,{n:'integer'});
 assert.deepEqual(importBody('json','[]','invalid').column_types,{});assert.throws(()=>importBody('csv','x','invalid'));
});
