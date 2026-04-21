#!/usr/bin/env bash
# © YAGA Project — Todos los derechos reservados
# Túnel SSH → postgres contenedor en _Y4GA_Pruebas (NO produccion)
# Resuelve IP EC2 via AWS CLI y IP Docker via docker inspect (no hardcoded)
# Uso: ./scripts/mcp_postgres_tunnel.sh [start|stop|status]

set -euo pipefail

INSTANCE_ID="i-09ed69e9862e38253"   # _Y4GA_Pruebas (dev, sin datos productivos)
REGION="us-east-2"
SSH_USER="ubuntu"
SSH_KEY="${HOME}/Documentos/Project_Y4GA_/cloud_y4ga.pem"
LOCAL_PORT=5433   # 5432 en uso por postgres local
PIDFILE="/tmp/yaga_mcp_pg_tunnel.pid"

cmd="${1:-start}"

case "$cmd" in
  status)
    if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "tunnel running (pid $(cat "$PIDFILE"))"
      exit 0
    fi
    echo "tunnel not running"; exit 1 ;;
  stop)
    if [[ -f "$PIDFILE" ]]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi
    echo "tunnel stopped"; exit 0 ;;
  start) ;;
  *) echo "usage: $0 [start|stop|status]"; exit 2 ;;
esac

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDFILE"))"; exit 0
fi

# Guard: evita apuntar accidentalmente a YAGA_Backend (prod con PII de conductores)
name=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].Tags[?Key==`Name`].Value|[0]' --output text)
if [[ "$name" != "_Y4GA_Pruebas" ]]; then
  echo "ABORT: instance $INSTANCE_ID is '$name', expected _Y4GA_Pruebas"; exit 3
fi

ec2_ip=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
[[ "$ec2_ip" == "None" || -z "$ec2_ip" ]] && { echo "instance has no public IP"; exit 4; }

pg_ip=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=8 \
  "${SSH_USER}@${ec2_ip}" \
  "docker inspect yaga_postgres --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'")

echo "tunnel: localhost:${LOCAL_PORT} → ${ec2_ip} → ${pg_ip}:5432 (via ssh)"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
    -o ExitOnForwardFailure=yes -N -f \
    -L "${LOCAL_PORT}:${pg_ip}:5432" "${SSH_USER}@${ec2_ip}"

pgrep -f "ssh.*-L ${LOCAL_PORT}:${pg_ip}:5432.*${ec2_ip}" > "$PIDFILE"
echo "started (pid $(cat "$PIDFILE"))"
