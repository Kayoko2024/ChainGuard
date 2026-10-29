"""Observational timings only. No change to transaction bytes or authorization."""
import json
import logging
import sys
import time


def performance_logger():
    logger=logging.getLogger('chainguard.performance')
    if not logger.handlers:
        handler=logging.StreamHandler(sys.__stderr__);handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO);logger.propagate=False
    return logger


class TransactionMetrics:
    def __init__(self,store):
        self.store=store
        with store.transaction() as db:db.execute('''CREATE TABLE IF NOT EXISTS transaction_metrics(
            tx_hash TEXT PRIMARY KEY,action_id TEXT NOT NULL,kind TEXT NOT NULL,
            submitted_at_ms INTEGER,confirmed_at_ms INTEGER,confirmation_observed_ms INTEGER)''')

    def submitted(self,tx_hash,action_id,kind):
        with self.store.transaction() as db:db.execute('INSERT OR IGNORE INTO transaction_metrics(tx_hash,action_id,kind,submitted_at_ms) VALUES (?,?,?,?)',(tx_hash,action_id,kind,time.time_ns()//1000000))

    def confirmed(self,db,tx_hash):
        row=db.execute('SELECT * FROM transaction_metrics WHERE tx_hash=?',(tx_hash,)).fetchone()
        if not row or row['confirmed_at_ms'] is not None:return
        now=time.time_ns()//1000000;elapsed=max(0,now-row['submitted_at_ms'])
        db.execute('UPDATE transaction_metrics SET confirmed_at_ms=?,confirmation_observed_ms=? WHERE tx_hash=?',(now,elapsed,tx_hash))
        performance_logger().info(json.dumps(dict(event='FOUR_NODE_RECEIPT_VERIFIED',tx_hash=tx_hash,kind=row['kind'],
            submitted_at_ms=row['submitted_at_ms'],confirmed_at_ms=now,confirmation_observed_ms=elapsed)))
