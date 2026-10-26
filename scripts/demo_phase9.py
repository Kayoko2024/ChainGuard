"""Read-only demonstrator. --fresh creates new real sandbox/chain evidence first."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from smoke_audit import smoke


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8080')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--fresh',action='store_true',help='Run real phase8 protocol experiments before deploying a refreshed catalog')
    args=parser.parse_args()
    output=(args.out or ROOT/'results/phase9/demos'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')).resolve()
    if output.exists() or not output.is_relative_to(ROOT/'results/phase9'):raise ValueError('New phase9 output required')
    output.mkdir(parents=True)
    if args.fresh:
        # Original protocol runner creates actual restricted side effects/transactions.
        from urllib.parse import urlsplit
        port=urlsplit(args.url).port
        if not args.url.startswith('http://127.0.0.1:') or port is None:raise ValueError('Local URL with port required')
        result=subprocess.run([sys.executable,str(ROOT/'scripts/deploy_phase9.py'),'--out',str(output/'fresh-deployment'),'--port',str(port)],cwd=ROOT)
        if result.returncode:raise SystemExit(result.returncode)
    report=smoke(args.url)
    (output/'demo-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('1. 查看四节点共同区块高度；历史快照与当前查链分列。')
    print('2. 合法发送：原工具卷已核验副作用；重新核验预约、两组织签名、工具回执及finalize。')
    for tx in report['normal']['transactions']:
        print(tx['kind']+' '+tx['tx_hash']+' block='+tx['block_number']+' nodes='+str(tx['node_receipts']))
    print('3. 越权无预约记录：'+report['denied_entry']+'；没有伪造拒绝交易。')
    print('4. UNKNOWN：'+report['unknown']['status']+'，不推断未执行，不重新派发。')
    print('5. 伪造/重放/篡改效果及置信区间见独立协议报告；真实模型未攻击不算网关阻断。')
    print('演示PASS；没有用截图或浏览器状态替代链证据。')


if __name__=='__main__':main()
