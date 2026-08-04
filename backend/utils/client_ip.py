"""Deriving a caller's IP when a reverse proxy may be in front of us.

``X-Forwarded-For`` is a *request header*: it is written by whoever
opened the connection. Believing it unconditionally means believing a
value the caller chose, which is fine for a request that genuinely came
through our proxy and worthless for one that did not.

That distinction matters here because the derived IP is a **rate-limit
key**. Production publishes the app port directly (``8002:8000``), so a
client that reaches the container without going through Caddy can send a
different fake first hop on every request and get a fresh 60-second
window each time — the limiter still counts, it just never counts the
same caller twice.

The fix is the standard one: only believe the header when the
*connection itself* comes from a proxy we run. ``TRUSTED_PROXY_CIDRS``
lists those peers; anything else is keyed by the address it actually
connected from, which it cannot forge over TCP.

Two deliberate choices:

* **The default trusts loopback and the private ranges**, because that
  is where Caddy and the Docker bridge sit. It keeps existing
  deployments working with no config change while still refusing the
  header from a public-internet peer — the case the attack needs. An
  operator who knows the exact proxy address should narrow it.
* **An unparseable entry is skipped with a warning, not fatal.** A typo
  in one CIDR degrades that entry to "not trusted" — the safe
  direction — instead of taking the process down at import time.

This is edge code: it reads settings, so it belongs to routers and
middleware. A service must not call it.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

from fastapi import Request

from backend.config import get_settings

logger = logging.getLogger(__name__)

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# Used when there is no peer address at all — an ASGI scope without a
# client, which happens in some test transports. A constant rather than
# ``None`` so callers can key a dict with it unchanged.
UNKNOWN_IP = "unknown"


@lru_cache(maxsize=8)
def _parse_cidrs(raw: str) -> tuple[_Network, ...]:
    """Parse the comma-separated setting once per distinct value.

    Cached on the raw string rather than read from settings inside, so a
    test that swaps the setting gets a fresh parse instead of a stale
    hit.
    """
    networks: list[_Network] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            networks.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            logger.warning("trusted_proxy_cidrs: ignoring unparseable entry %r", chunk)
    return tuple(networks)


def is_trusted_proxy(peer: str, trusted_cidrs: str) -> bool:
    """Whether ``peer`` is allowed to speak for someone else."""
    networks = _parse_cidrs(trusted_cidrs)
    if not networks:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        # A hostname or a mangled value — not something we can place
        # inside a network, so not something we trust.
        return False
    return any(address in network for network in networks)


def derive_client_ip(
    peer: str | None, forwarded_for: str | None, trusted_cidrs: str
) -> str:
    """Pure core: the caller's address given the three inputs.

    Separated from the request so the trust rule can be tested without a
    transport, and so both the header-present and header-absent paths
    return the same thing for an untrusted peer.
    """
    if peer is None:
        return UNKNOWN_IP
    if not forwarded_for or not is_trusted_proxy(peer, trusted_cidrs):
        return peer
    # Left-most hop is the original client. Everything after it was
    # appended by intermediaries and is equally unverifiable, so taking
    # the first is neither better nor worse — it is the convention the
    # proxy in front of us follows.
    first_hop = forwarded_for.split(",", 1)[0].strip()
    return first_hop or peer


def client_ip(request: Request) -> str:
    """The caller's address, trusting ``X-Forwarded-For`` only from a
    configured proxy peer."""
    return derive_client_ip(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        get_settings().trusted_proxy_cidrs,
    )
