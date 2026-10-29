"""Only the trusted tool process can reach the internal reviewed-HTTP service."""
import json
import urllib.error
import urllib.request
from chainguard_gateway.canonical import canonical,parse_json
from chainguard_gateway.github_read import NoRedirect
from chainguard_gateway.http_tools import HTTPFailure


def request(store,operation,value):
    try:
        config=json.loads(store.private_read('http-reader.json'))
        if set(config)!={'token'}:raise ValueError()
        r=urllib.request.Request('http://http-reader:8080/'+operation,data=canonical(value),method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+config['token']})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(r,timeout=10) as response:return parse_json(response.read(131073))
    except urllib.error.HTTPError as error:
        try:code=parse_json(error.read(8192))['error']['code']
        except Exception:code='HTTP_UNAVAILABLE'
        allowed={'HTTP_TARGET_DENIED','HTTP_UNAVAILABLE','HTTP_EXECUTION_UNKNOWN','HTTP_LOCAL_RATE_LIMIT','HTTP_REDIRECT_REJECTED','HTTP_REMOTE_ERROR','HTTP_RESPONSE_INVALID','HTTP_RESPONSE_TOO_LARGE','POLICY_REVOKED','UNAUTHORIZED_SCOPE','IDEMPOTENCY_CONFLICT'}
        raise HTTPFailure(code if isinstance(code,str) and code in allowed else 'HTTP_UNAVAILABLE') from None
    except (OSError,ValueError,KeyError,urllib.error.URLError):raise HTTPFailure('HTTP_UNAVAILABLE') from None
