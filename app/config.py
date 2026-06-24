from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    database_url: str
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    trusted_proxy_hops: int = 1
    mcp_allowed_hosts: str = "localhost:8001,127.0.0.1:8001"
    mcp_allowed_origins: str = "http://localhost:8001,http://127.0.0.1:8001"

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]

    @property
    def mcp_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.mcp_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
