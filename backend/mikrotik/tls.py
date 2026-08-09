"""TLS pinning for the exact RouterOS classic API socket."""

from __future__ import annotations

import hashlib
import hmac
import ssl
import string
from typing import Any


class TlsFingerprintMismatch(ConnectionError):
    """The RouterOS leaf certificate differs from its configured pin."""


def normalize_fingerprint(value: str) -> str:
    normalized = value.replace(":", "").strip().lower()
    if len(normalized) != 64 or any(
        character not in string.hexdigits.lower() for character in normalized
    ):
        raise ValueError("TLS fingerprint must be a SHA-256 hex digest")
    return normalized


class PinnedTlsContext:
    """Verify the leaf on the same TLS socket used for API authentication."""

    def __init__(self, expected: str, *, ssl_context: Any | None = None) -> None:
        self.expected = normalize_fingerprint(expected)
        if ssl_context is None:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            ssl_context = context
        self._context = ssl_context

    def wrap_socket(self, *args: Any, **kwargs: Any) -> Any:
        tls_socket = self._context.wrap_socket(*args, **kwargs)
        certificate = tls_socket.getpeercert(binary_form=True)
        actual = hashlib.sha256(certificate or b"").hexdigest()
        if not certificate or not hmac.compare_digest(actual, self.expected):
            tls_socket.close()
            raise TlsFingerprintMismatch("RouterOS TLS fingerprint mismatch")
        return tls_socket
