import asyncio
import socket

import pytest

from app.research.url_safety import UnsafeURL, public_url, validate_public_destination


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/x", "http://127.0.0.1", "http://169.254.169.254", "http://[::1]", "http://[::ffff:8.8.8.8]", "http://2130706433", "http://127.1", "http://0x7f000001", "https://user:pass@shop.com", "http://a.internal", "https://shop.com:8080", "https://shop.com\\@evil.com", "https://shop.com/%20\n"])
def test_reject_unsafe(url):
    with pytest.raises(UnsafeURL):
        public_url(url)


def test_normalize_public():
    assert public_url("https://SHOP.COM/path#fragment") == "https://shop.com/path"


def test_mixed_dns_and_resolution_error_fail_closed():
    async def mixed(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]
    async def unavailable(*args, **kwargs):
        raise OSError("offline")
    for resolver in (mixed, unavailable):
        with pytest.raises(UnsafeURL):
            asyncio.run(validate_public_destination("https://shop.com", resolver))
