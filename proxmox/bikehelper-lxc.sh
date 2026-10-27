#!/usr/bin/env bash
# BikeHelper als LXC-Container auf einem Proxmox-VE-Host einrichten.
#
# Auf dem Proxmox-Host (als root) ausführen:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Tillhnz/Bikehelper/main/proxmox/bikehelper-lxc.sh)"
#
# Das Skript legt einen Debian-12-Container mit Docker-Unterstützung (Nesting) an und führt darin die normale Installation
# (install.sh) aus. Danach gelten alle Befehle von install.sh im Container (Update, Sicherung, Registrierung sperren).
#
# Optionale Umgebungsvariablen (vor dem Befehl setzen, z. B.  CT_RAM=4096 bash -c "…"):
#   CT_ID=<nummer>            Container-Nummer (Standard: nächste freie)
#   CT_NAME=bikehelper        Rechnername
#   CT_CORES=2                CPU-Kerne
#   CT_RAM=2048               Arbeitsspeicher in MB (der erste Start baut das Frontend, weniger als 2048 ist riskant)
#   CT_DISK=16                Festplatte in GB
#   CT_STORAGE=<name>         Speicher für die Festplatte (Standard: local-lvm, sonst der erste passende)
#   CT_BRIDGE=vmbr0           Netzwerkbrücke
#   CT_IP=dhcp                oder feste Adresse, z. B. 192.168.178.50/24 (dann auch CT_GW setzen)
#   CT_GW=<gateway>           Gateway bei fester Adresse
#   CT_PASSWORD=<passwort>    Root-Passwort im Container (ohne Angabe: Zugang nur über  pct enter <ID>  vom Host)
#   CT_UNPRIVILEGED=1         1 = unprivilegierter Container (empfohlen), 0 = privilegiert
#   BIKEHELPER_PUBLIC_URL=…   Öffentliche Adresse (Standard: http://<Container-IP>:8080)
set -euo pipefail

info() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m✘\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Bitte als root auf dem Proxmox-Host ausführen."
command -v pct >/dev/null 2>&1 && command -v pveam >/dev/null 2>&1 && command -v pvesm >/dev/null 2>&1 \
  || die "pct, pveam oder pvesm fehlen. Dieses Skript gehört auf einen Proxmox-VE-Host, nicht in einen Container oder auf einen normalen Server."

CT_NAME="${CT_NAME:-bikehelper}"
CT_CORES="${CT_CORES:-2}"
CT_RAM="${CT_RAM:-2048}"
CT_DISK="${CT_DISK:-16}"
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"
CT_IP="${CT_IP:-dhcp}"
CT_UNPRIVILEGED="${CT_UNPRIVILEGED:-1}"
REPO_RAW="${BIKEHELPER_RAW:-https://raw.githubusercontent.com/Tillhnz/Bikehelper/main}"

# Container-Nummer
CT_ID="${CT_ID:-$(pvesh get /cluster/nextid)}"
if pct status "$CT_ID" >/dev/null 2>&1; then die "Die Nummer $CT_ID ist schon vergeben. Setze CT_ID=<andere Nummer>."; fi

# Speicher für die Festplatte
if [ -z "${CT_STORAGE:-}" ]; then
  mapfile -t roots < <(pvesm status -content rootdir | awk 'NR>1 && $3=="active" {print $1}')
  [ "${#roots[@]}" -gt 0 ] || die "Kein Speicher für Container-Festplatten gefunden. Setze CT_STORAGE=<name> (siehe: pvesm status)."
  CT_STORAGE="${roots[0]}"
  for s in "${roots[@]}"; do [ "$s" = "local-lvm" ] && CT_STORAGE="local-lvm"; done
fi

# Speicher für Vorlagen
mapfile -t tmpl_stores < <(pvesm status -content vztmpl | awk 'NR>1 && $3=="active" {print $1}')
[ "${#tmpl_stores[@]}" -gt 0 ] || die "Kein Speicher für Container-Vorlagen gefunden (pvesm status -content vztmpl)."
TEMPLATE_STORAGE="${tmpl_stores[0]}"
for s in "${tmpl_stores[@]}"; do [ "$s" = "local" ] && TEMPLATE_STORAGE="local"; done

