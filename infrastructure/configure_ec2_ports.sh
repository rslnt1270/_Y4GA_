#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# Verifica y/o agrega reglas de entrada en los Security Groups de ambas
# instancias EC2 de testing.
#
# Uso: bash configure_ec2_ports.sh [--my-ip] [ubuntu|ec2|all]
#   --my-ip  restringe reglas a tu IP pública (recomendado en producción)
#   ubuntu   solo instancia Ubuntu (us-east-1, puerto 6285)
#   ec2      solo instancia EC2    (us-east-2, puerto 8000)
#   all      ambas (default)
#
# Requiere: aws cli configurado (aws configure) con permisos EC2

set -euo pipefail

# ── Instancia Ubuntu (us-east-1) — SG conocido: sg-0486cecc1922afa30 ─────────
UBUNTU_DNS="ec2-34-228-82-92.compute-1.amazonaws.com"
UBUNTU_REGION="us-east-1"
UBUNTU_PORT=6285
UBUNTU_SG="sg-0486cecc1922afa30"   # launch-wizard-3

# ── Instancia EC2 testing (us-east-2) ────────────────────────────────────────
EC2_DNS="ec2-13-58-246-32.us-east-2.compute.amazonaws.com"
EC2_REGION="us-east-2"
EC2_PORT=8000

# ── Parseo de argumentos ──────────────────────────────────────────────────────
CIDR="0.0.0.0/0"
TARGET="all"

for ARG in "$@"; do
  case "$ARG" in
    --my-ip)
      MY_IP=$(curl -s https://checkip.amazonaws.com)
      CIDR="${MY_IP}/32"
      echo "Modo restringido: solo tu IP ($CIDR)"
      ;;
    ubuntu|ec2|all) TARGET="$ARG" ;;
  esac
done

# ── Función: asegurar regla en un SG ─────────────────────────────────────────
ensure_port() {
  local REGION="$1"
  local SG="$2"
  local PORT="$3"
  local LABEL="$4"

  EXISTING=$(aws ec2 describe-security-groups \
    --region "$REGION" --group-ids "$SG" \
    --query "SecurityGroups[0].IpPermissions[?FromPort==\`$PORT\` && ToPort==\`$PORT\` && IpProtocol=='tcp']" \
    --output text 2>/dev/null || echo "")

  if [ -n "$EXISTING" ]; then
    echo "  ✓ Puerto $PORT ya abierto en $SG ($LABEL)"
  else
    aws ec2 authorize-security-group-ingress \
      --region "$REGION" --group-id "$SG" \
      --protocol tcp --port "$PORT" --cidr "$CIDR"
    echo "  + Puerto $PORT agregado en $SG ($LABEL) desde $CIDR"
  fi
}

# ── Función: obtener SG de una instancia por DNS ──────────────────────────────
get_sg() {
  local REGION="$1"
  local DNS="$2"
  aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=dns-name,Values=$DNS" \
    --query "Reservations[0].Instances[0].SecurityGroups[0].GroupId" \
    --output text 2>/dev/null || echo ""
}

# ── Función: mostrar reglas actuales ─────────────────────────────────────────
show_rules() {
  local REGION="$1"
  local SG="$2"
  aws ec2 describe-security-groups \
    --region "$REGION" --group-ids "$SG" \
    --query "SecurityGroups[0].IpPermissions[*].{Protocolo:IpProtocol,Puerto:FromPort,Origen:IpRanges[0].CidrIp}" \
    --output table
}

echo "========================================================"
echo " Configuración de Security Groups — Django Testing"
echo "========================================================"

# ── Ubuntu (us-east-1, puerto 6285) ──────────────────────────────────────────
if [[ "$TARGET" == "ubuntu" || "$TARGET" == "all" ]]; then
  echo ""
  echo "── Ubuntu (us-east-1) ─────────────────────────────────"
  echo "  DNS : $UBUNTU_DNS"
  echo "  SG  : $UBUNTU_SG (launch-wizard-3)"
  echo "  Port: $UBUNTU_PORT"
  ensure_port "$UBUNTU_REGION" "$UBUNTU_SG" 22         "SSH"
  ensure_port "$UBUNTU_REGION" "$UBUNTU_SG" "$UBUNTU_PORT" "Django"
  echo ""
  echo "  Reglas actuales:"
  show_rules "$UBUNTU_REGION" "$UBUNTU_SG"
  echo ""
  echo "  Para iniciar Django:"
  echo "    ssh -i develomen.pem ubuntu@$UBUNTU_DNS"
  echo "    source ~/venv/bin/activate && cd ~/venv/www/testing"
  echo "    python manage.py runserver 0.0.0.0:$UBUNTU_PORT"
  echo "    → http://$UBUNTU_DNS:$UBUNTU_PORT/"
fi

# ── EC2 testing (us-east-2, puerto 8000) ─────────────────────────────────────
if [[ "$TARGET" == "ec2" || "$TARGET" == "all" ]]; then
  echo ""
  echo "── EC2 testing (us-east-2) ────────────────────────────"
  echo "  DNS : $EC2_DNS"
  echo "  Port: $EC2_PORT"

  EC2_SG=$(get_sg "$EC2_REGION" "$EC2_DNS")
  if [ -z "$EC2_SG" ] || [ "$EC2_SG" = "None" ]; then
    echo "  ADVERTENCIA: no se pudo obtener el SG automáticamente."
    echo "  Verifica en consola AWS → EC2 → Instancias → Security groups"
  else
    echo "  SG  : $EC2_SG"
    ensure_port "$EC2_REGION" "$EC2_SG" 22       "SSH"
    ensure_port "$EC2_REGION" "$EC2_SG" "$EC2_PORT" "Django"
    echo ""
    echo "  Reglas actuales:"
    show_rules "$EC2_REGION" "$EC2_SG"
  fi
  echo ""
  echo "  Para iniciar Django:"
  echo "    ssh -i YAGA_development_pm.pem ec2-user@$EC2_DNS"
  echo "    source ~/venv/bin/activate && cd ~/venv/www/testing"
  echo "    python manage.py runserver 0.0.0.0:$EC2_PORT"
  echo "    → http://$EC2_DNS:$EC2_PORT/"
fi

echo ""
echo "========================================================"
echo " LISTO"
echo "========================================================"
