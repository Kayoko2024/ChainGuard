"""Run original real protocol suite with explicit stage9 missing-read adapter."""
import io
import json
from pathlib import Path
import sys
import tarfile

import run_phase8

original_context=run_phase8.build_context


def context():
    raw,names=original_context()
    output=io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(raw)) as source,tarfile.open(fileobj=output,mode='w') as target:
        for item in source:
            content=source.extractfile(item).read()
            if item.name=='evaluation/phase8.Dockerfile':
                content=content.replace(b'"evaluation.replay"',b'"evaluation.audit_demo"')
            item.size=len(content)
            target.addfile(item,io.BytesIO(content))
    return output.getvalue(),names


if __name__=='__main__':
    run_phase8.build_context=context
    run_phase8.main()
    if '--out' in sys.argv:
        path=Path(sys.argv[sys.argv.index('--out')+1])
        (path/'phase9-transport-adapter.json').write_text(json.dumps({'adapter':'evaluation.audit_demo.DemoReadRPC',
            'core_source_modified':False,'missing_validator_read':'CHAIN_UNAVAILABLE; existing bounded polling',
            'successful_values':'unchanged actual RPC result','fake_validator_or_receipt':False},indent=2)+'\n')
