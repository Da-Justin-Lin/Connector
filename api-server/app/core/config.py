from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    snaptrade_client_id: str = ""
    snaptrade_consumer_key: str = ""
    snaptrade_user_id: str = ""
    snaptrade_user_secret: str = ""

    # Market data (Finnhub) — needed for per-symbol candle charts
    finnhub_api_key: str = ""

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/connector"

    secret_key: str = "changeme"
    algorithm: str = "HS256"
    # Short-lived access token; the frontend silently refreshes it via the
    # long-lived refresh-token cookie, so sessions still feel "remembered".
    access_token_expire_minutes: int = 30
    # Long-lived, revocable refresh token (stored hashed in the DB).
    refresh_token_expire_days: int = 30
    # Send the refresh cookie only over HTTPS. Keep False for local http dev;
    # set COOKIE_SECURE=true in production.
    cookie_secure: bool = False

    # Comma-separated list of allowed CORS origins
    allowed_origins: str = "http://localhost:3000"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Used to build the Google OAuth redirect URI and post-auth redirect
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
