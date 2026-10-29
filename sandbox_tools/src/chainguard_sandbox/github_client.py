"""Tool-only access to the fixed internal public GitHub reader."""
import json
import urllib.request
import urllib.error
from chainguard_gateway.canonical import canonical,parse_json
from chainguard_gateway.github_read import GitHubFailure,NoRedirect

def query(store,key):
    try:
        config=json.loads(store.private_read('github-reader.json'))
        if set(config)!={'token'}:raise ValueError()
        request=urllib.request.Request('http://github-reader:8080/fetch',data=canonical({'query':key}),method='POST',headers={'Content-Type':'application/json','Authorization':'Bearer '+config['token']})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=6) as r:
            value=parse_json(r.read(65537))
            return value['data'],value['fetch_id'],value['repository_policy']
    except urllib.error.HTTPError as error:
        try:
            value=parse_json(error.read(8192));code=value['error']['code'];proof=value.get('repository_policy')
        except Exception:code,proof='GITHUB_UNAVAILABLE',None
        raise GitHubFailure(code if code in {'GITHUB_REPOSITORY_DENIED','GITHUB_POLICY_UNAVAILABLE','GITHUB_RATE_LIMITED','GITHUB_LOCAL_RATE_LIMIT','GITHUB_NOT_FOUND','GITHUB_REDIRECT_REJECTED','GITHUB_HTTP_ERROR','GITHUB_RESPONSE_INVALID','GITHUB_RESOURCE_MISMATCH','GITHUB_RESPONSE_TOO_LARGE'} else 'GITHUB_UNAVAILABLE',error.code,repository_policy=proof) from None
    except (OSError,ValueError,KeyError,urllib.error.URLError):raise GitHubFailure('GITHUB_UNAVAILABLE') from None
