from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./bikehelper.db"
    secret_key: str = "dev-secret-change-me"
    public_url: str = "http://localhost:8080"
    allow_registration: bool = False  # nur der erste Nutzer und Eingeladene dürfen sich registrieren
    trusted_proxies: int = 1  # Proxys vor dem Webserver (Nginx Proxy Manager = 1), für die Login-Drosselung
    token_expire_days: int = 7
    frame_ancestors: str = ""  # Adressen, die BikeHelper einbetten dürfen (z. B. Home Assistant), mit Leerzeichen getrennt
    updater_url: str = ""  # leer = kein Update-Dienst
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

    # intervals.icu: Fahrten (auch von Garmin, Zwift, Polar …) mit dem persönlichen API-Schlüssel abholen
    intervals_enabled: bool = True
    intervals_api_url: str = "https://intervals.icu"

    class Config:
        env_file = ".env"
        extra = "ignore"  # alte Einträge (zum Beispiel WAHOO_ENABLED) stören den Start nicht


settings = Settings()
