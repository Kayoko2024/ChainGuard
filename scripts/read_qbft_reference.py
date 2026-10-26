"""Read official QBFT reference values; never execute downloaded content."""
import html
import json
from pathlib import Path
import re
import urllib.request

url = 'https://docs.besu-eth.org/private-networks/tutorials/qbft'
with urllib.request.urlopen(url, timeout=40) as response:
    raw = response.read().decode('utf-8')
text = html.unescape(re.sub('<[^>]+>', '', raw))
matches = re.findall(r'"mixHash"\s*:\s*"(0x[0-9a-f]+)"', text)
result = {'source': url, 'mixHash': list(dict.fromkeys(matches))}
Path('results/phase4/upstream-qbft-reference.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
