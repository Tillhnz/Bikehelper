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

## Ratgeber

Die Seite „Ratgeber“ beantwortet für die nächste Tour zwei Fragen. Du wählst Rad, Start (vorbelegt mit jetzt), Dauer, Durchschnittsgeschwindigkeit und Ort. Reifenbreite, Radgewicht und Felge kommen aus der Garage (montierter Reifensatz und Radangaben), der Untergrund ist je Radtyp vorbelegt (Rennrad Asphalt, Gravel fester Schotter). Das Wetter kommt aus der 15-Tage-Vorhersage von Open-Meteo (nur gerundeter Ort und Zeit werden gesendet) oder von Hand.

Die Oberfläche arbeitet mit Reglern und Bildkarten: Du wählst dein Rad (oder einen Radtyp) als Zeichnung, stellst Reifenbreite, Untergrund, Start, Dauer, Tempo und Gewicht per Schieberegler ein, und Reifendruck, Kleidung und Wetter passen sich sofort an. Die Garage zeigt jedes Rad als schlichte Strichzeichnung je nach Typ (Rennrad, Gravel, Mountainbike, Sonstiges). Bewegung (Zeichnen, rollender Kilometerzähler, Messuhren) wird abgeschaltet, wenn dein System „Bewegung reduzieren“ eingestellt hat.

**Reifendruck** aus Gewicht, Reifenbreite und Untergrund:
- Grundformel nach Frank Bertos 15-%-Regel, als Formel gefasst von BikeLab: `P = 600 · L / W² + 0,75 · W − 25` (psi, L Last pro Rad in lb, W echte Reifenbreite in mm), laut Quelle auf etwa ±2 psi genau. Hinten wird direkt gerechnet, vorn sind es 93 %. Das Hinterrad trägt bei Rennrädern 60 %, bei Gravel und MTB 55 % des Systemgewichts.
- Zu- und Abschläge: Untergrund (fester Schotter −9 %, lockerer −17,5 %, grober −33 %, rauer Asphalt −5 %, nach SILCA und BikeLab), Schlauch +5 %, weiche Karkasse −5 %, steife +5 %, feuchte Straße −5 %, nasse −10 % (Continental nennt rund 10 % weniger bei Regen).
- Hookless-Felgen werden auf 5,0 bar begrenzt (bei Innenweite ab 30 mm auf 4,1 bar). Es gilt immer der Maximaldruck, der auf Reifen und Felge steht.
- Das ist ein Startwert. Verglichen mit dem SILCA-Rechner liegt die Formel bei 80 kg und 30 mm etwa 8 % darunter; sie liefert für 10 kg mehr Fahrergewicht rund 9 psi mehr. Für MTB-Reifen ist es nur eine grobe Näherung.

**Kleidung** („kurz-kurz“ bis „lang-lang“):
- Aus Temperatur zu Beginn und im Mittel entsteht eine gefühlte Kleidungstemperatur. Zusätzlich zählen echter Wind (Windchill-Formel von Environment Canada, nur über den normalen Fahrtwind hinaus), Regen (eine Stufe wärmer), Tempo (hart: etwa 3 °C weniger, locker: 2 °C mehr), Kälteempfinden (±2 °C), Dauer (unter 1 Std. etwas wärmer, ab 4 Std. mehr Reserve).
- Stufen: ab 24 °C kurz/kurz mit Sonnenschutz, 20 bis 24 kurz/kurz, 16 bis 20 kurz mit Armlingen, 12 bis 16 lang mit Beinlingen und dünnen Handschuhen, 8 bis 12 lang/lang mit Überschuhen, 4 bis 8 Thermo und winddichte Jacke, 0 bis 4 Winterausrüstung, darunter zusätzlich Zehenwärmer und Sturmhaube. Die Grenzen sind das Mittel aus den Tabellen von Roadman, Löffler und Down The Road.
- Dazu kommen Regen- und Windkleidung, Sonnenschutz, Mitnehmen (Weste für die Abfahrt, Notfall-Schicht ab 3 Std., Armlinge zum Ausziehen bei starkem Temperaturanstieg), Licht bei Dunkelheit sowie Warnungen bei Frost oder Glatteis. Zu- und Abschläge sind eigene Annahmen und Geschmackssache.

Quellen: BikeLab PSI Calculator, SILCA-Rechner, Lebel Bicycles, Lennard Zinn (Active.com) und Velo (Reifendruck bei Nässe); Roadman Cycling, Löffler, Down The Road (Kleidung); Cyclowax, bike-components, Componentry, CyclingCeramic (Kettenwachs).

## Uploads im Hintergrund

Uploads und Importe laufen weiter, wenn du die Seite oder den Tab wechselst. Der Fortschritt steht auf jeder Seite oben in einer Meldung, im Tab-Titel, und am Ende kommt eine Meldung („Import abgeschlossen“). Beim ersten Upload fragt der Browser, ob BikeHelper Benachrichtigungen senden darf; ist der Tab dann im Hintergrund, erscheint eine Systembenachrichtigung. Die Verarbeitung der ZIP läuft auf dem Server und übersteht auch ein Neuladen. Nur das Hochladen selbst bricht ab, wenn du den Tab schließt oder neu lädst (der Browser warnt davor), und auf dem Handy kann ein gesperrter Bildschirm den Upload anhalten.

## Einzelauswertung und Neuimport

- Ein Klick auf eine Fahrt öffnet die Einzelauswertung: Karte mit Start und Ziel, Kennzahlen (Strecke, Zeiten, Tempo, Höhenmeter, Puls, Trittfrequenz, Leistung, soweit aufgezeichnet), Verlaufsdiagramme und das Wetter. Fährst du mit der Maus über ein Diagramm, wandert ein Punkt über die Karte.
- Verlaufsdaten werden beim Import gespeichert. Fahrten, die früher importiert wurden, haben sie nicht. Es genügt, denselben Export noch einmal hochzuladen: Vorhandene Fahrten werden ergänzt (Verlauf, Rad), nicht doppelt angelegt.
- Unter „Fahrten“ gibt es ganz unten „Alle Fahrten löschen“ (mit Bestätigung durch Eintippen). Räder, Komponenten und Wartungseinträge bleiben dabei erhalten.

## Kartenhintergrund

