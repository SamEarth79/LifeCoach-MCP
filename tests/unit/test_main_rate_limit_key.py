from unittest.mock import MagicMock

from app.config import get_settings
from app.main import get_client_ip


def _request_with(headers: dict, client_host: str = "10.0.0.1") -> MagicMock:
    request = MagicMock()
    request.headers = headers
    request.client.host = client_host
    return request


def test_uses_remote_address_when_no_forwarded_header():
    request = _request_with({}, client_host="203.0.113.5")

    assert get_client_ip(request) == "203.0.113.5"


def test_trusts_the_single_hop_appended_by_our_proxy():
    # One trusted proxy (default), header has exactly the hop it appended.
    request = _request_with({"X-Forwarded-For": "198.51.100.7"})

    assert get_client_ip(request) == "198.51.100.7"


def test_resists_client_spoofing_a_fake_leading_entry():
    # A client that sends its own X-Forwarded-For value, with our trusted
    # proxy appending the real connecting address afterward, must resolve
    # to the proxy-appended entry, not the client-supplied one.
    request = _request_with({"X-Forwarded-For": "1.2.3.4, 198.51.100.7"})

    assert get_client_ip(request) == "198.51.100.7"


def test_falls_back_to_remote_address_when_fewer_hops_than_trusted_proxies(
    monkeypatch,
):
    get_settings.cache_clear()
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    get_settings.cache_clear()

    import app.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module, "settings", get_settings())

    request = _request_with({"X-Forwarded-For": "198.51.100.7"}, client_host="10.0.0.1")

    assert rate_limit_module.get_client_ip(request) == "10.0.0.1"

    get_settings.cache_clear()
