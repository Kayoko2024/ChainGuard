"""Bounded, transient async GET verification jobs; results grant no authority."""
from concurrent.futures import ThreadPoolExecutor
import secrets
import threading
import time
from chainguard_sandbox.protocol import ToolError


class VerificationJobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='chain-verification')
        self.lock=threading.Lock();self.jobs={}

    def submit(self,key,verify):
        with self.lock:
            now=time.monotonic()
            self.jobs={id:j for id,j in self.jobs.items() if not j['future'].done() or now-j['created']<300}
            for id,j in self.jobs.items():
                if j['key']==key and not j['future'].done():return self.get(id,locked=True)
            if len(self.jobs)>=64:raise ToolError('QUEUE_FULL')
            id=secrets.token_hex(16);self.jobs[id]=dict(key=key,created=now,future=self.pool.submit(verify))
            return dict(status='PENDING',verification_id=id)

    def get(self,id,*,locked=False):
        if not locked:
            with self.lock:return self.get(id,locked=True)
        j=self.jobs.get(id)
        if not j:raise ToolError('NOT_FOUND')
        if not j['future'].done():return dict(status='PENDING',verification_id=id)
        try:result=j['future'].result()
        except Exception:result=dict(status='UNAVAILABLE',reason='CHAIN_UNAVAILABLE')
        return dict(status='COMPLETED',verification_id=id,result=result)
