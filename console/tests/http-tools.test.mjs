import test from 'node:test';
import assert from 'node:assert/strict';
import {httpRegistration} from '../src/http-tools.mjs';
import {registrationFrom,prepareReadTask} from '../src/custom-management.mjs';
const form={name:'custom.vision_api',label:'Vision',description:'Image inference',url:'https://vision.example.com/v1/query',method:'POST',profile:'photo',query:'{"lang":"zh"}',body:'{"image_url":"https://images.example.com/test.png"}'};
test('generic API form binds endpoint, method, query and nested JSON body to R1',()=>{
 const v=httpRegistration(form);assert.equal(v.risk,1);assert.equal(v.adapter,'http.request');
 assert.equal(v.http.method,'POST');assert.equal(v.records[0].body.image_url,'https://images.example.com/test.png');
 assert.deepEqual(httpRegistration({...form,method:'GET'}).records[0].body,null);
 assert.deepEqual(registrationFrom({manifest:v,records:v.records}),v);
});
test('malformed methods, URLs and parameters cannot submit a valid API manifest',()=>{
 for(const change of [{method:'DELETE'},{url:'http://example.com'},{url:'https://a:b@example.com'},{url:'https://example.com/?key=secret'},{query:'[]'},{query:'{"x":{}}'},{body:'null'},{body:'bad'}])assert.throws(()=>httpRegistration({...form,...change}));
});
test('task preparation uses exact reviewed request profile without mail permissions',()=>{
 const task=prepareReadTask({name:form.name,adapter:'http.request',enabled:true,state:'ACTIVE',revision:'0xabc',resources:['photo']},['photo']);
 assert.match(task.text,/query 为 photo/);assert.deepEqual(task.recipients,[]);assert.deepEqual(task.custom[0].allowed_keys,['photo']);
});
