from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./bikehelper.db"
    secret_key: str = "dev-secret-change-me"
    public_url: str = "http://localhost:8080"
    allow_registration: bool = True
    token_expire_days: int = 30
    weather_enabled: bool = True
    timezone: str = "Europe/Berlin"

    class Config:
        env_file = ".env"


settings = Settings()
