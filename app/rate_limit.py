from limits import parse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings

settings = get_settings()
per_ip_rate_limit = f"{settings.rate_limit_requests}/{settings.rate_limit_window_seconds}second"


def get_client_ip(request: Request) -> str:
    """Resolve the client IP for rate limiting.

    The app runs behind the PaaS host's reverse proxy, so the raw TCP peer
    (`request.client.host`) is the proxy, not the client — every request
    would otherwise collapse into a single shared rate-limit bucket.

    The leftmost `X-Forwarded-For` entry is client-supplied and can be
    spoofed (a proxy that appends rather than overwrites would let a
    client inject its own value ahead of the real chain). Only the
    rightmost `trusted_proxy_hops` entries are appended by infrastructure
    we trust; the client IP is the one just before those, which cannot be
    forged because it's appended by our own trusted proxy, not the client.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
        trusted_index = len(hops) - settings.trusted_proxy_hops
        if 0 <= trusted_index < len(hops):
            return hops[trusted_index]
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip, default_limits=[per_ip_rate_limit])
_mcp_rate_limit_item = parse(per_ip_rate_limit)


class McpRateLimitExceeded(Exception):
    """Raised when an MCP tool call exceeds the per-IP rate limit."""


async def enforce_mcp_rate_limit(request: Request | None, user_id: str | None = None) -> None:
    """Rate-limit an MCP tool call, keyed by client IP, same window as REST.

    MCP tool handlers aren't FastAPI routes, so they can't use
    `@limiter.limit`/the `enforce_rate_limit` dependency, which both rely on
    Starlette's routing/dependency machinery to find the matching route's
    limit and attach state to the response. The underlying `limits`-package
    rate limiter that backs `Limiter` (`limiter.limiter`) has no such
    requirement — it only needs a key — so it's called directly here,
    against the same per-IP rate limit item the REST endpoints use, keyed
    by the same client-IP resolution.

    Called before JWT verification (matching the REST pattern's
    cheap-checks-first ordering, where `enforce_rate_limit` is declared
    ahead of `get_current_user`), so `user_id` is not yet known in the
    normal case and is keyed by IP instead. Falls back to keying on
    `user_id` only if no real HTTP request is available (should not
    happen in production, since the MCP SDK only invokes tools with a
    live request attached); if neither is available, fails loudly rather
    than silently skipping the limit.
    """
    if request is not None:
        key = get_client_ip(request)
    elif user_id is not None:
        key = user_id
    else:
        raise McpRateLimitExceeded("Rate limit cannot be enforced: no request or user id")

    if not limiter.limiter.hit(_mcp_rate_limit_item, key):
        raise McpRateLimitExceeded(f"Rate limit exceeded: {per_ip_rate_limit}")
