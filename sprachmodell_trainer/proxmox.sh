#!/usr/bin/env bash
# Sprachmodell Trainer as its own LXC container on Proxmox VE (Debian 12 + Docker).
# Run in the Proxmox shell:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Wadim-dev/sprachmodell_ha/claude/project-thread-ab1adh/sprachmodell_trainer/proxmox.sh)" -- <HA_URL> <KEY>
# HA_URL e.g. http://192.168.178.190:8123, KEY = trainer key shown in the Sprachmodell panel (Trainer section).
# Optional environment: CT_CORES (4), CT_RAM_MB (6144), CT_DISK_GB (40), CT_STORAGE (first storage for containers), CT_BRIDGE (vmbr0)
#
# The trainer updates itself every time the container starts: restarting the container
# (Proxmox, or the "Restart" button of the Proxmox integration in Home Assistant) installs the newest version.
# Existing container from an older script: run this script once with the single argument "update".
set -euo pipefail

command -v pct >/dev/null || { echo "Run this in the Proxmox VE shell."; exit 1; }
NAME="sprachmodell-trainer"
BILD="ghcr.io/wadim-dev/sprachmodell-trainer:latest"

# Files inside the container: settings, update script, boot service
einrichten() {  # $1 = container id, settings come from /tmp/sprachmodell-trainer.env on the host
  local id="$1" tmp
  tmp="$(mktemp -d)"
  cat >"$tmp/aktualisieren" <<EOF
#!/bin/bash
# Newest trainer image; recreate the container when the image changed. Data stays in the volume.
set -u
BILD="$BILD"
for _ in \$(seq 1 30); do docker pull -q "\$BILD" >/dev/null 2>&1 && break; sleep 10; done
NEU=\$(docker image inspect -f '{{.Id}}' "\$BILD" 2>/dev/null || true)
LAEUFT=\$(docker inspect -f '{{.Image}}' $NAME 2>/dev/null || true)
if [ -n "\$NEU" ] && [ "\$NEU" != "\$LAEUFT" ]; then
  docker rm -f $NAME >/dev/null 2>&1 || true
  docker run -d --name $NAME --restart unless-stopped --env-file /etc/sprachmodell-trainer.env \\
    -v sprachmodell-trainer:/data "\$BILD" >/dev/null
  docker image prune -f >/dev/null 2>&1 || true
  echo "Trainer updated"
else
  docker start $NAME >/dev/null 2>&1 || true
  echo "Trainer up to date"
fi
EOF
  cat >"$tmp/dienst" <<EOF
[Unit]
Description=Sprachmodell Trainer: update and start
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sprachmodell-trainer-aktualisieren

[Install]
WantedBy=multi-user.target
EOF
  pct push "$id" /tmp/sprachmodell-trainer.env /etc/sprachmodell-trainer.env --perms 600
  pct push "$id" "$tmp/aktualisieren" /usr/local/bin/sprachmodell-trainer-aktualisieren --perms 755
  pct push "$id" "$tmp/dienst" /etc/systemd/system/sprachmodell-trainer-aktualisieren.service
  rm -rf "$tmp" /tmp/sprachmodell-trainer.env
  pct exec "$id" -- systemctl daemon-reload
  pct exec "$id" -- systemctl enable sprachmodell-trainer-aktualisieren.service >/dev/null 2>&1
  pct exec "$id" -- /usr/local/bin/sprachmodell-trainer-aktualisieren
}

# Update / switch an existing container to self-updating
if [ "${1:-}" = "update" ]; then
  ID="$(pct list | awk -v n="$NAME" 'NR>1 && $NF==n {print $1; exit}')"
  [ -n "$ID" ] || { echo "No container named $NAME found."; exit 1; }
  if [ -n "${2:-}" ] && [ -n "${3:-}" ]; then   # update <HA_URL> <KEY>: settings given again
    printf 'HA_URL=%s\nSCHLUESSEL=%s\nTRAINER_NAME=Proxmox\n' "$2" "$3" >/tmp/sprachmodell-trainer.env
  elif pct exec "$ID" -- test -f /etc/sprachmodell-trainer.env; then
    pct pull "$ID" /etc/sprachmodell-trainer.env /tmp/sprachmodell-trainer.env
  else
    pct exec "$ID" -- docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$NAME" 2>/dev/null \
      | grep -E '^(HA_URL|SCHLUESSEL|TRAINER_NAME|THREADS|ZIEL_FEHLAUSLOESER|SCHRITTE)=' >/tmp/sprachmodell-trainer.env.neu || true
    if grep -q '^SCHLUESSEL=' /tmp/sprachmodell-trainer.env.neu; then
      mv /tmp/sprachmodell-trainer.env.neu /tmp/sprachmodell-trainer.env
    elif ! grep -qs '^SCHLUESSEL=' /tmp/sprachmodell-trainer.env; then
      rm -f /tmp/sprachmodell-trainer.env.neu
      echo "Settings not found. Run: proxmox.sh update <HA_URL> <KEY>"; exit 1
    fi
    rm -f /tmp/sprachmodell-trainer.env.neu
  fi
  pct exec "$ID" -- docker rm -f "$NAME" >/dev/null 2>&1 || true   # recreated from the settings file
  einrichten "$ID"
  echo "Done. Container $ID runs the newest trainer and updates itself on every restart."
  exit 0
fi

HA_URL="${1:-}"; KEY="${2:-}"
if [ -z "$HA_URL" ] || [ -z "$KEY" ]; then echo "Usage: proxmox.sh <HA_URL> <KEY>   or   proxmox.sh update"; exit 1; fi

CORES="${CT_CORES:-4}"; RAM="${CT_RAM_MB:-6144}"; DISK="${CT_DISK_GB:-40}"; BRIDGE="${CT_BRIDGE:-vmbr0}"
STORAGE="${CT_STORAGE:-$(pvesm status --content rootdir --enabled 1 | awk 'NR>1{print $1; exit}')}"
if pct list | awk 'NR>1{print $NF}' | grep -qx "$NAME"; then
  echo "A container named $NAME already exists – nothing changed. To update it: run this script with the argument update."; exit 1
fi

echo "== Template"
pveam update >/dev/null
TPL="$(pveam available --section system | awk '/debian-12-standard/{print $2}' | sort -V | tail -1)"
pveam list local | grep -q "$TPL" || pveam download local "$TPL"

ID="$(pvesh get /cluster/nextid)"
echo "== Container $ID ($CORES cores, $RAM MB, $DISK GB on $STORAGE)"
pct create "$ID" "local:vztmpl/$TPL" --hostname "$NAME" --cores "$CORES" --memory "$RAM" --swap 1024 \
  --rootfs "$STORAGE:$DISK" --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp" \
  --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1 --startup order=90 \
  --description "Sprachmodell Trainer (wake words) – github.com/Wadim-dev/sprachmodell_ha"
pct start "$ID"

echo "== Waiting for network"
for _ in $(seq 1 60); do pct exec "$ID" -- ping -c1 -W1 deb.debian.org >/dev/null 2>&1 && break; sleep 2; done

echo "== Docker"
pct exec "$ID" -- bash -c "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io ca-certificates >/dev/null"

echo "== Trainer"
printf 'HA_URL=%s\nSCHLUESSEL=%s\nTRAINER_NAME=Proxmox\n' "$HA_URL" "$KEY" >/tmp/sprachmodell-trainer.env
einrichten "$ID"

echo
echo "Done. Container $ID runs the trainer; it shows up as connected in the Sprachmodell panel within a minute."
echo "Logs: pct exec $ID -- docker logs -f $NAME"
echo "Updates: restart the container – it installs the newest trainer by itself."
