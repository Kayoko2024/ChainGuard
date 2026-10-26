"""Pinned HS256 local JWTs; roles and organization always come from the registry."""

import base64
import hashlib
import hmac
import re
import time

from .canonical import canonical, parse_json
from .crypto import random_id
from chainguard_sandbox.protocol import ToolError

ISSUER = "chainguard-local-central"
AUDIENCE = "chainguard-central-gateway"


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _decode(value):
    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ValueError()
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def issue_token(key, subject, lifetime=600):
    if len(key) < 32 or type(lifetime) is not int or not 1 <= lifetime <= 900:
        raise ValueError("Invalid local JWT configuration")
    stamp = int(time.time())
    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": subject, "iat": stamp, "nbf": stamp,
              "exp": stamp + lifetime, "jti": random_id()}
    unsigned = _b64(canonical({"alg": "HS256", "typ": "JWT"})) + "." + _b64(canonical(claims))
    return unsigned + "." + _b64(hmac.digest(key, unsigned.encode(), "sha256"))


def authenticate(key, authorization):
    try:
        if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 4096:
            raise ValueError()
        token = authorization[7:]
        head, body, signature = token.split(".")
        expected = hmac.digest(key, (head + "." + body).encode("ascii"), "sha256")
        if not hmac.compare_digest(expected, _decode(signature)):
            raise ValueError()
        if parse_json(_decode(head)) != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError()
        claims = parse_json(_decode(body))
        if type(claims) is not dict or set(claims) != {"iss", "aud", "sub", "iat", "nbf", "exp", "jti"}:
            raise ValueError()
        stamp = int(time.time())
        if (claims["iss"] != ISSUER or claims["aud"] != AUDIENCE or type(claims["sub"]) is not str
                or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", claims["sub"]) is None
                or any(type(claims[k]) is not int for k in ("iat", "nbf", "exp"))
                or not claims["iat"] <= stamp < claims["exp"] or not claims["nbf"] <= stamp
                or not 0 < claims["exp"] - claims["iat"] <= 900):
            raise ValueError()
        return claims["sub"]
    except (ValueError, TypeError, UnicodeError, ToolError):
        raise ToolError("AUTH_REQUIRED") from None
