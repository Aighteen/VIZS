"""Public URL admission for provider-only retrieval, NOT a safe direct HTTP fetcher.

Direct fetches would additionally require connection pinning and redirect validation.
"""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit


class UnsafeURL(ValueError):
    pass


def public_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048 or re.search(r"[\x00-\x20\\]", value):
        raise UnsafeURL("Invalid URL")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
    except (ValueError, UnicodeError) as exc:
        raise UnsafeURL("Invalid URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not host or parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("Public HTTP(S) URL required")
    if port not in {None, 80, 443} or "%" in host:
        raise UnsafeURL("Unsupported destination")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")) or host == "localhost":
            raise UnsafeURL("Nonpublic destination")
        if not re.fullmatch(r"[a-z0-9.-]+", host) or any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in host.split(".")):
            raise UnsafeURL("Invalid hostname")
        # Reject alternate numeric IPv4 encodings (127.1, integer, octal, hex).
        if all(re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", p) for p in host.split(".")):
            raise UnsafeURL("Ambiguous numeric destination")
    else:
        if not address.is_global or getattr(address, "ipv4_mapped", None) is not None:
            raise UnsafeURL("Nonpublic address")
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority += f":{port}"
    return urlunsplit((parsed.scheme.lower(), authority, parsed.path or "/", parsed.query, ""))


async def validate_public_destination(value: str, resolver=None) -> str:
    """Reject mixed public/private DNS answers before sending URL to provider.

    This does not promise DNS-rebinding protection for direct fetching. No code in
    this package connects to the returned destination.
    """
    normalized = public_url(value)
    host = urlsplit(normalized).hostname
    if resolver is None:
        resolver = asyncio.get_running_loop().getaddrinfo
    try:
        async with asyncio.timeout(2):
            answers = await resolver(host, None, type=socket.SOCK_STREAM)
        if not answers or any(not ipaddress.ip_address(a[4][0]).is_global for a in answers):
            raise UnsafeURL("Nonpublic DNS destination")
    except (OSError, ValueError, TimeoutError) as exc:
        raise UnsafeURL("Destination unavailable or unsafe") from exc
    return normalized
