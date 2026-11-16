#!/usr/bin/env bash
# Sprachmodell Trainer as its own LXC container on Proxmox VE (Debian 12 + Docker).
# Run in the Proxmox shell:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Wadim-dev/sprachmodell_ha/claude/project-thread-ab1adh/sprachmodell_trainer/proxmox.sh)" -- <HA_URL> <KEY>
# HA_URL e.g. http://192.168.178.190:8123, KEY = trainer key shown in the Sprachmodell panel (Trainer section).
# Optional environment: CT_CORES (4), CT_RAM_MB (6144), CT_DISK_GB (40), CT_STORAGE (first storage for containers), CT_BRIDGE (vmbr0)
set -euo pipefail

HA_URL="${1:-}"; KEY="${2:-}"
if [ -z "$HA_URL" ] || [ -z "$KEY" ]; then echo "Usage: proxmox.sh <HA_URL> <KEY>"; exit 1; fi
command -v pct >/dev/null || { echo "Run this in the Proxmox VE shell."; exit 1; }

CORES="${CT_CORES:-4}"; RAM="${CT_RAM_MB:-6144}"; DISK="${CT_DISK_GB:-40}"; BRIDGE="${CT_BRIDGE:-vmbr0}"
STORAGE="${CT_STORAGE:-$(pvesm status --content rootdir --enabled 1 | awk 'NR>1{print $1; exit}')}"
NAME="sprachmodell-trainer"
BILD="ghcr.io/wadim-dev/sprachmodell-trainer:latest"

if pct list | awk 'NR>1{print $NF}' | grep -qx "$NAME"; then
  echo "A container named $NAME already exists – nothing changed."; exit 1
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
pct exec "$ID" -- docker run -d --name sprachmodell-trainer --restart unless-stopped \
  -e HA_URL="$HA_URL" -e SCHLUESSEL="$KEY" -e TRAINER_NAME="Proxmox" \
  -v sprachmodell-trainer:/data "$BILD"

echo
echo "Done. Container $ID runs the trainer; it shows up as connected in the Sprachmodell panel within a minute."
echo "Logs: pct exec $ID -- docker logs -f sprachmodell-trainer"
echo "Update: pct exec $ID -- bash -c 'docker pull $BILD && docker rm -f sprachmodell-trainer' and run the docker line again (data stays in the volume)."
