"""Four-node event polling into a durable display cache, never an authorization source."""
import json
import time
from chainguard_sandbox.protocol import ToolError


class ChainEventIndexer:
    def __init__(self,store,chain,extra_addresses=()):
        self.store,self.chain=store,chain;self.started=False;self.extra_addresses=list(extra_addresses)
        with store.db() as db:db.execute('''CREATE TABLE IF NOT EXISTS indexed_chain_events(
            tx_hash TEXT NOT NULL,log_index TEXT NOT NULL,block_number INTEGER NOT NULL,
            block_hash TEXT NOT NULL,data TEXT NOT NULL,observed REAL NOT NULL,PRIMARY KEY(tx_hash,log_index))''')

    def tick(self):
        if not self.started:self.chain.healthy();self.started=True
        nodes=self.chain.nodes
        heights=[int(n.call('eth_blockNumber'),16) for n in nodes];height=min(heights)
        cursor=self.store.cached('chain_event_cursor')
        if cursor:
            previous=[n.call('eth_getBlockByNumber',[hex(cursor['height']),False]) for n in nodes]
            if any(not b or b['hash']!=cursor['hash'] for b in previous):raise ToolError('CHAIN_UNAVAILABLE')
            start=cursor['height']+1
        else:
            # On upgrade/recovery include known receipts that predate this
            # listener, rather than silently starting after those transactions.
            known=[int(ev['block_number']) for record in self.store.cached('records',{}).values()
                for key in ('reservation_evidence','finalization_evidence')
                if (ev:=record.get(key)) and ev.get('block_number') is not None]
            start=max(0,min([height-1,*known]))
        end=min(height,start+499)
        if end<start:return
        deployments=[self.chain.config,*self.chain.config.get('legacyDeployments',[])]
        addresses=sorted({item['address'] for d in deployments for item in d['contracts'].values()}|set(self.extra_addresses))
        query=dict(address=addresses,fromBlock=hex(start),toBlock=hex(end))
        batches=[n.call('eth_getLogs',[query]) for n in nodes]
        normalized=[json.dumps(sorted(logs,key=lambda l:(int(l['blockNumber'],16),int(l['logIndex'],16))),sort_keys=True) for logs in batches]
        blocks=[n.call('eth_getBlockByNumber',[hex(end),False]) for n in nodes]
        if len(set(normalized))!=1 or any(not b for b in blocks) or len({b['hash'] for b in blocks})!=1:raise ToolError('CHAIN_UNAVAILABLE')
        if any(l.get('removed') or not start<=int(l['blockNumber'],16)<=end or l['address'].lower() not in {a.lower() for a in addresses} for l in batches[0]):raise ToolError('CHAIN_UNAVAILABLE')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for log in batches[0]:db.execute('INSERT OR IGNORE INTO indexed_chain_events VALUES (?,?,?,?,?,?)',(log['transactionHash'],log['logIndex'],int(log['blockNumber'],16),log['blockHash'],json.dumps(log,sort_keys=True),time.time()))
            # The cursor and events commit together; a restart cannot skip a batch.
            value=dict(height=end,hash=blocks[0]['hash'],checked_nodes=len(nodes))
            db.execute('INSERT INTO projections VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',('chain_event_cursor',self.store.seal('projection/chain_event_cursor',value),time.time()))
        return end<height
