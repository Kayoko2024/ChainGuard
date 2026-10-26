"""Actual TLS client identity, independent service bearer, bounded JSON I/O."""
import hashlib
import hmac
import http.client
import ssl
from urllib.parse import urlsplit

from uvicorn.protocols.http.h11_impl import H11Protocol

from .canonical import canonical, parse_json
from chainguard_sandbox.protocol import ToolError


class PeerCertificateProtocol(H11Protocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        tls = transport.get_extra_info('ssl_object')
        peer = tls.getpeercert(binary_form=True) if tls else None
        fingerprint = hashlib.sha256(peer).hexdigest() if peer else None
        original = self.app

        async def with_verified_peer(scope, receive, send):
            scope = dict(scope, chainguard_peer_fingerprint=fingerprint)
            await original(scope,receive,send)
        self.app = with_verified_peer


def service_identity(request, fingerprint, token):
    if not request.scope.get('chainguard_peer_fingerprint'):
        raise ToolError('AUTH_REQUIRED')
    if not hmac.compare_digest(request.scope['chainguard_peer_fingerprint'],fingerprint):
        raise ToolError('FORBIDDEN')
    if not hmac.compare_digest(request.headers.get('authorization',''),'Bearer '+token):
        raise ToolError('AUTH_REQUIRED')


class TLSClient:
    def __init__(self,url,ca,certificate,key,token):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.path not in ('','/'):
            raise ValueError('Pinned HTTPS service endpoint required')
        self.host,self.port=parsed.hostname,parsed.port or 443
        self.context=ssl.create_default_context(cafile=str(ca))
        self.context.load_cert_chain(str(certificate),str(key))
        self.token=token

    def request(self,method,path,body=None,key=None):
        connection=http.client.HTTPSConnection(self.host,self.port,context=self.context,timeout=8)
        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'}
        if key: headers['Idempotency-Key']=key
        try:
            connection.request(method,path,body=canonical(body) if body is not None else None,headers=headers)
            response=connection.getresponse()
            data=response.read(65537)
            value=parse_json(data)
            if response.status>=400:
                code=value.get('error',{}).get('code')
                from .canonical import ERRORS
                raise ToolError(code if code in ERRORS else 'EXECUTION_UNKNOWN')
            return value
        except (OSError,TimeoutError,http.client.HTTPException,ValueError):
            raise ToolError('EXECUTION_UNKNOWN') from None
        finally:
            connection.close()


async def request_body(request,name):
    from .canonical import validate
    if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
        raise ToolError('SCHEMA_INVALID')
    parts=[]
    length=0
    async for part in request.stream():
        length+=len(part)
        if length>65536: raise ToolError('SCHEMA_INVALID')
        parts.append(part)
    return validate(name,parse_json(b''.join(parts)))
