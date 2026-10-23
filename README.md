# BikeHelper

Verwaltung für Rennrad, Gravel & Co.: Garage mit Komponenten, Kilometerzähler, Wartungsintervalle mit Warnungen.
Dazu Heatmap, Statistiken und Wetter pro Fahrt, das die Wartungsintervalle beeinflusst.

## Stand

- Login und Registrierung (mehrbenutzerfähig)
- Garage: Räder, Komponenten (Kette, Kassette, Reifen …), Kilometerstände
- Wartungsregeln (nach km und/oder Monaten), Wartungsprotokoll, Anzeige „Das steht an“
- Neue Räder bekommen Standardkomponenten mit Wartungsintervallen (siehe unten), die Nässe berücksichtigen
- Wetter pro Fahrt (Temperatur, Regen, Wind, Zeit auf nasser Straße) von Open-Meteo
- Heatmap aller Fahrten und Statistik mit Kachel-Erkundung wie bei Statshunters
- Fahrten-Import ohne Strava-Abo: Strava-Datenexport (ZIP) und GPX-/FIT-/TCX-Dateien, mit automatischer Zuordnung zu den Rädern

## Fahrten importieren

Die Strava-API verlangt seit 2026 ein Abo. BikeHelper kommt deshalb ohne sie aus und liest Dateien ein. Alles findet auf der Seite „Fahrten“ statt.

**Strava-Export (ganze Historie auf einmal)**
1. Auf strava.com unter Einstellungen, „Mein Konto“, „Dein Konto herunterladen“ den Download anfordern (die Menünamen können sich ändern). Strava schickt per E-Mail einen Link, das kann einige Stunden dauern.
2. Stelle die Sprache deines Strava-Kontos vor der Anforderung auf Englisch. Sonst werden die Fahrten zwar importiert, die Räder aber nicht automatisch zugeordnet.
3. Lade die ZIP-Datei auf der Seite „Fahrten“ hoch, ohne sie zu entpacken. Der Import läuft im Hintergrund, der Fortschritt wird angezeigt.

Aus dem Export werden nur Radfahrten übernommen. Kilometer, Zeit, Höhenmeter und Strecke berechnet BikeHelper aus den Aktivitätsdateien selbst. Bereits vorhandene Fahrten werden erkannt und übersprungen, ein erneuter Import ist also ungefährlich.

**Einzelne Dateien**: GPX, FIT und TCX (auch als `.gz`) lassen sich beliebig oft und gleich mehrfach hochladen und direkt einem Rad zuordnen. Reine Routen ohne Zeitstempel (zum Beispiel geplante Touren) werden abgelehnt.

Sehr große Exporte: Hinter dem Nginx Proxy Manager kann der Upload mit „413“ scheitern. Trage dann beim Proxy Host unter „Advanced“ die Zeile `client_max_body_size 8g;` ein.

## Wartungsintervalle und Nässe

Beim Anlegen eines Rades (oder über „Standardkomponenten ergänzen“) entstehen Komponenten mit Regeln, passend zum Radtyp. Alle Werte lassen sich je Regel ändern.

| Teil | Aufgabe | Intervall | Nässefaktor |
|---|---|---|---|
| Kette | reinigen und schmieren | 200 km | 2,0 |
| Kette | wechseln (Kettenlehre) | 3.000 km | 2,0 |
| Kassette | wechseln | 9.000 km | 1,5 |
| Kettenblätter | wechseln | 20.000 km | 1,5 |
| Reifen vorn / hinten | wechseln | 6.000 / 4.000 km | – |
| Bremsbeläge | prüfen / wechseln | 500 / 1.500 km | 2,0 |
| Bremsflüssigkeit | wechseln | 12 Monate | – |
| Züge | erneuern | 5.000 km oder 12 Monate | 1,3 |
| Lenkerband | erneuern | 12 Monate | – |
| Dichtmilch (Tubeless) | auffüllen / erneuern | 4 / 15 Monate | – |
| Steuersatz, Tretlager, Naben | warten | 5.000 km oder 12 Monate | 1,5 |

**Wie Nässe zählt:** Ein Kilometer bei Nässe zählt wie *Nässefaktor* Kilometer. Eine Fahrt gilt für die Zeit als nass, in der es regnete oder die Straße noch feucht war (mindestens 0,1 mm in der Stunde oder 0,5 mm in den zwei Stunden davor). Der Anteil nasser Fahrzeit wird auf die Strecke der Fahrt umgelegt.

**Wie belastbar die Zahlen sind:** Für die Kette gibt es einen Labortest eines Schmierstoffherstellers (nass etwa 1,5-fach, sehr nass etwa 2,3-fach Verschleiß). Die Intervalle der übrigen Teile sind Richtwerte aus Werkstatt-Ratgebern und Herstellerangaben und streuen stark; die übrigen Nässefaktoren sind begründete Schätzungen. Wer es genauer weiß, ändert sie an der Regel. Die Kettenlehre schlägt jede Rechnung.

