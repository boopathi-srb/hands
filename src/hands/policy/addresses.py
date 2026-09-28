"""Parsing of web addresses and entry points into the parts a policy judges: origin and path.

Parsing is strict and exception free: anything that is not a plain http(s) URL with a well-formed host and
port yields None, which the gate treats as "not allowlisted".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

WEB_SCHEMES = ("http", "https")
DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_PORT = 65_535
_HOST_PORT = re.compile(r"^(?P<host>\[[0-9A-Fa-f:.]+\]|[^:\[\]/@]+)(?::(?P<port>\d{1,5}))?$")


@dataclass(frozen=True)
class WebAddress:
    """An http(s) URL reduced to what the policy needs."""

    origin: str
    path: str


def looks_like_url(entry_point: str) -> bool:
    """Entry points containing '://' are URLs; everything else is a desktop bundle id."""
    return "://" in entry_point


def parse_web_address(url: str) -> WebAddress | None:
    """Split an http(s) URL into a normalized origin and its raw path, or None if it is not one."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in WEB_SCHEMES or "@" in parts.netloc:
        return None
    origin = _normalized_origin(scheme, parts.netloc)
    if origin is None:
        return None
    return WebAddress(origin=origin, path=parts.path or "/")


def normalize_origin(origin: str) -> str | None:
    """Normalize a configured origin such as 'http://127.0.0.1:8700'. None when it is not a bare origin."""
    parts = urlsplit(origin.strip())
    scheme = parts.scheme.lower()
    has_extra_parts = parts.path not in ("", "/") or bool(parts.query) or bool(parts.fragment)
    if scheme not in WEB_SCHEMES or has_extra_parts or "@" in parts.netloc:
        return None
    return _normalized_origin(scheme, parts.netloc)


def _normalized_origin(scheme: str, netloc: str) -> str | None:
    host_port = _HOST_PORT.match(netloc)
    if host_port is None:
        return None
    host = host_port.group("host").lower()
    port_text = host_port.group("port")
    port = int(port_text) if port_text else DEFAULT_PORTS[scheme]
    if not 0 < port <= MAX_PORT:
        return None
    return f"{scheme}://{host}:{port}"
