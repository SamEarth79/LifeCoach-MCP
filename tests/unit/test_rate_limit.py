from types import SimpleNamespace

import pytest

from app import rate_limit

# `app.rate_limit` is reloaded via `importlib.reload` by
# tests/feature/test_rate_limit.py to exercise env-driven settings. A
# `from app.rate_limit import McpRateLimitExceeded` binding taken at this
# module's collection time would go stale after such a reload (the reloaded
# module defines a *new* exception class object), so the class and the
# function under test are both looked up through the `rate_limit` module
# reference at call time instead, the same way that test file already
# re-fetches `app.main`/`app.rate_limit` attributes off the module rather
# than off a stale direct import.


def _request_with_ip(ip: str) -> SimpleNamespace:
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


@pytest.mark.asyncio
async def test_enforce_mcp_rate_limit_allows_requests_within_the_configured_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "per_ip_rate_limit", "2/60second")
    monkeypatch.setattr(rate_limit, "_mcp_rate_limit_item", rate_limit.parse("2/60second"))
    rate_limit.limiter.reset()

    request = _request_with_ip("203.0.113.9")

    await rate_limit.enforce_mcp_rate_limit(request, "user-1")
    await rate_limit.enforce_mcp_rate_limit(request, "user-1")

    rate_limit.limiter.reset()


@pytest.mark.asyncio
async def test_enforce_mcp_rate_limit_rejects_request_exceeding_the_configured_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "per_ip_rate_limit", "1/60second")
    monkeypatch.setattr(rate_limit, "_mcp_rate_limit_item", rate_limit.parse("1/60second"))
    rate_limit.limiter.reset()

    request = _request_with_ip("203.0.113.10")

    await rate_limit.enforce_mcp_rate_limit(request, "user-1")
    with pytest.raises(rate_limit.McpRateLimitExceeded):
        await rate_limit.enforce_mcp_rate_limit(request, "user-1")

    rate_limit.limiter.reset()


@pytest.mark.asyncio
async def test_enforce_mcp_rate_limit_keys_by_client_ip_not_user_id(monkeypatch):
    monkeypatch.setattr(rate_limit, "per_ip_rate_limit", "1/60second")
    monkeypatch.setattr(rate_limit, "_mcp_rate_limit_item", rate_limit.parse("1/60second"))
    rate_limit.limiter.reset()

    request = _request_with_ip("203.0.113.11")

    await rate_limit.enforce_mcp_rate_limit(request, "user-a")
    with pytest.raises(rate_limit.McpRateLimitExceeded):
        await rate_limit.enforce_mcp_rate_limit(request, "user-b")

    rate_limit.limiter.reset()


@pytest.mark.asyncio
async def test_enforce_mcp_rate_limit_falls_back_to_user_id_key_when_no_request(monkeypatch):
    monkeypatch.setattr(rate_limit, "per_ip_rate_limit", "1/60second")
    monkeypatch.setattr(rate_limit, "_mcp_rate_limit_item", rate_limit.parse("1/60second"))
    rate_limit.limiter.reset()

    await rate_limit.enforce_mcp_rate_limit(None, "user-without-request")
    with pytest.raises(rate_limit.McpRateLimitExceeded):
        await rate_limit.enforce_mcp_rate_limit(None, "user-without-request")

    rate_limit.limiter.reset()
