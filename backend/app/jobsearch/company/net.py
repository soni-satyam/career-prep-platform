"""Outbound fetching with SSRF protection.

Every URL we fetch here comes from user input or from a remote page (career links, job links), so
it is checked before each request, including every redirect hop: http(s) only, standard ports only
and the host must resolve to public addresses only (no localhost, private ranges, link-local /
cloud-metadata addresses).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

MAX_CHARS = 1_500_000
_REDIRECTS = {301, 302, 303, 307, 308}

_resolve = socket.getaddrinfo   # replaced in tests


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    return addr.is_global and not addr.is_multicast


async def is_public_url(url: str) -> bool:
    p = urlparse(url or "")
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    if p.port not in (None, 80, 443):
        return False
    host = p.hostname.lower()
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal", ".lan", ".home")):
        return False
    try:
        ipaddress.ip_address(host)
        return _ip_is_public(host)
    except ValueError:
        pass
    try:
        infos = await asyncio.to_thread(_resolve, host, None)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(_ip_is_public(a) for a in addrs)


async def safe_get(client: Any, url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None,
                   max_redirects: int = 4) -> Optional[Any]:
    """GET with manual, validated redirects. Returns None when the URL is not allowed or too many hops."""
    cur = url
    for hop in range(max_redirects + 1):
        if not await is_public_url(cur):
            return None
        r = await client.get(cur, headers=headers, params=params if hop == 0 else None, follow_redirects=False)
        if r.status_code in _REDIRECTS:
            loc = r.headers.get("location")
            if not loc:
                return r
            cur = urljoin(cur, loc)
            continue
        return r
    return None


def text_of(r: Any) -> str:
    """Response body as text, capped. Empty for non-text content types."""
    ct = (r.headers.get("content-type") or "").lower()
    if ct and not any(t in ct for t in ("html", "json", "xml", "text")):
        return ""
    return (r.text or "")[:MAX_CHARS]
