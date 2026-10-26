"""R0 synthetic fixture reads with explicit tool-owned task/document capabilities."""
import base64
import json
import time

from .protocol import ToolError,document_id
from .tools import LocalTestTools
from .resources import Resources
from chainguard_gateway.canonical import validate
from chainguard_gateway.crypto import random_id


class ReadBroker:
    def __init__(self,store):
        self.store=store
        self.tools=LocalTestTools(store)
        with store.connect() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS read_capabilities(task_id TEXT,agent TEXT,doc_id TEXT,expires_at INTEGER,
 PRIMARY KEY(task_id,agent,doc_id));
CREATE TABLE IF NOT EXISTS observation_sources(doc_id TEXT PRIMARY KEY,source_kind TEXT NOT NULL);
''')

    def provision(self,key,documents):
        self.store.authorize_operator(key)
        for item in documents:
            if item['source_kind'] not in {'document','email'}: raise ToolError('SCHEMA_INVALID')
            Resources(self.store).create_document(key,item['doc_id'],item['content'].encode(),scope='PUBLIC_DOCS')
            with self.store.transaction() as db:
                db.execute('INSERT INTO observation_sources VALUES (?,?)',(item['doc_id'],item['source_kind']))

    def grant(self,key,task_id,agent,documents,expires_at):
        self.store.authorize_operator(key)
        validate('Bytes32',task_id); validate('Address',agent)
        if not int(time.time())<expires_at<=int(time.time())+3600: raise ToolError('RESERVATION_EXPIRED')
        with self.store.transaction() as db:
            for doc_id in documents:
                resource=Resources(self.store).lookup(db,doc_id)
                if resource['scope']!='PUBLIC_DOCS': raise ToolError('UNAUTHORIZED_SCOPE')
                db.execute('INSERT INTO read_capabilities VALUES (?,?,?,?)',(task_id,agent,doc_id,expires_at))

    def read(self,task_id,agent,doc_id):
        validate('Bytes32',task_id); validate('Address',agent); document_id(doc_id)
        with self.store.connect() as db:
            grant=db.execute('SELECT * FROM read_capabilities WHERE task_id=? AND agent=? AND doc_id=?',(task_id,agent,doc_id)).fetchone()
            source=db.execute('SELECT source_kind FROM observation_sources WHERE doc_id=?',(doc_id,)).fetchone()
        if not grant or not source: raise ToolError('UNAUTHORIZED_SCOPE')
        if int(time.time())>=grant['expires_at']: raise ToolError('RESERVATION_EXPIRED')
        key=self.store.private_read('operator.key').decode()
        action_id=random_id()
        token=self.tools.issue_permit(key,action_id,'agent-reader','doc.read',{'doc_id':doc_id},scope='PUBLIC_DOCS',allowed_documents=[doc_id])
        result=self.tools.execute(action_id,'agent-reader','doc.read',{'doc_id':doc_id},token)
        if result['state']!='COMPLETED': raise ToolError('EXECUTION_UNKNOWN')
        value=result['result']
        return {'doc_id':doc_id,'source_kind':source['source_kind'],'trust':'untrusted','content':base64.b64decode(value['content_b64']).decode(),
            'sha256':value['sha256'],'read_execution_id':action_id}
