#!/usr/bin/env bash
# Wake Word Studio Trainer as its own LXC container on Proxmox VE (Debian 12 + Docker).
# Run in the Proxmox shell:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Wadim-dev/wake-word-studio_ha/main/sprachmodell_trainer/proxmox.sh)" -- <HA_URL> <KEY>
# HA_URL e.g. http://192.168.1.10:8123, KEY = trainer key shown in Wake Word Studio (Settings -> Trainer).
# Optional environment: CT_CORES (4), CT_RAM_MB (6144), CT_DISK_GB (40), CT_STORAGE (first storage for containers), CT_BRIDGE (vmbr0)
#
# The trainer updates itself every time the container starts: restarting the container
# (Proxmox, or the "Restart" button of the Proxmox integration in Home Assistant) installs the newest version.
# Existing container from an older script: run this script once with the single argument "update".
set -euo pipefail

command -v pct >/dev/null || { echo "Run this in the Proxmox VE shell."; exit 1; }
NAME="wake-word-studio-trainer"
ALT="sprachmodell-trainer"          # name used by earlier versions
BILD="ghcr.io/wadim-dev/wake-word-studio-trainer:latest"
ENV="/etc/$NAME.env"

# Files inside the container: settings, update script, boot service
einrichten() {  # $1 = container id, settings come from /tmp/$NAME.env on the host
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
GRENZE_JETZT=\$(docker inspect -f '{{.HostConfig.Memory}}' $NAME 2>/dev/null || echo 0)
if [ -n "\$NEU" ] && { [ "\$NEU" != "\$LAEUFT" ] || [ "\$GRENZE_JETZT" = "0" ]; }; then
  docker rm -f $NAME $ALT >/dev/null 2>&1 || true
  # Keep the downloaded base data of an earlier installation
  VOLUME=$NAME
  docker volume inspect $ALT >/dev/null 2>&1 && VOLUME=$ALT
  # Memory limit of this LXC container also for Docker, so the trainer sees it and adapts
  GRENZE_MB=\$(( \$(awk '/^MemTotal:/{print \$2}' /proc/meminfo) * 9 / 10 / 1024 ))
  docker run -d --name $NAME --restart unless-stopped --memory \${GRENZE_MB}m --env-file $ENV \\
    -v "\$VOLUME":/data "\$BILD" >/dev/null
  docker image prune -af >/dev/null 2>&1 || true
  echo "Trainer updated"
else
  docker start $NAME >/dev/null 2>&1 || true
  echo "Trainer up to date"
fi
EOF
  cat >"$tmp/dienst" <<EOF
[Unit]
Description=Wake Word Studio Trainer: update and start
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/$NAME-update

[Install]
WantedBy=multi-user.target
EOF
  pct push "$id" "/tmp/$NAME.env" "$ENV" --perms 600
  pct push "$id" "$tmp/aktualisieren" "/usr/local/bin/$NAME-update" --perms 755
  pct push "$id" "$tmp/dienst" "/etc/systemd/system/$NAME-update.service"
  rm -rf "$tmp" "/tmp/$NAME.env"
  # Service and files of earlier versions
  pct exec "$id" -- bash -c "systemctl disable --now $ALT-aktualisieren.service >/dev/null 2>&1; rm -f /etc/systemd/system/$ALT-aktualisieren.service /usr/local/bin/$ALT-aktualisieren /etc/$ALT.env" || true
  pct exec "$id" -- systemctl daemon-reload
  pct exec "$id" -- systemctl enable "$NAME-update.service" >/dev/null 2>&1
  pct exec "$id" -- "/usr/local/bin/$NAME-update"
}

# Update / switch an existing container to self-updating
if [ "${1:-}" = "update" ]; then
  ID="$(pct list | awk -v n="$NAME" -v a="$ALT" 'NR>1 && ($NF==n || $NF==a) {print $1; exit}')"
  [ -n "$ID" ] || { echo "No container named $NAME found."; exit 1; }
  if [ -n "${2:-}" ] && [ -n "${3:-}" ]; then   # update <HA_URL> <KEY>: settings given again
    printf 'HA_URL=%s\nKEY=%s\nTRAINER_NAME=Proxmox\n' "$2" "$3" >"/tmp/$NAME.env"
  elif pct exec "$ID" -- test -f "$ENV"; then
    pct pull "$ID" "$ENV" "/tmp/$NAME.env"
  elif pct exec "$ID" -- test -f "/etc/$ALT.env"; then
    pct pull "$ID" "/etc/$ALT.env" "/tmp/$NAME.env"
  else
    for c in "$NAME" "$ALT"; do
      pct exec "$ID" -- docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" 2>/dev/null \
        | grep -E '^(HA_URL|KEY|SCHLUESSEL|TRAINER_NAME|THREADS|ZIEL_FEHLAUSLOESER|SCHRITTE)=' >"/tmp/$NAME.env.neu" || true
      grep -qE '^(KEY|SCHLUESSEL)=' "/tmp/$NAME.env.neu" && break
    done
    if grep -qE '^(KEY|SCHLUESSEL)=' "/tmp/$NAME.env.neu"; then
      mv "/tmp/$NAME.env.neu" "/tmp/$NAME.env"
    else
      rm -f "/tmp/$NAME.env.neu"
      echo "Settings not found. Run: proxmox.sh update <HA_URL> <KEY>"; exit 1
    fi
  fi
  pct exec "$ID" -- docker rm -f "$NAME" "$ALT" >/dev/null 2>&1 || true   # recreated from the settings file
  einrichten "$ID"
  echo "Done. Container $ID runs the newest trainer and updates itself on every restart."
  exit 0
fi

HA_URL="${1:-}"; KEY="${2:-}"
if [ -z "$HA_URL" ] || [ -z "$KEY" ]; then echo "Usage: proxmox.sh <HA_URL> <KEY>   or   proxmox.sh update"; exit 1; fi

CORES="${CT_CORES:-4}"; RAM="${CT_RAM_MB:-6144}"; DISK="${CT_DISK_GB:-40}"; BRIDGE="${CT_BRIDGE:-vmbr0}"
STORAGE="${CT_STORAGE:-$(pvesm status --content rootdir --enabled 1 | awk 'NR>1{print $1; exit}')}"
if pct list | awk 'NR>1{print $NF}' | grep -qxE "$NAME|$ALT"; then
  echo "A trainer container already exists - nothing changed. To update it: run this script with the argument update."; exit 1
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
  --description "Wake Word Studio Trainer (own wake words) - github.com/Wadim-dev/wake-word-studio_ha"
pct start "$ID"

echo "== Waiting for network"
for _ in $(seq 1 60); do pct exec "$ID" -- ping -c1 -W1 deb.debian.org >/dev/null 2>&1 && break; sleep 2; done

echo "== Docker"
pct exec "$ID" -- bash -c "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io ca-certificates >/dev/null"

echo "== Trainer"
printf 'HA_URL=%s\nKEY=%s\nTRAINER_NAME=Proxmox\n' "$HA_URL" "$KEY" >"/tmp/$NAME.env"
einrichten "$ID"

echo
echo "Done. Container $ID runs the trainer; it shows up as connected in Wake Word Studio within a minute."
echo "Logs: pct exec $ID -- docker logs -f $NAME"
echo "Updates: restart the container - it installs the newest trainer by itself."
