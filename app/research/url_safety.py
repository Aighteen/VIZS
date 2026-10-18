"""Public URL admission for provider-only retrieval, NOT a safe direct HTTP fetcher.

Direct fetches would additionally require connection pinning and redirect validation.
"""
import asyncio
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


class UnsafeURL(ValueError):
    pass


# Ad/click tracking parameters that never select page content (LIVE-01). Only
# these are removed; every other query parameter is kept in order.
_TRACKING_PARAMS = frozenset({"gclid", "gclsrc", "gbraid", "wbraid", "dclid", "fbclid", "msclkid", "ttclid",
                              "twclid", "yclid", "igshid", "li_fat_id", "mc_cid", "mc_eid", "srsltid", "_gl"})
_TRACKING_PREFIXES = ("utm_", "gad_")
_TRACKING_VALUES = {("source", "shoppingads")}


def _is_tracking(name: str, value: str) -> bool:
    key = name.lower()
    return (key in _TRACKING_PARAMS or key.startswith(_TRACKING_PREFIXES)
            or (key, value.lower()) in _TRACKING_VALUES)


def _content_query(query: str) -> list[tuple[str, str]]:
    return [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if not _is_tracking(k, v)]


def strip_tracking(value: str) -> str:
    """Return the public URL without ad-tracking query parameters."""
    url = public_url(value)
    parsed = urlsplit(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    kept = _content_query(parsed.query)
    if len(kept) == len(pairs):
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(kept), ""))


def same_page_key(value: str) -> tuple:
    """Identity of a page for matching provider results to requested URLs.

    Ignores scheme, a leading ``www.``, a trailing slash, percent-encoding
    differences, tracking parameters and query order. Host and path must match.
    """
    parsed = urlsplit(public_url(value))
    path = unquote(parsed.path).rstrip("/") or "/"
    return (parsed.hostname.removeprefix("www."), path, tuple(sorted(_content_query(parsed.query))))


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
