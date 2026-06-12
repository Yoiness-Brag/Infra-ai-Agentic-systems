"""JWT verification (defense-in-depth, after Kong's jwt plugin).

Verifies an HS256 bearer token: signature, ``iss == JWT_ISS`` and ``exp``.
Returns the token subject. Any failure -> HTTP 401.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

logger = logging.getLogger("agent_backend.auth")

_CLOCK_SKEW_LEEWAY_SECONDS = 30

_bearer = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> str:
    """FastAPI dependency: validate JWT and return the subject (``sub``)."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized("missing bearer token")

    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_iss,
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            options={
                "require": ["exp", "iss"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": False,
            },
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("token expired") from None
    except jwt.InvalidIssuerError:
        raise _unauthorized("invalid issuer") from None
    except jwt.InvalidTokenError as exc:
        raise _unauthorized(f"invalid token: {exc.__class__.__name__}") from None

    subject = claims.get("sub")
    if not subject:
        raise _unauthorized("token missing subject")
    return str(subject)


def _unauthorized(reason: str) -> HTTPException:
    logger.warning("jwt rejected", extra={"reason": reason})
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )
