from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"

    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/connector"

    secret_key: str = "changeme"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Comma-separated list of allowed CORS origins
    allowed_origins: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