# Debian-12-Vorlage holen
info "Suche die Debian-12-Vorlage …"
pveam update >/dev/null 2>&1 || warn "pveam update ist fehlgeschlagen, nutze die vorhandene Liste."
TEMPLATE="$(pveam available --section system | awk '{print $2}' | grep -E '^debian-12-standard_.*_amd64\.tar\.(zst|gz)$' | sort -V | tail -n 1 || true)"
[ -n "$TEMPLATE" ] || die "Keine Debian-12-Vorlage gefunden. Prüfe die Internetverbindung des Hosts (pveam available --section system)."
if ! pveam list "$TEMPLATE_STORAGE" | grep -q "$TEMPLATE"; then
  info "Lade $TEMPLATE herunter …"
  pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi

# Netzwerk
if [ "$CT_IP" = "dhcp" ]; then
  NET="name=eth0,bridge=${CT_BRIDGE},ip=dhcp"
else
  [ -n "${CT_GW:-}" ] || die "Bei fester Adresse bitte auch CT_GW=<Gateway> setzen."
  NET="name=eth0,bridge=${CT_BRIDGE},ip=${CT_IP},gw=${CT_GW}"
fi

info "Lege Container $CT_ID ($CT_NAME) an: ${CT_CORES} Kerne, ${CT_RAM} MB RAM, ${CT_DISK} GB auf ${CT_STORAGE} …"
args=(
  "$CT_ID" "${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}"
  --hostname "$CT_NAME" --cores "$CT_CORES" --memory "$CT_RAM" --swap 512
  --rootfs "${CT_STORAGE}:${CT_DISK}" --net0 "$NET"
  --unprivileged "$CT_UNPRIVILEGED" --features nesting=1,keyctl=1,fuse=1
  --onboot 1 --ostype debian --description "BikeHelper (Docker im LXC)"
)
[ -n "${CT_PASSWORD:-}" ] && args+=(--password "$CT_PASSWORD")
pct create "${args[@]}"

info "Starte den Container …"
pct start "$CT_ID"

# Auf Netzwerk warten
ip=""
for _ in $(seq 1 60); do
  ip="$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
  if [ -n "$ip" ] && pct exec "$CT_ID" -- getent hosts deb.debian.org >/dev/null 2>&1; then break; fi
  sleep 2
done
[ -n "$ip" ] || die "Der Container hat kein Netzwerk bekommen. Prüfe CT_BRIDGE und DHCP. Aufräumen: pct stop $CT_ID; pct destroy $CT_ID"
ok "Container läuft mit der Adresse $ip."

PUBLIC_URL="${BIKEHELPER_PUBLIC_URL:-http://${ip}:8080}"
info "Installiere BikeHelper im Container (Docker, Bauen und Starten dauern einige Minuten) …"
if ! pct exec "$CT_ID" -- bash -c "set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl git ca-certificates
  curl -fsSL ${REPO_RAW}/install.sh | BIKEHELPER_PUBLIC_URL='${PUBLIC_URL}' bash"; then
  warn "Die Installation im Container ist fehlgeschlagen."
  warn "Der Container bleibt zur Fehlersuche bestehen:  pct enter $CT_ID   (dann:  cd ~/Bikehelper && ./install.sh logs)"
  warn "Häufige Ursache: Docker startet im LXC nicht. Prüfe Nesting/keyctl (pct config $CT_ID) und bei ZFS-Speicher den Docker-Speichertreiber."
  exit 1
fi

cat <<EOF

────────────────────────────────────────────────────────
 BikeHelper läuft im Container $CT_ID ($CT_NAME).

 Öffnen:          ${PUBLIC_URL}
 In den Container: pct enter $CT_ID
 Aktualisieren:    pct exec $CT_ID -- bash -c 'cd ~/Bikehelper && ./install.sh update'
                   (oder im Admin-Bereich auf den Update-Knopf)
 Sichern:          pct exec $CT_ID -- bash -c 'cd ~/Bikehelper && ./install.sh backup'

 Danach: Konto anlegen, dann neue Registrierungen sperren:
   pct exec $CT_ID -- bash -c 'cd ~/Bikehelper && ./install.sh lock'
────────────────────────────────────────────────────────
EOF
