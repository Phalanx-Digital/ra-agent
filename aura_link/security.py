from __future__ import annotations

import hmac
import ssl
from pathlib import Path


def bearer_from_headers(headers: object) -> str:
    authorization = getattr(headers, "get", lambda *_: "")("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" else ""


def constant_time_token_valid(provided: str, expected: str) -> bool:
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def client_ssl_context(ca_file: str | None = None) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=ca_file)


def server_ssl_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    if not Path(cert_file).exists() or not Path(key_file).exists():
        raise FileNotFoundError("TLS certificate/key not found")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_file, key_file)
    return context