CARTO zeigt seine Karten nur noch mit einem Schlüssel ohne Wasserzeichen „API KEY REQUIRED“. Der Schlüssel ist kostenlos, braucht kein Konto und gilt für private Projekte bis 5 Millionen Kartenabrufe im Monat: <https://carto.com/basemaps/apikey/>

- **Mit Schlüssel (einfach):** Als Administrator in der Administration im Bereich „Karten“ einfügen. Er gilt für alle Nutzer, normale Nutzer sehen dazu keine Einstellung. Dann erscheint die dunkle Karte.
- **Alternativ:** `CARTO_API_KEY=…` in die `.env` eintragen und `./install.sh update` ausführen.
- **Ohne Schlüssel:** BikeHelper nimmt die helle OpenStreetMap-Karte. Für private Nutzung in kleinem Umfang ist das in Ordnung (Nutzungsregeln: <https://operations.osmfoundation.org/policies/tiles/>), für viele Nutzer nicht.
- **Eigener Anbieter:** `MAP_TILE_URL` (mit `{z}/{x}/{y}`) und `MAP_TILE_DARK=false` für helle Karten setzen.

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

**Kettenschmierung:** Am Rad wählst du nur Öl oder Wachs. Welche Art Wachs du benutzt hast, trägst du bei jeder Wartung der Kette ein (Heißwachs im Tauchbad oder flüssiges Tropfwachs). Davon hängt das Intervall ab:

| Schmierung | Schmieren bzw. neu wachsen | Nässefaktor | Kette wechseln |
|---|---|---|---|
| Öl | 200 km | 2,0 | 3.000 km |
| Wachs, heiß | 500 km | 2,5 | 5.000 km |
| Wachs, flüssig | 250 km | 2,5 | 5.000 km |

Die Quellen nennen für Heißwachs 300 bis 600 km (BikeRadar, SILCA, CyclingCeramic), für Tropfwachs 200 bis 400 km und raten, nach jeder Nassfahrt früher neu zu wachsen, weil Regen das Wachs abwäscht. Bei Dauerregen und Streusalz sei Öl besser. Zur Lebensdauer gibt es nur Herstellerangaben („bis zu dreimal so lang“, Cyclowax); unabhängige Messungen habe ich nicht gefunden. Deshalb rechnet BikeHelper vorsichtig mit gut dem Anderthalbfachen. Ein Wechsel der Schmierung stellt die Regeln um, Wartungseinträge bleiben erhalten.

**Reifen:** Auf der Seite eines Rades legst du jeden Reifensatz (Mäntel) an und wählst, welcher montiert ist. Die Fahrten des Rades zählen ab dem Montagetag automatisch auf den montierten Satz, bis du einen anderen montierst. So siehst du die Kilometer je Satz, auch wenn du Sätze wechselst und später wieder aufziehst. Zeiträume lassen sich nachtragen, ändern und löschen. Breite und Tubeless-Angabe des montierten Satzes übernimmt das Rad für den Ratgeber. Optional trägst du eine erwartete Lebensdauer ein, dann zeigt eine Anzeige den Verbrauch.

**Daten wieder entfernen:** Einbaudaten lassen sich ändern oder entfernen, Wartungseinträge einzeln löschen (im Wartungsverlauf der Komponente), ausgemusterte Teile wieder einbauen.

### Prüfergebnis bei Bremsbelägen

Beim Eintragen von „Belagstärke prüfen“ wählst du das Ergebnis und die App passt die Intervalle an:

- **Gut:** Die Beläge gelten zum Prüfzeitpunkt höchstens zur Hälfte verbraucht. Das Wechselintervall verlängert sich entsprechend, die nächste Prüfung kommt nach dem normalen Intervall.
- **Beobachtung:** Die Beläge gelten mindestens zu 80 % verbraucht („bald fällig“), die nächste Prüfung kommt nach 40 % des normalen Intervalls (200 statt 500 km).
- **Wechseln:** „Bremsbeläge wechseln“ ist sofort fällig.

Die Werte 50 %, 80 % und 40 % sind Schätzungen (`GOOD_MAX_RATIO`, `WATCH_MIN_RATIO`, `WATCH_RECHECK_FACTOR` in `services.py`). Nach dem Eintrag „Bremsbeläge wechseln“ zählt das alte Ergebnis nicht mehr.

### Sichtprüfung jeder Komponente

In jeder Komponente (Garage, Rad öffnen) gibt es unter der Anleitung „Sichtprüfung eintragen“ mit drei Ergebnissen:

- **Völlig okay:** Das Intervall startet am Prüftag neu, Kilometer und Monate zählen ab dann von null.
- **Im Auge behalten:** Das Intervall startet ebenfalls neu, wird aber halbiert (Kilometer und Monate). Bei einer Kette mit 5000 km Intervall wird sie nach 2500 km wieder fällig.
- **Schlecht, austauschen:** Die Wechselregel („… wechseln“, „… erneuern“) ist sofort fällig, bis ein neuerer Wartungseintrag existiert.

Die Sichtprüfung wirkt auf die Wechselregeln der Komponente, nicht auf Schmierregeln, Flüssigkeiten oder Dichtmilch. Eine Prüfung mit „okay“ oder „im Auge behalten“ ersetzt ältere Kettenverschleiß-Messungen. Bremsbeläge behalten ihre eigene Prüfregel (siehe oben). Die Prüfung steht im Wartungsverlauf und lässt sich dort löschen. Den Faktor 0,5 legt `VISUAL_WATCH_FACTOR` in `services.py` fest.

## Startseite, Inventar, Anleitungen und Orte

- **Startseite:** Kilometer der Woche je Tag mit Vergleich zur Vorwoche (mit „‹ Zurück“ blätterst du durch frühere Wochen, ein Tipp auf einen Tag öffnet dessen Fahrten), die wichtigsten Wartungen mit Knopf „Erledigt“, deine Räder, deine Jahresziele mit nötigem Pensum pro Woche und die letzten Fahrten. Auf der Seite einer Fahrt steht, was am Rad zu tun ist, und lässt sich direkt abhaken.
- **Nasse Fahrt:** Nach einer Fahrt mit mindestens 5 Minuten Regen oder nasser Straße (laut Wetterdaten) erscheint auf der Startseite ein Hinweis zur Kette. Er verschwindet 4 Stunden nach dem Ende der Fahrt, mit „Verstanden“ oder sobald du die Kette gepflegt einträgst. Bei Öl heißt es abwischen und bei Bedarf neu schmieren, bei Wachs abwischen und trocknen lassen, neu wachsen nur bei Dreck, Rost oder sehr nasser Fahrt. Das Wetter für eine Fahrt kommt erst nach dem Hochladen und kann einen Moment dauern.
- **Suche:** Der Knopf „Suche“ oder die Taste `/` durchsucht Fahrten, Räder, Teile und Lager.
- **Einkaufsliste** (Garage): Was bald oder jetzt gewechselt werden muss, abgeglichen mit dem Lager, zum Kopieren oder Drucken.
- **Darstellung** (Einstellungen): Automatisch, Hell oder Dunkel. **Meine Daten:** Export aller eigenen Daten als JSON.
- **Passwort vergessen:** Ist der E-Mail-Versand eingerichtet, erscheint auf der Anmeldeseite „Passwort vergessen?“. Der Link gilt eine Stunde und nur einmal.
- **Inventar** (in der Garage über „Inventar“): Ersatzteile mit Anzahl, Warnschwelle, Preis, Lagerort und passendem Rad. „Einbauen“ legt das Teil als Komponente am Rad an, mustert ein Teil derselben Art aus und verringert den Bestand.
- **Anleitungen:** Bei jeder Wartungsregel öffnet „Anleitung“ geprüfte Links, hauptsächlich die Reparaturanleitungen von Park Tool (Englisch, teils mit Video) und für Wachs die von Silca. Die Links liegen im Katalog (`backend/app/catalog.py`, `GUIDES`) und lassen sich dort ändern.
- **Orte** (Statistik, Reiter „Orte“): Deine Hauptstadt (die Stadt mit den meisten Fahrtstarts) mit Anteil erkundeter Kacheln, weitere Städte und Länder. Grenzen holt BikeHelper einmalig je Ort von OpenStreetMap (Nominatim, höchstens eine Anfrage pro Sekunde) und speichert sie. Dabei gehen nur die Mittelpunkte einzelner Kacheln hinaus. Der Anteil eines Landes ist geschätzt (erkundete Kacheln geteilt durch Landfläche). Mit `GEO_ENABLED=false` ausschalten oder `NOMINATIM_URL` auf einen eigenen Server setzen.

### intervals.icu-Import (automatisch)

Neben dem Datei-Upload und dem Strava-Export ist intervals.icu der Weg für automatische Fahrten, auch von Wahoo-, Garmin- und Hammerhead-Radcomputern. Eine direkte Wahoo-Schnittstelle gibt es nicht mehr.

[intervals.icu](https://intervals.icu) sammelt Fahrten aus Garmin Connect, Wahoo, Zwift, Polar, Suunto und weiteren Diensten. BikeHelper holt sie von dort ab, das ist auch der Weg für Garmin ohne Strava (Garmin vergibt seine eigene API nur an Geschäftskunden):

1. Bei intervals.icu das Garmin-, Wahoo- oder Hammerhead-Konto verbinden, **nicht Strava**: Strava gibt Aktivitäten nicht über die Schnittstelle weiter.
2. Dort unter Einstellungen → Entwicklereinstellungen den persönlichen API-Schlüssel kopieren.
3. In BikeHelper unter Einstellungen → intervals.icu einfügen und „Verbinden“ klicken.

Danach werden alle 30 Minuten neue Fahrten als Originaldatei (FIT, GPX, TCX) geholt und dem gewählten Rad zugeordnet, sonst nach dem Radnamen in intervals.icu (Übereinstimmung mit dem Namen deines Rades). Doppelte Fahrten, etwa aus Strava-Export oder Upload, werden erkannt. Fahrten, die bei intervals.icu von Strava stammen, gibt intervals.icu nicht heraus und werden übersprungen. Der Schlüssel liegt in der Datenbank und wird nie wieder angezeigt. Unter Administration → Funktionen lässt sich der Import abschalten (oder mit `INTERVALS_ENABLED=false`). Nach dem Update erscheint einmal pro Konto ein kurzer Hinweis auf die neue Funktion.

**Radvorschläge:** Für Fahrten ohne Rad schlägt BikeHelper in der Fahrtenliste ein Rad vor (mit „Übernehmen“ je Fahrt oder für alle auf einmal). Grundlage sind deine bisherigen Zuordnungen: Gehören fast alle Fahrten mit demselben Radnamen (Strava-Export, intervals.icu) zu einem Rad, wird dieses vorgeschlagen. Sonst zählen ähnliche Fahrten mit gleichem Startort (etwa 400 m), ähnlicher Länge (±35 %) und ähnlicher Tageszeit, wenn mindestens 3 davon zu mindestens 75 % zu einem Rad gehören. Danach vergleicht BikeHelper die Merkmale der Fahrt mit dem, was bei jedem Rad bisher typisch war (ab 8 zugeordneten Fahrten je Rad, bei mindestens zwei Rädern): ob Leistungs- und Trittfrequenzdaten aufgezeichnet wurden (hast du nur an einem Rad einen Leistungsmesser, ist das ein sehr starker Hinweis), die Datenquelle, die Fahrtart (Gravel, Gelände, Straße, E-Bike, soweit Datei oder Export sie nennen) und das Durchschnittstempo. Vorgeschlagen wird nur, wenn ein Rad mit mindestens 90 % Wahrscheinlichkeit vorn liegt; die Begründung nennt die entscheidenden Merkmale. Einen Untergrund enthält eine GPX- oder FIT-Datei nicht; Fahrtart und Tempo sind nur Anhaltspunkte dafür. Ein Abgleich mit Kartendaten (OpenStreetMap) würde deine Strecken an einen fremden Dienst senden und ist deshalb nicht eingebaut. Ältere Fahrten werden nach dem Update im Hintergrund einmalig ausgewertet. Es ist eine Schätzung, nichts wird automatisch zugeordnet. Das Wetter wird nach jedem Import (Upload, Strava-Export, intervals.icu) sofort geholt.

### Rundgang für neue Konten

Nach der ersten Anmeldung führt ein kleiner Rundgang durch die App (Garage, Komponenten und Wartung, Fahrten importieren, Start, Ratgeber, Statistik, Gruppen, Einstellungen) und endet mit drei Startschritten: Rad anlegen, Fahrten importieren, Erinnerungen einrichten. Er hebt jeweils den passenden Menüpunkt hervor und lässt sich überspringen. Bestehende Konten bekommen ihn nicht automatisch; unter Einstellungen → Rundgang startest du ihn jederzeit selbst.

### Hinweis nach einem Update

Meldet sich ein Konto nach einem Update zum ersten Mal an, erscheint ein kleines Fenster mit der Versionskennung und den Änderungen seit der zuletzt gesehenen Version (höchstens die letzten 5). Neue Konten sehen es nicht. Die Texte stehen in `backend/app/data/changelog.json`, neueste Version oben. Zu jedem Update kommt dort ein Eintrag mit neuer `id` dazu (Datum, bei mehreren am selben Tag mit Zähler, zum Beispiel `2026-10-27.3`), `title` und `changes`; ein Eintrag kann optional eine `action` mit Knopf und Ziel haben.

### Gruppen

Unter „Gruppen“ gründest du eine Gruppe und lädst Freunde per E-Mail ein (ohne eingerichteten Mailversand bekommst du einen Link zum Weitergeben; die Einladung gilt 14 Tage und einmal). Es gibt Gruppenadministratoren (laden ein, ernennen weitere, entfernen Mitglieder, benennen oder löschen die Gruppe) und Mitglieder. Die Gruppenansicht zeigt die Rangliste für Woche, Monat, Jahr und gesamt (mit Blättern in frühere Zeiträume) mit allen Kennzahlen nebeneinander: Kilometer, Höhenmeter, Fahrzeit, Fahrten, Ø Tempo, längste Fahrt und aktive Tage, sortierbar nach jeder Spalte, dazu die Kilometer pro Woche der letzten 12 Wochen.

Neben der Einladung per E-Mail gibt es einen **Einladungslink** für mehrere Personen (30 Tage gültig, ein neuer Link ersetzt den alten, jederzeit abschaltbar). Er enthält einen Schlüssel: Wer noch kein BikeHelper-Konto hat, kann sich darüber auch bei geschlossener Registrierung ein Konto anlegen und tritt danach der Gruppe bei. Dasselbe gilt für Links aus der E-Mail-Einladung.

Zusätzlich zu den Grundwerten gibt jedes Mitglied pro Gruppe selbst frei (beim Beitritt und später unter „Meine Teilnahme“): **Fahrrhythmus** (Wochentage, Tageszeiten, Streckenlängen), **Rekorde**, **Belastung und Form** (geschätzt) und **Wetter** (Kilometer bei Regen, Temperaturen). Wer einen Bereich nicht freigibt, erscheint dort mit „–“. Der Verlauf im Diagramm folgt dem gewählten Zeitraum (Wochentage, Tage, Monate oder Jahre) und lässt sich aufsummieren.

**Weitere Gruppenfunktionen:** Gruppenadministratoren setzen ein **gemeinsames Ziel** (Kilometer, Höhenmeter oder Fahrten in einem Zeitraum) mit Fortschritt, Sollverlauf und Hochrechnung. Der Reiter **Duell** stellt zwei Mitglieder über 12 Wochen gegenüber, **Serien & Meilensteine** zeigt überschrittene Kilometermarken, die größte Steigerung zum Zeitraum davor, Fahrten pro Woche und die aktuelle Wochenserie (diese nur bei freigegebenen Rekorden). Pausierende Mitglieder zählen bei Ziel und Duell nicht mit.

Datenschutz: Geteilt werden nur diese Summen unter einem Anzeigenamen, den jedes Mitglied pro Gruppe selbst wählt. Keine Strecken, Karten, Räder, Wartung, Fahrtnamen oder E-Mail-Adressen. Jedes Mitglied kann seine Teilnahme je Gruppe pausieren oder die Gruppe verlassen; auch der Server-Administrator sieht keine Gruppeninhalte.

### Reifenkatalog

Beim Anlegen eines Reifensatzes suchst du den Reifen im Katalog (Marke, Modell, Breite) und die Felder werden gefüllt. Alles bleibt änderbar, und ein Reifen, der nicht im Katalog steht, lässt sich wie bisher von Hand eintragen. Zu jedem Satz kannst du die Karkasse (dünn, normal, Pannenschutz; der Ratgeber übernimmt sie für den Reifendruck), Gewicht, Rollwiderstand (Watt je Reifen) und einen Quell-Link speichern. Hast du mehrere Sätze mit Watt-Werten, zeigt jede Karte den Abstand zum besten Satz.

Der mitgelieferte Katalog (`backend/app/data/tires.csv`) ist bewusst klein: Er enthält nur Herstellerangaben (Breite, Gewicht, Art) mit Link zur Produktseite, aber keine Messwerte. Watt-Werte sind urheberrechtlich geschützte Messreihen einzelner Prüfstände und gehören nicht in ein öffentliches Repository. Du kannst sie unter Reifen → „Reifenkatalog erweitern“ als CSV für dein eigenes Konto einlesen (Spalten: `brand, model, category, width_mm, tubeless, weight_g, watts, watts_note, source_url, casing`). Eigene Einträge sieht nur dein Konto. Alternativ lädt „Reifenkatalog erweitern“ eine CSV von einer https-Adresse deiner Wahl (zum Beispiel eine Datei in einem eigenen GitHub-Repository; lokale und private Adressen sind gesperrt). Eine offene Reifendatenbank mit Rollwiderstandswerten, die man direkt einbinden könnte, habe ich nicht gefunden. Neue Zeilen für die mitgelieferte Liste kannst du per Pull Request ergänzen.

## Reifen: Lebensdauer und Sichtprüfung

Jeder Reifensatz zeigt, wie viele Kilometer er gefahren ist und (wenn du eine erwartete Lebensdauer einträgst) wie viele noch übrig sind. Dazu kommt ein Prüfintervall für die Sichtprüfung (Standard 1.000 km). Mit „Geprüft“ beginnt der Zähler neu. Ab 80 % wird ein Satz „bald fällig“, ab 100 % „fällig“, und der montierte Satz erscheint dann unter „Das steht an“. Erinnerungen per E-Mail oder ntfy gibt es dafür noch nicht.

## Einkaufslinks und Mechanics-Modus

**Einkaufslink:** Bei jeder Komponente und jedem Reifensatz kannst du einen Link hinterlegen, wo du das Teil nachkaufst (nur `http`/`https`). Er gehört zu deinem Rad, erscheint als „Nachkaufen“, steht in der Einkaufsliste und wird bei „Teil gewechselt“ ans neue Teil übernommen.

**Mechanics-Modus:** In den Einstellungen schaltest du den Bereich „Werkstatt“ in der Garage frei. Dort fragst du mit der E-Mail-Adresse eines Partner-Kontos den Zugriff an. Die Antwort verrät nicht, ob es das Konto gibt; ist der E-Mail-Versand eingerichtet, bekommt der Partner zusätzlich eine Mail. Er sieht die Anfrage auf seiner Startseite und lässt sie zu oder lehnt sie ab. Entziehen kann er den Zugriff jederzeit in den Einstellungen, der Mechaniker kann ihn zurückgeben.

Mit Zugriff darf der Mechaniker Räder, Komponenten, Wartungsregeln und -einträge, Messwerte und Reifensätze des Partners ansehen und ändern; neue Teile gehören dem Besitzer, Wartungseinträge tragen „durch <Mechaniker>“. Nicht möglich: ein Rad löschen sowie Zugriff auf Fahrten, Lager, Ziele, Orte, Gewicht und Einstellungen. Die Kilometer einer Komponente sind sichtbar, weil sie aus den Fahrten des Besitzers berechnet werden, die Fahrten selbst nicht. Pro Nutzer sind höchstens 5 Anfragen am Tag möglich.

## Statistik

Die Statistik hat diese Bereiche: **Übersicht** (Summen, Rekorde, Kacheln, Wetter), **Belastung**, **Leistung**, **Muster & Wetter**, **Räder**, **Strecken**, **Jahresrückblick**, **Ziele**, **Vergleiche**, **Orte** und **Heatmap**.

- **Belastung:** Fitness (Mittel der letzten 6 Wochen), Ermüdung (7 Tage) und Form (Fitness minus Ermüdung) nach dem Prinzip der gängigen Trainingsplattformen. Weil Strava-Exporte und Dateien nicht immer Puls oder Leistung enthalten, schätzt BikeHelper die Belastung einer Fahrt aus Fahrzeit, Höhenmetern und Tempo. Die Zahlen sind ein Gefühl für Tendenzen, keine Messung. Dazu Wochenwerte für Belastung, Kilometer und Höhenmeter.
- **Leistung:** Nur mit Fahrten, die Wattwerte enthalten. Beim Import speichert BikeHelper deine besten Durchschnittswerte über 5 s, 30 s, 1, 5, 20 und 60 Minuten (Pausen zählen als 0 W). Daraus entstehen die Leistungskurve (Allzeit, letzte 90 Tage, aktuelles Jahr, auch in W/kg, wenn du dein Gewicht in den Einstellungen einträgst) und die **FTP-Schätzung**: 95 % der besten 20 Minuten der letzten 90 Tage, mindestens aber die beste Stunde. Wer nie 20 Minuten voll ausgefahren ist, bekommt einen zu niedrigen Wert, es ist eine Schätzung und kein Test. Dazu der FTP-Verlauf je Monat, die Leistungszonen nach Coggan, die Stunden je Zone (aus der Durchschnittsleistung je Fahrt, daher grob) und eine Form-Kurve aus Trainingspunkten nach FTP. Ältere Fahrten ohne gespeicherten Sekundenverlauf werden aus dem Streckenprofil genähert (ab 5 Minuten, im Text als „≈“ markiert); für exakte Werte die Datei erneut importieren.
- **Muster & Wetter:** Dein Tempo nach Temperatur, Wind, Regen, Wochentag, Tageszeit, Jahreszeit und Ruhetagen vor der Fahrt, jeweils mit der Abweichung zu deinem Durchschnitt, dazu die typische Pause zwischen Fahrtagen. Gruppen mit weniger als 3 Fahrten werden nicht ausgewertet. Dazu kommt das Tempo nach Gegen- und Rückenwind, sobald eine Fahrt mit Windrichtung ausgewertet ist (bei Rundtouren heben sich Gegen- und Rückenwind teilweise auf).
- **Einfluss einer Fahrt:** Auf der Seite jeder Fahrt zeigt BikeHelper, was sie für Fitness, Ermüdung und Form bedeutet hat (Stand nach dieser Fahrt, mit und ohne sie gerechnet, dazu wie hart sie im Vergleich zu deinen letzten Fahrten war). Mit Leistungsdaten kommen die Änderung der FTP-Schätzung, neue Bestleistungen über 5 s bis 60 Minuten und die Intensität im Verhältnis zur FTP dazu.
- **Leistungsanalyse einer Fahrt:** Beim Import wertet BikeHelper Leistung, Puls und Trittfrequenz sekundengenau aus (Pausen über 10 s zählen nicht). Auf der Fahrtseite stehen dann Durchschnitt, normalisierte Leistung (NP), Variabilität, Intensität (IF), Trainingspunkte (TSS), Arbeit in kJ, die Zeit in den Wattzonen nach FTP, deine Spitzenwerte über 5 s bis 60 Minuten im Vergleich zu deinen Bestwerten, die Zeit in den Pulszonen (Prozent des Maximalpulses: Z1 unter 60, Z2 60–70, Z3 70–80, Z4 80–90, Z5 ab 90), Effizienz (Watt je Herzschlag), die Entkopplung von Leistung und Puls (erste gegen zweite Hälfte, ab 40 Minuten mit beiden Werten) und die Verteilung der Trittfrequenz. Der Maximalpuls steht in den Einstellungen, sonst gilt der höchste gemessene Wert. Ältere Fahrten ohne Sekundenauswertung werden aus dem Streckenprofil genähert; dieselbe Datei oder derselbe Strava-Export noch einmal hochgeladen ergänzt sie (es entsteht keine doppelte Fahrt).
- **Räder:** Alle Räder nebeneinander (Anteil, Tempo, Fahrtlänge, Höhenmeter je 100 km, Nässe, Leistung, Untergrund, ersetzte Teile je 1000 km). Darunter die **Prognose**, wann Wartungsregeln voraussichtlich fällig werden, gerechnet mit deinem Kilometertempo der letzten 8 Wochen bzw. dem Zeitintervall. Kosten werden nicht ausgewertet, weil BikeHelper keine Teilepreise je Rad speichert.
- **Strecken:** Erkennt Stammrunden: mindestens drei Fahrten mit etwa gleichem Start (400 m), ähnlicher Länge (±15 %) und zu mindestens 80 % gleichem Verlauf. Gezeigt werden Tempo, beste und schnellste Fahrt, die Entwicklung je Jahr und der Trend der letzten drei gegen die ersten drei Fahrten. Das läuft ausschließlich auf deinen eigenen Daten.
- **Jahresrückblick:** Kennzahlen mit Vergleich zum Vorjahr, stärkster Monat, Lieblingstag, meistgefahrenes Rad, Fahrten über 100 und 150 km, Frühstarter, Winterfahrten, Pausen, Extreme beim Wetter, neue Kacheln und die fünf längsten Fahrten.
- **Ziele:** Jahresziele für Kilometer, Höhenmeter, Fahrten und Fahrzeit mit Vergleich zum gleichmäßigen Plan, Hochrechnung aufs Jahresende und dem nötigen Wochenwert.
- **Vergleiche:** Kilometer pro Monat und Jahr, Räder pro Jahr, Tempo, Profil, Tageszeit, Jahreszeiten, Tempo pro Monat, Meilensteine (500 bis 100.000 km), Bestenlisten und Vergleiche wie Erdumrundungen.

Die Heatmap zoomt beim Öffnen auf dein Heimatgebiet und hat einen **Zeitverlauf**: Er spielt ab, wie die Touren über die Jahre dazugekommen sind (neue Fahrten leuchten kurz hell auf, dazu Zähler für Fahrten, Kilometer und Kacheln). Mit dem Regler springst du zu jedem Tag.  „Alles anzeigen“ zeigt auch Ausreißer wie Urlaubsfahrten.

## Kettenlehre, Erinnerungen und App

**Kettenlehre.** In der Kettenkarte trägst du über „Messwert eintragen“ die gemessene Längung in Prozent ein (Grenzwert 0,5 % bei 10-fach und mehr, 0,75 % bei 9-fach und weniger). Ab dann rechnet die Regel „Kette wechseln“ mit dem gemessenen Zustand statt nur mit Kilometern: Aus Messwert und gefahrenen Kilometern wird die Längung bis heute fortgeschrieben und die Restkilometer bis zum Grenzwert angezeigt. Nach einem Kettenwechsel zählen alte Messwerte nicht mehr.

**Erinnerungen.** Unter Einstellungen wählst du E-Mail und/oder Push per ntfy. BikeHelper meldet jede Wartung einmal, wenn sie „bald“ und einmal, wenn sie „fällig“ wird, nur zwischen 8 und 21 Uhr. Für ntfy installierst du die App ntfy aufs Handy und abonnierst dasselbe Thema (am besten zufällig, das Thema ist wie ein Passwort). Für E-Mail richtet der Administrator unter Administration → E-Mail-Versand einen SMTP-Server ein. Mit „Testnachricht senden“ prüfst du beides.

**E-Mail einrichten, Schritt für Schritt.** Melde dich als Administrator an, öffne Administration → E-Mail-Versand und trage ein, was dein Anbieter verlangt. Nach „Speichern“ gilt es sofort, ein Neustart ist nicht nötig:

| Anbieter | SMTP-Server | Port | Benutzername / Absender | Passwort |
|---|---|---|---|---|
| Gmail | `smtp.gmail.com` | `587` | deine Gmail-Adresse | App-Passwort (Google-Konto → Sicherheit → Bestätigung in zwei Schritten → App-Passwörter), nicht dein Login-Passwort |
| GMX | `mail.gmx.net` | `587` | deine GMX-Adresse | dein Passwort, SMTP-Versand muss in den GMX-Einstellungen erlaubt sein |
| web.de | `smtp.web.de` | `587` | deine web.de-Adresse | dein Passwort, SMTP muss freigeschaltet sein |
| Eigener Mailserver | dein Server | `587` oder `465` | Konto auf dem Server | dessen Passwort |

Klicke dann „Testmail an mich senden“. Danach können Nutzer unter Einstellungen → Erinnerungen „E-Mail“ einschalten. Die Mail geht an die Adresse des jeweiligen Kontos. Kommt ein Fehler, steht der Grund in der Meldung, bei Gmail meist ein falsches Passwort (das App-Passwort ohne Leerzeichen eintragen). Schau sonst in `docker compose logs backend`. Das Passwort wird nur in der Datenbank deines Servers gespeichert und nie wieder angezeigt.

**Als App installieren.** Über https (also über den Reverse Proxy) bietet der Browser „App installieren“ an, in den Einstellungen gibt es dafür einen Knopf. Die App öffnet ohne Browserleiste; ohne Verbindung erscheint die zuletzt geladene Oberfläche, Daten kommen immer live vom Server.

## Wetter

Nach jedem Import holt BikeHelper im Hintergrund das Wetter zu den Fahrten von [Open-Meteo](https://open-meteo.com) (Daten unter CC BY 4.0, kostenlos, ohne Schlüssel). Alle sechs Stunden wird nach neuen Fahrten gesucht; Fahrten der letzten Tage werden vorläufig ausgewertet und später aus dem Archiv korrigiert.

**Wetter entlang der Strecke:** Eine Fahrt mit Streckendaten wird in Abschnitte von etwa 12 km (höchstens 12) geteilt. Jeder Abschnitt bekommt das Wetter an seiner Position und zu seiner Zeit; die Zeit wird dabei gleichmäßig über die Strecke verteilt, ein konstantes Tempo ist also angenommen. Regen und Nässezeit addieren sich über die Abschnitte, Temperatur und Wind sind nach Dauer gewichtete Mittel. Fahrten ohne Strecke (zum Beispiel manche Importe) behalten das Wetter am Startpunkt. **Windrichtung:** Gespeichert sind die mittlere Richtung, aus der der Wind kam, und der mittlere Gegenwind in Fahrtrichtung (negativ heißt Rückenwind); der Gegenwind wird je Wegstück der Strecke berechnet, bei einer Rundtour heben sich Gegen- und Rückenwind also zum Teil auf. Ältere Fahrten, die bisher nur das Wetter am Startpunkt hatten, werden nach dem Update im Hintergrund einmalig neu ausgewertet. Das braucht deutlich mehr Abfragen als vorher und kann bei vielen Fahrten länger dauern; bei erreichtem Limit macht BikeHelper später automatisch weiter.

**Datenschutz:** Gesendet werden nur gerundete Koordinaten von Punkten entlang der Fahrten (0,1 Grad, rund 10 km) und Zeiträume, keine Namen oder Konten. Wer das nicht möchte, schaltet es unter Administration → Funktionen aus; dann gibt es kein Wetter und keine Nässe-Korrektur.

## Heatmap und Statistik

- **Heatmap** (in der Statistik als Tab): alle Strecken auf dunkler Karte, oft gefahrene Wege leuchten heller. Filter nach Jahr und Rad, optional mit den erkundeten Kacheln und dem größten Quadrat. Die Kartenkacheln lädt dein Browser vom Kartenanbieter (siehe unten).
- **Statistik:** Kennzahlen, Jahre und Monate, Kalender der Fahrtage, Wochentage, Startzeiten, Fahrtlängen, Rekorde, Serien, Räder, Temperatur und Nässe.
- **Kacheln:** Zoomstufe 14 (rund 1,5 km). Das größte Quadrat zählt nur vollständig erkundete Kacheln; ein „Gebiet“ umfasst auch diagonal verbundene Kacheln. Das kann von Statshunters leicht abweichen.
- Zeiten werden in der Zeitzone `TIMEZONE` ausgewertet (Standard `Europe/Berlin`).

## Sicherheit

Die App ist für den Betrieb hinter dem Nginx Proxy Manager mit HTTPS gedacht. Eingebaut sind:

- **Login-Drosselung:** Nach 8 Fehlversuchen pro E-Mail (oder 40 pro Adresse) in 15 Minuten antwortet die App mit „Zu viele Fehlversuche“. Registrierungen sind auf 10 pro Stunde und Adresse begrenzt. Die Zähler liegen im Speicher und sind nach einem Neustart leer. Hinter dem Nginx Proxy Manager zählt die echte Client-Adresse (`TRUSTED_PROXIES=1`); läuft BikeHelper ohne Proxy davor, setze `TRUSTED_PROXIES=0`.
- **Anmeldung:** Tokens gelten 7 Tage (`TOKEN_EXPIRE_DAYS`). Unter Einstellungen → Sicherheit kannst du das Passwort ändern oder dich überall abmelden. Beides macht alle älteren Tokens ungültig.
- **Konto löschen:** Einstellungen → Sicherheit entfernt das Konto samt aller Daten vom Server (Passwort nötig).
- **Einladungen:** Die Registrierung ist standardmäßig geschlossen (`ALLOW_REGISTRATION=false`). Das erste Konto ist immer erlaubt und wird Administrator. Weitere Nutzer brauchen einen Einladungscode: Administration → Einladungen → „Neue Einladung erzeugen“ → „Link kopieren“ und der Person schicken. Der Link öffnet direkt die Registrierung mit eingetragenem Code, und jeder Code gilt einmal. Unter Administration → Konten und Rollen siehst du alle Konten (nur E-Mail, Rolle, Status; keine Räder, Fahrten oder sonstige Inhalte). Du kannst Rollen vergeben (Administrator oder Nutzer), Konten sperren oder samt Daten löschen. Die offene Registrierung schaltest du unter Administration → Zugang ein und aus.
- **Updates per Knopf:** Unter Administration → Updates siehst du die installierte Version, suchst nach neuen Änderungen und startest das Update mit „Jetzt aktualisieren“. Die Seite ist dabei ein bis zwei Minuten kurz weg und lädt danach selbst neu. Schlägt der Bau fehl, bleibt die laufende Version unverändert. Dahinter steckt der Container `updater`: Er hat keinen veröffentlichten Port, nimmt nur Anfragen des Backends mit Token an und darf Docker steuern, was Root-Rechten auf dem Server entspricht. Wer das nicht will, entfernt den Block `updater` aus der `docker-compose.yml` und aktualisiert weiter mit `./install.sh update`. Den ersten Start des Update-Dienstes (und spätere Änderungen am Dienst selbst) erledigt `./install.sh update` im Terminal.
- **Live-Protokoll:** Unter Administration → Live-Protokoll siehst du live (alle paar Sekunden aktualisiert), wer sich wann angemeldet hat, fehlgeschlagene Anmeldungen, grobe Aktionen der Nutzer, Verwaltungsvorgänge und Serverfehler, mit Filter. Aus Datenschutzgründen steht dort nur der Bereich („Lager: gelöscht“), nie ein Name, eine Zahl, ein Passwort oder eine IP-Adresse. Einträge bleiben 30 Tage.
- **Administration:** Nur Administratoren sehen den Bereich. Dort stellst du alles ein, was früher in der `.env` stand: Registrierung, Anmeldedauer, Proxys, öffentliche Adresse, Zeitzone, E-Mail, ntfy, Wetter, Ortssuche und Karten. Die Werte in der `.env` sind nur Startwerte; was du in der Administration speicherst, hat Vorrang. In der `.env` bleiben nur `SECRET_KEY`, `POSTGRES_PASSWORD`, `WEB_PORT` und die Datenbankadresse.
- **Header:** Der Webserver setzt Content-Security-Policy, `X-Frame-Options`, `nosniff`, `Referrer-Policy` und `Permissions-Policy`. API-Antworten sind nicht cachebar.
- **Uploads:** Eine Fahrtdatei darf höchstens 50 MB haben, ein Strava-Export entpackt höchstens 40 GB, die CSV darin höchstens 300 MB. Der Webserver nimmt höchstens 4 GB (Export) bzw. 1 GB (Fahrtdateien) an.

Was du selbst tun musst: HTTPS im Nginx Proxy Manager aktivieren (inklusive „Force SSL“ und HSTS), einen langen `SECRET_KEY` setzen, die Registrierung nach dem Anlegen deines Kontos unter Administration → Zugang geschlossen lassen und die Ports von Datenbank und Backend nicht nach außen öffnen. Wer die App mit anderen teilt, sollte regelmäßig ein Backup der Datenbank ziehen (siehe Backup).

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

## Proxmox: als LXC-Container (ein Befehl)

Auf dem Proxmox-Host (als root) legt dieser Befehl einen Debian-12-Container mit Docker-Unterstützung an und installiert BikeHelper darin:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Tillhnz/Bikehelper/main/proxmox/bikehelper-lxc.sh)"
```

Standard sind 2 Kerne, 2 GB RAM und 16 GB Festplatte, unprivilegiert, mit DHCP und Start beim Hochfahren. Anpassen vor dem Befehl, zum Beispiel `CT_RAM=4096 CT_IP=192.168.178.50/24 CT_GW=192.168.178.1 bash -c "…"`; alle Optionen stehen im Kopf von `proxmox/bikehelper-lxc.sh`. Danach gelten die üblichen Befehle im Container: `pct exec <ID> -- bash -c 'cd ~/Bikehelper && ./install.sh update'`, `backup` und `lock`; der Update-Knopf im Admin-Bereich funktioniert ebenfalls. Der Container braucht die Optionen Nesting und keyctl (setzt das Skript). Auf ZFS-Speicher kann Docker auf einen langsameren Speichertreiber zurückfallen.

## Mit fertigen Docker-Images (ohne Bauen)

Für alle, die ohnehin mit Docker arbeiten: GitHub baut bei jeder Änderung Images für amd64 und arm64 und legt sie in der GitHub Container Registry ab (`ghcr.io/tillhnz/bikehelper-backend` und `…-frontend`). Du brauchst nur Docker mit Compose, kein Git und keinen Build:

```bash
mkdir bikehelper && cd bikehelper
curl -fsSLO https://raw.githubusercontent.com/Tillhnz/Bikehelper/main/docker-compose.ghcr.yml
curl -fsSL https://raw.githubusercontent.com/Tillhnz/Bikehelper/main/.env.example -o .env
# .env anpassen: POSTGRES_PASSWORD, SECRET_KEY (openssl rand -hex 32), PUBLIC_URL
docker compose -f docker-compose.ghcr.yml up -d
```

Die Seite läuft danach auf `http://<server-ip>:8080` (`WEB_PORT`). Aktualisieren:

```bash
docker compose -f docker-compose.ghcr.yml pull && docker compose -f docker-compose.ghcr.yml up -d
```

Mit `BIKEHELPER_TAG=<Version oder Commit>` in der `.env` bleibst du auf einem bestimmten Stand (Standard `latest`). Der Update-Knopf im Admin-Bereich gehört zur Variante mit `install.sh` und fehlt hier, weil der Update-Dienst Zugriff auf den Docker-Socket bräuchte. Die Daten liegen im Volume `db_data`; Sicherung wie unter „Backup“ beschrieben mit `pg_dump` im Container `db`.

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

**Große Uploads (Strava-Export):** Der Nginx Proxy Manager bricht lange Anfragen standardmäßig nach 60 Sekunden ab und puffert den Upload erst komplett. Dann steht die Fortschrittsanzeige kurz vor Schluss bei 100 %, und es kommt ein Fehler (502/504), obwohl die Datei ankommt. Trage im Proxy Host unter „Advanced“ → „Custom Nginx Configuration“ ein:

```
client_max_body_size 8g;
proxy_request_buffering off;
proxy_read_timeout 900s;
proxy_send_timeout 900s;
send_timeout 900s;
```

BikeHelper erkennt in diesem Fall einen bereits angekommenen Upload und zeigt dessen Fortschritt an, statt ihn noch einmal zu verlangen.

Die Registrierung ist standardmäßig geschlossen, nur das erste Konto ist immer erlaubt. Weitere Nutzer lädst du als Administrator per Link ein (siehe Abschnitt Sicherheit).

## Tests und CI

Bei jedem Push prüft GitHub Actions (`.github/workflows/ci.yml`) das Backend (ruff und pytest), baut das Frontend und prüft `install.sh` und die Compose-Datei. Lokal: `cd backend && pip install -r requirements-dev.txt && python -m pytest`.

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

Die Daten liegen im Docker-Volume `db_data`. Sicherungen entstehen so:

- Im Admin-Bereich unter Übersicht → Sicherungen mit „Jetzt sichern“, und automatisch vor jedem Update. Sie landen im Ordner `backups/` auf dem Server, die letzten 14 bleiben. Sie lassen sich bewusst nicht über die Oberfläche herunterladen, denn sie enthalten die Daten aller Konten.
- Im Terminal: `./install.sh backup`.
- **Auf eine NFS-Freigabe, verschlüsselt:** Ist die Freigabe im Container eingebunden (z. B. `/mnt/nas/bikehelper`), setzt `./install.sh backup-dir /mnt/nas/bikehelper` den Ordner (prüft vorher, ob dort geschrieben werden kann). Dann `./install.sh backup-key`: erzeugt ein age-Schlüsselpaar, im Container bleibt nur der öffentliche Teil, der private wird einmal angezeigt und gehört in deinen Passwortmanager. Ab dann sind alle Sicherungen (Terminal, Admin-Knopf, vor jedem Update) als `.sql.gz.age` verschlüsselt; ohne den privaten Schlüssel kann sie niemand lesen, auch nicht der NAS-Betreiber. `restore` fragt den Schlüssel ab und prüft ihn, bevor etwas überschrieben wird. Die laufende Datenbank bleibt bewusst auf der lokalen Platte, denn Postgres auf NFS riskiert beschädigte Daten (Dateisperren, Verbindungsabbrüche). Bei unprivilegierten LXC-Containern muss die Freigabe für die verschobene Root-Kennung (meist 100000) beschreibbar sein.
- Zurückspielen (ersetzt alle aktuellen Daten, mit Rückfrage): `./install.sh restore backups/bikehelper-JJJJMMTT-HHMMSS.sql.gz`.

Updates aus dem Admin-Bereich prüfen nach dem Neustart, ob BikeHelper antwortet. Wenn nicht, gehen sie selbst zur vorherigen Version zurück.

Zusätzlich lohnt sich ein regelmäßiges Proxmox-Backup der VM bzw. des LXC.

## Struktur

```
backend/    FastAPI, SQLAlchemy, Auth (JWT), Garage-API, Tests
frontend/   React + Vite, nginx als Auslieferung und /api-Proxy
```

## In Home Assistant einbetten

Aus Sicherheitsgründen verbietet BikeHelper, in fremde Seiten eingebettet zu werden (sonst könnte eine fremde Seite ihn unsichtbar einbetten und Klicks unterschieben). Unter **Administration → Zugang → In andere Seiten einbetten** trägst du die Adressen ein, unter denen du Home Assistant öffnest (z. B. `https://ha.example.de http://192.168.1.20:8123`). Die Änderung wirkt sofort: Der Webserver fragt bei jedem Seitenaufruf beim Backend nach. In Home Assistant legst du eine Webseiten-Karte oder einen Webseiten-Eintrag im Dashboard mit der Adresse von BikeHelper an; im eingebetteten Fenster meldest du dich beim ersten Mal einmal an.
