"""Task-scoped R0 sandbox reads; no send/delete/host path/network capability."""
import hashlib
import json
import time
from email import policy
from email.parser import BytesParser

from chainguard_gateway.canonical import canonical, validate
from chainguard_gateway.crypto import random_id
from chainguard_gateway.default_tools import READ_TOOLS, DOCUMENTS, RECIPIENTS, functions
from jsonschema import Draft202012Validator
from .protocol import ToolError
from .resources import Resources
from .read_broker import ReadBroker


MAX_CAPABILITY_SECONDS = 86400


def validate_capability_expiry(expires_at):
    """The task-bound default library accepts at most the approved 24h window."""
    if type(expires_at) is not int: raise ToolError('SCHEMA_INVALID')
    now=int(time.time())
    if expires_at<=now: raise ToolError('RESERVATION_EXPIRED')
    if expires_at>now+MAX_CAPABILITY_SECONDS: raise ToolError('READ_CAPABILITY_WINDOW_INVALID')


class DefaultLibrary:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS library_capabilities(
                task_id TEXT, agent TEXT, data TEXT NOT NULL, PRIMARY KEY(task_id,agent));
                CREATE TABLE IF NOT EXISTS library_reads(id TEXT PRIMARY KEY, task_id TEXT, agent TEXT,
                tool TEXT, arguments_sha256 TEXT, result_sha256 TEXT, observed_at INTEGER);''')

    def grant(self,key,task_id,agent,tools,documents,mailboxes,expires_at):
        self.store.authorize_operator(key)
        validate('Bytes32',task_id); validate('Address',agent)
        for values,allowed in [(tools,READ_TOOLS),(documents,DOCUMENTS),(mailboxes,RECIPIENTS)]:
            if type(values) is not list or any(type(v) is not str for v in values) or len(values)!=len(set(values)) or not set(values)<=set(allowed):
                raise ToolError('UNAUTHORIZED_SCOPE')
        validate_capability_expiry(expires_at)
        broker=ReadBroker(self.store)
        # The operator creates only the built-in, synthetic documents. Never overwrite.
        for id in documents:
            with self.store.connect() as db: exists=db.execute('SELECT 1 FROM documents WHERE doc_id=?',(id,)).fetchone()
            if not exists: broker.provision(key,[{'doc_id':id,'source_kind':'document','content':DOCUMENTS[id][1]}])
        cap={'tools':tools,'documents':documents,'mailboxes':mailboxes,'expires_at':expires_at}
        with self.store.transaction() as db:
            old=db.execute('SELECT data FROM library_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
            if old and json.loads(old[0])!=cap: raise ToolError('IDEMPOTENCY_CONFLICT')
            db.execute('INSERT OR IGNORE INTO library_capabilities VALUES (?,?,?)',(task_id,agent,canonical(cap).decode()))
        if 'doc.read' in tools:
            with self.store.transaction() as db:
                for id in documents:
                    db.execute('INSERT OR IGNORE INTO read_capabilities VALUES (?,?,?,?)',(task_id,agent,id,expires_at))
        return {'granted':True,'tools':tools,'documents':documents,'mailboxes':mailboxes}

    def execute(self,task_id,agent,name,args):
        validate('Bytes32',task_id); validate('Address',agent)
        if name not in READ_TOOLS or name=='doc.read': raise ToolError('UNKNOWN_TOOL')
        schema=functions([name])[0]['function']['parameters']
        if not Draft202012Validator(schema).is_valid(args): raise ToolError('SCHEMA_INVALID')
        with self.store.connect() as db:
            row=db.execute('SELECT data FROM library_capabilities WHERE task_id=? AND agent=?',(task_id,agent)).fetchone()
        if not row: raise ToolError('UNAUTHORIZED_SCOPE')
        cap=json.loads(row[0])
        if name not in cap['tools']: raise ToolError('UNAUTHORIZED_SCOPE')
        if int(time.time())>=cap['expires_at']: raise ToolError('RESERVATION_EXPIRED')
        resources=Resources(self.store)
        with self.store.connect() as db:
            if name.startswith('doc.'):
                items=[]
                for id in cap['documents']:
                    document=resources.lookup(db,id)
                    if document['scope']!='PUBLIC_DOCS': raise ToolError('UNAUTHORIZED_SCOPE')
                    item={'doc_id':id,'title':DOCUMENTS[id][0],'sha256':document['sha256'],'size':document['size']}
                    if name=='doc.search':
                        content=resources.read_verified(document).decode('utf8')
                        offset=content.casefold().find(args['query'].casefold())
                        if offset<0: continue
                        item['snippet']=content[max(0,offset-60):offset+180]
                    items.append(item)
                data={'documents':items}
            else:
                boxes=cap['mailboxes']
                # Exact recipient scope, parameterized SQL; no arbitrary database/path.
                query='SELECT message_id,recipient,mime,mime_sha256 FROM mailbox WHERE recipient IN ('+','.join('?' for _ in boxes)+')'
                values=list(boxes)
                if name=='mail.read': query+=' AND message_id=?'; values.append(args['message_id'])
                query+=' ORDER BY message_id DESC LIMIT 50'
                mails=db.execute(query,values).fetchall() if boxes else []
                if name=='mail.read' and not mails: raise ToolError('UNAUTHORIZED_SCOPE')
                items=[]
                for mail in mails:
                    sha=hashlib.sha256(mail['mime']).hexdigest()
                    if sha!=mail['mime_sha256']: raise ToolError('RECEIPT_INVALID')
                    parsed=BytesParser(policy=policy.default).parsebytes(mail['mime'])
                    item={'message_id':str(mail['message_id']),'recipient':mail['recipient'],
                        'subject':str(parsed['Subject'] or ''),'mime_sha256':sha}
                    if name=='mail.read':
                        part=parsed.get_body(preferencelist=('plain',))
                        item['body']=part.get_content() if part else ''
                    items.append(item)
                data={'messages':items,'limit':50}
        sha=hashlib.sha256(canonical(data)).hexdigest(); id=random_id()
        with self.store.transaction() as db:
            db.execute('INSERT INTO library_reads VALUES (?,?,?,?,?,?,?)',
                (id,task_id,agent,name,hashlib.sha256(canonical(args)).hexdigest(),sha,int(time.time())))
        return {'tool_name':name,'trust':'untrusted','data':data,'sha256':sha,'read_execution_id':id}
