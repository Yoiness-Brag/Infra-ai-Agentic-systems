"""Mint a short-lived HS256 JWT for local testing (iss from JWT_ISS, secret from JWT_SECRET)."""
import base64
import hashlib
import hmac
import json
import os
import sys
import time


def b64(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def segment(obj: dict) -> bytes:
    return b64(json.dumps(obj, separators=(",", ":")).encode())


def main() -> int:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        print("JWT_SECRET is empty", file=sys.stderr)
        return 1
    issuer = os.environ.get("JWT_ISS", "mvp-app")
    subject = os.environ.get("JWT_SUB", "smoke-user")
    ttl = int(os.environ.get("JWT_TTL_SECONDS", "900"))
    now = int(time.time())

    header = segment({"alg": "HS256", "typ": "JWT"})
    payload = segment({"iss": issuer, "sub": subject, "iat": now, "exp": now + ttl})
    signing_input = header + b"." + payload
    signature = b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    sys.stdout.write((signing_input + b"." + signature).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