Teile ohne Einbaudatum (zum Beispiel aus dem Standardsatz) zeigen „Einbaudatum fehlt“, bis du ein Datum einträgst oder eine Regel als erledigt abhakst. Erst dann kann gezählt werden. Mit „Teil gewechselt“ wird das alte Teil ausgemustert und das neue übernimmt alle Regeln.

Quellen: Park Tool (Kettenverschleiß), BikeGremlin, Slowtwitch, Zero Friction Cycling, Geekay, BikeRadar, Lennard Zinn, CX Magazine, Michelin sowie Herstellerangaben von SRAM, Shimano und TRP.

## Wetter

Nach jedem Import holt BikeHelper im Hintergrund das Wetter zu den Fahrten von [Open-Meteo](https://open-meteo.com) (Daten unter CC BY 4.0, kostenlos, ohne Schlüssel). Alle sechs Stunden wird nach neuen Fahrten gesucht; Fahrten der letzten Tage werden vorläufig ausgewertet und später aus dem Archiv korrigiert.

**Datenschutz:** Gesendet werden nur gerundete Startkoordinaten (0,1 Grad, rund 10 km) und Zeiträume, keine Namen oder Konten. Wer das nicht möchte, setzt `WEATHER_ENABLED=false` in der `.env`; dann gibt es kein Wetter und keine Nässe-Korrektur.

## Heatmap und Statistik

- **Heatmap:** alle Strecken auf dunkler Karte, oft gefahrene Wege leuchten heller. Filter nach Jahr und Rad, optional mit den erkundeten Kacheln und dem größten Quadrat. Kartendaten: OpenStreetMap-Mitwirkende, CARTO. Die Kartenkacheln lädt der Browser von carto.com.
- **Statistik:** Kennzahlen, Jahre und Monate, Kalender der Fahrtage, Wochentage, Startzeiten, Fahrtlängen, Rekorde, Serien, Räder, Temperatur und Nässe.
- **Kacheln:** Zoomstufe 14 (rund 1,5 km). Das größte Quadrat zählt nur vollständig erkundete Kacheln; ein „Gebiet“ umfasst auch diagonal verbundene Kacheln. Das kann von Statshunters leicht abweichen.
- Zeiten werden in der Zeitzone `TIMEZONE` ausgewertet (Standard `Europe/Berlin`).

## Schnellinstallation

Auf einer frischen Debian-/Ubuntu-Maschine (VM oder LXC auf Proxmox), per SSH als normaler Benutzer mit sudo oder als root:

```bash
curl -fsSL https://raw.githubusercontent.com/Tillhnz/Bikehelper/main/install.sh | bash
```

Das Skript installiert bei Bedarf Git und Docker, erzeugt die Passwörter, schreibt die `.env` und startet BikeHelper.
Wer vorher nachlesen möchte, was es tut, klont das Repository und startet `./install.sh` selbst.

Weitere Befehle im Projektordner:

| Befehl | Wirkung |
| --- | --- |
| `./install.sh update` | Neueste Version holen und neu starten |
| `./install.sh lock` / `unlock` | Neue Registrierungen sperren / erlauben |
| `./install.sh url https://bike.example.de` | Öffentliche Adresse ändern |
| `./install.sh logs` | Protokolle anzeigen |

## Manuell starten (Docker)

Auf dem Server muss Docker mit Compose installiert sein.

```bash
cp .env.example .env
# .env anpassen: POSTGRES_PASSWORD, SECRET_KEY (openssl rand -hex 32), PUBLIC_URL
docker compose up -d --build
```

Die Seite läuft danach auf `http://<server-ip>:8080` (Port über `WEB_PORT` änderbar).

## Reverse Proxy (Nginx Proxy Manager)

Neuer Proxy Host: Domain deiner Wahl, Forward auf `<server-ip>` Port `8080` (Schema http),
SSL-Zertifikat über Let's Encrypt, „Force SSL“ und „Websockets Support“ aktivieren.
Trage dieselbe Adresse (mit `https://`) als `PUBLIC_URL` in der `.env` ein.

Nach dem Anlegen deines Kontos `ALLOW_REGISTRATION=false` setzen und `docker compose up -d`,
damit sich niemand Fremdes registrieren kann. Das erste Konto ist immer erlaubt.

## Entwicklung ohne Docker

```bash
# Backend (SQLite, ohne PostgreSQL)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests          # Ende-zu-Ende-Test der API
uvicorn app.main:app --reload   # http://localhost:8000

# Frontend (zweites Terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173, /api wird ans Backend weitergereicht
```

## Backup

Die Daten liegen im Docker-Volume `db_data`. Sicherung der Datenbank:

```bash
docker compose exec db pg_dump -U bikehelper bikehelper > backup.sql
```

Zusätzlich lohnt sich ein regelmäßiges Proxmox-Backup der VM bzw. des LXC.

## Struktur

```
backend/    FastAPI, SQLAlchemy, Auth (JWT), Garage-API, Tests
frontend/   React + Vite, nginx als Auslieferung und /api-Proxy
```
