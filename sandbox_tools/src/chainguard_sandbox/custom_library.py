"""Immutable, admitted dataset lookup. No path, URL, executable, or external credential."""
import hashlib
import json
import os
import secrets
import time
from Crypto.Cipher import AES
from jsonschema import Draft202012Validator
from chainguard_gateway.canonical import canonical,validate
from chainguard_gateway.crypto import random_id
from chainguard_gateway.custom_tools import validate_manifest,check_grants
from .protocol import ToolError
from chainguard_gateway.github_read import GitHubFailure

class CustomLibrary:
    def __init__(self,store,*,repository_policy=None):
        self.store=store
        from chainguard_gateway.github_policy import configured_check
        self.repository_policy=repository_policy or (lambda query:configured_check(self.store,query))
        try:
            fd=os.open('custom-data.key',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=store.root_fd)
        except FileExistsError: pass
        else:
            with os.fdopen(fd,'wb') as stream: stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
        self.key=store.private_read('custom-data.key')
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS custom_tool_catalog(revision TEXT PRIMARY KEY,active INTEGER,data BLOB);
                CREATE TABLE IF NOT EXISTS custom_tool_capabilities(task_id TEXT,agent TEXT,data TEXT,PRIMARY KEY(task_id,agent));
                CREATE TABLE IF NOT EXISTS custom_tool_reads(id TEXT PRIMARY KEY,task_id TEXT,agent TEXT,revision TEXT,
                    arguments_sha256 TEXT,result_sha256 TEXT,observed_at INTEGER);
                CREATE TABLE IF NOT EXISTS custom_github_results(id TEXT PRIMARY KEY,fetch_id TEXT,status TEXT,data BLOB);''')
            db.execute('CREATE TABLE IF NOT EXISTS custom_http_results(id TEXT PRIMARY KEY,status TEXT,data BLOB)')

    def seal(self,revision,value):
        cipher=AES.new(self.key,AES.MODE_GCM);cipher.update(revision.encode())
        data,tag=cipher.encrypt_and_digest(canonical(value));return cipher.nonce+tag+data

    def open(self,revision,blob):
        cipher=AES.new(self.key,AES.MODE_GCM,nonce=blob[:16]);cipher.update(revision.encode())
        return json.loads(cipher.decrypt_and_verify(blob[32:],blob[16:32]))

    def item(self,db,revision):
        row=db.execute('SELECT * FROM custom_tool_catalog WHERE revision=?',(revision,)).fetchone()
        if not row: raise ToolError('NOT_FOUND')
        return dict(self.open(revision,row['data']),state='ACTIVE' if row['active'] else 'DISABLED')

    def install(self,key,manifest,records):
        self.store.authorize_operator(key);validate_manifest(manifest,records)
        if manifest['adapter']=='http.request':
            from .http_client import request
            from chainguard_gateway.http_tools import HTTPFailure
            try:
                installed=request(self.store,'install',{'manifest':manifest,'records':records})
                if installed!={'revision':manifest['revision'],'active':True}:raise ToolError('POLICY_REVOKED')
            except HTTPFailure:raise ToolError('EXECUTION_UNKNOWN') from None
        revision=manifest['revision'];value={'manifest':manifest,'records':records}
        with self.store.transaction() as db:
            old=db.execute('SELECT data FROM custom_tool_catalog WHERE revision=?',(revision,)).fetchone()
            if old:
                if self.open(revision,old[0])!=value: raise ToolError('PARAMS_MISMATCH')
                # Retrying activation never re-enables a previously revoked revision.
            else: db.execute('INSERT INTO custom_tool_catalog VALUES (?,?,?)',(revision,1,self.seal(revision,value)))
            return {'revision':revision,'active':self.item(db,revision)['state']=='ACTIVE'}

    def disable(self,key,revision):
        self.store.authorize_operator(key);validate('Bytes32',revision)
        with self.store.transaction() as db:
            self.item(db,revision)
            db.execute('UPDATE custom_tool_catalog SET active=0 WHERE revision=?',(revision,))
        if self.item_is_http(revision):
            from .http_client import request
            from chainguard_gateway.http_tools import HTTPFailure
            try:request(self.store,'disable',{'revision':revision})
            except HTTPFailure:raise ToolError('EXECUTION_UNKNOWN') from None
        return {'revision':revision,'active':False}

    def item_is_http(self,revision):
        with self.store.connect() as db:return self.item(db,revision)['manifest']['adapter']=='http.request'

    def grant(self,key,task_id,agent,tools,expires_at):
        self.store.authorize_operator(key);validate('Bytes32',task_id);validate('Address',agent)
        if type(expires_at) is not int or not int(time.time())<expires_at<=int(time.time())+86400: raise ToolError('RESERVATION_EXPIRED')
        with self.store.transaction() as db:
            check_grants(tools,[g.get('name') for g in tools if isinstance(g,dict)] if isinstance(tools,list) else [],lambda revision:self.item(db,revision))
            cap=canonical({'tools':tools,'expires_at':expires_at}).decode()
            row=db.execute('SELECT data FROM custom_tool_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
            if row and row[0]!=cap: raise ToolError('IDEMPOTENCY_CONFLICT')
            db.execute('INSERT OR IGNORE INTO custom_tool_capabilities VALUES (?,?,?)',(task_id,agent,cap))
        return {'granted':True}

    def execute(self,task_id,agent,tool_name,revision,arguments):
        validate('Bytes32',task_id);validate('Address',agent);validate('Bytes32',revision)
        with self.store.transaction() as db:
            row=db.execute('SELECT data FROM custom_tool_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
            if not row: raise ToolError('UNAUTHORIZED_SCOPE')
            cap=json.loads(row[0])
            if cap['expires_at']<=int(time.time()): raise ToolError('RESERVATION_EXPIRED')
            item=self.item(db,revision);manifest=item['manifest']
            if item['state']!='ACTIVE': raise ToolError('POLICY_REVOKED')
            grant=next((g for g in cap['tools'] if g['name']==tool_name and g['revision']==revision),None)
            if not grant or manifest['name']!=tool_name: raise ToolError('UNAUTHORIZED_SCOPE')
            if not Draft202012Validator(manifest['input_schema']).is_valid(arguments): raise ToolError('SCHEMA_INVALID')
            if arguments['query'] not in grant['allowed_keys']: raise ToolError('UNAUTHORIZED_SCOPE')
            record=next((r for r in item['records'] if r[manifest['key_field']]==arguments['query']),None)
            if record is None: raise ToolError('NOT_FOUND')
            github=manifest['adapter']=='github.read';http=manifest['adapter']=='http.request'
            if not github and not http:
                data={'record':{c:record[c] for c in manifest['output_fields']}}
                return self.record(db,task_id,agent,revision,tool_name,arguments,data,manifest)
        if http:return self.execute_http(task_id,agent,tool_name,revision,arguments)
        # No egress until the capability is checked; release the DB lock for HTTPS.
        from .github_client import query
        try:
            proof=self.repository_policy(arguments['query'])
            if not proof['allowed']:raise GitHubFailure('GITHUB_REPOSITORY_DENIED',repository_policy=proof)
            data,fetch_id,reader_proof=query(self.store,arguments['query'])
            proof=self.repository_policy(arguments['query'])
            if not proof['allowed']:raise GitHubFailure('GITHUB_REPOSITORY_DENIED',repository_policy=proof)
            if reader_proof.get('allowed') is not True or reader_proof.get('contract')!=proof['contract'] or reader_proof.get('repository_hash')!=proof['repository_hash']:
                raise GitHubFailure('GITHUB_POLICY_UNAVAILABLE')
        except GitHubFailure as error:
            id=random_id()
            with self.store.transaction() as db:
                db.execute('INSERT INTO custom_github_results VALUES (?,?,?,?)',(id,'',error.code,self.seal(id,{'error_code':error.code,'task_id':task_id,'revision':revision,'arguments':arguments,'repository_policy':error.repository_policy})))
            return {'status':'READ_FAILED','error_code':error.code,'read_execution_id':id,'repository_policy':error.repository_policy}
        with self.store.transaction() as db:
            # A disable/expired capability while waiting for GitHub cannot release data.
            row=db.execute('SELECT data FROM custom_tool_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
            if not row:raise ToolError('UNAUTHORIZED_SCOPE')
            cap=json.loads(row[0])
            if cap['expires_at']<=int(time.time()):raise ToolError('RESERVATION_EXPIRED')
            item=self.item(db,revision)
            if item['state']!='ACTIVE':raise ToolError('POLICY_REVOKED')
            if not any(g['name']==tool_name and g['revision']==revision and arguments['query'] in g['allowed_keys'] for g in cap['tools']):raise ToolError('UNAUTHORIZED_SCOPE')
            if data.get('record',{}).get('resource')!=arguments['query']:raise ToolError('PARAMS_MISMATCH')
            result=self.record(db,task_id,agent,revision,tool_name,arguments,data,item['manifest'])
            id=result['read_execution_id']
            result['repository_policy']=proof
            db.execute('INSERT INTO custom_github_results VALUES (?,?,?,?)',(id,fetch_id,'OK',self.seal(id,{'data':data,'repository_policy':proof,'reader_policy':reader_proof})))
            return result

    def execute_http(self,task_id,agent,tool_name,revision,arguments):
        from .http_client import request
        from chainguard_gateway.http_tools import HTTPFailure
        id='0x'+hashlib.sha256(canonical({'task_id':task_id,'agent':agent,'revision':revision,'arguments':arguments})).hexdigest()
        with self.store.transaction() as db:
            item=self.item(db,revision)
            caprow=db.execute('SELECT data FROM custom_tool_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
            if item['state']!='ACTIVE':raise ToolError('POLICY_REVOKED')
            if not caprow:raise ToolError('UNAUTHORIZED_SCOPE')
            cap=json.loads(caprow[0])
            if cap['expires_at']<=int(time.time()):raise ToolError('RESERVATION_EXPIRED')
            if not any(g['name']==tool_name and g['revision']==revision and arguments['query'] in g['allowed_keys'] for g in cap['tools']):raise ToolError('UNAUTHORIZED_SCOPE')
            old=db.execute('SELECT * FROM custom_http_results WHERE id=?',(id,)).fetchone()
            if old:
                if old['status']=='OK':return self.open(id,old['data'])
                return {'status':'READ_FAILED','error_code':'HTTP_EXECUTION_UNKNOWN','read_execution_id':id}
            db.execute('INSERT INTO custom_http_results VALUES (?,?,?)',(id,'STARTED',None))
        try:
            fetched=request(self.store,'fetch',{'revision':revision,'profile':arguments['query'],'execution_id':id})
            data=fetched['data']
            with self.store.transaction() as db:
                cap=json.loads(db.execute('SELECT data FROM custom_tool_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()[0])
                item=self.item(db,revision)
                if item['state']!='ACTIVE':raise ToolError('POLICY_REVOKED')
                if cap['expires_at']<=int(time.time()):raise ToolError('RESERVATION_EXPIRED')
                if not any(g['name']==tool_name and g['revision']==revision and arguments['query'] in g['allowed_keys'] for g in cap['tools']):raise ToolError('UNAUTHORIZED_SCOPE')
                if fetched['fetch_id']!=id or data.get('record',{}).get('profile')!=arguments['query']:raise ToolError('PARAMS_MISMATCH')
                manifest=item['manifest'];profile=next(r for r in item['records'] if r['profile']==arguments['query']);source=data.get('source',{})
                request_sha=hashlib.sha256(canonical({'http':manifest['http'],'record':profile})).hexdigest()
                if (source.get('url')!=manifest['http']['url'] or source.get('method')!=manifest['http']['method'] or
                    source.get('request_sha256')!=request_sha or type(source.get('http_status')) is not int or not 200<=source['http_status']<300):raise ToolError('PARAMS_MISMATCH')
                result=self.record(db,task_id,agent,revision,tool_name,arguments,data,item['manifest'])
                result['http_execution_id']=id
                db.execute('UPDATE custom_http_results SET status=?,data=? WHERE id=?',('OK',self.seal(id,result),id))
                return result
        except HTTPFailure as error:
            with self.store.transaction() as db:db.execute('UPDATE custom_http_results SET status=? WHERE id=?',(error.code,id))
            return {'status':'READ_FAILED','error_code':error.code,'read_execution_id':id}

    def record(self,db,task_id,agent,revision,tool_name,arguments,data,manifest):
        if not Draft202012Validator(manifest['output_schema']).is_valid(data): raise ToolError('SCHEMA_INVALID')
        sha=hashlib.sha256(canonical(data)).hexdigest();id=random_id()
        db.execute('INSERT INTO custom_tool_reads VALUES (?,?,?,?,?,?,?)',
            (id,task_id,agent,revision,hashlib.sha256(canonical(arguments)).hexdigest(),sha,int(time.time())))
        return {'tool_name':tool_name,'revision':revision,'trust':'untrusted','data':data,'sha256':sha,'read_execution_id':id}
