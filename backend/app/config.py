from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./bikehelper.db"
    secret_key: str = "dev-secret-change-me"
    public_url: str = "http://localhost:8080"
    allow_registration: bool = True
    token_expire_days: int = 30
    weather_enabled: bool = True
    timezone: str = "Europe/Berlin"
    # Kartenhintergrund: kostenloser CARTO-Schlüssel (dunkle Karte) oder eigene Kachel-URL; ohne beides OpenStreetMap
    carto_api_key: str = ""
    map_tile_url: str = ""
    map_tile_dark: bool = True

    # Erinnerungen per E-Mail (eigener SMTP-Server) und per ntfy (Push aufs Handy, https://ntfy.sh)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    ntfy_server: str = "https://ntfy.sh"
    reminders_enabled: bool = True
    # Orte und Länder: Städte werden einmalig bei OpenStreetMap (Nominatim) nachgeschlagen und gespeichert
    geo_enabled: bool = True
    nominatim_url: str = "https://nominatim.openstreetmap.org"

    class Config:
        env_file = ".env"


settings = Settings()
