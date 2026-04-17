#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# Configura Security Group de EC2 para exponer Django (puerto 8000)
# Uso: bash configure_ec2_ports.sh [--my-ip]
# Requiere: aws cli configurado (aws configure) con permisos EC2

set -euo pipefail

EC2_PUBLIC_DNS="ec2-13-58-246-32.us-east-2.compute.amazonaws.com"
EC2_REGION="us-east-2"
DJANGO_PORT=8000

echo "=== Configuración de puertos EC2 para Django testing ==="
echo "Instancia: $EC2_PUBLIC_DNS"
echo "Región:    $EC2_REGION"
echo ""

# Obtener Instance ID a partir del DNS público
INSTANCE_ID=$(aws ec2 describe-instances \
  --region "$EC2_REGION" \
  --filters "Name=dns-name,Values=$EC2_PUBLIC_DNS" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text)

if [ "$INSTANCE_ID" = "None" ] || [ -z "$INSTANCE_ID" ]; then
  echo "ERROR: No se encontró la instancia con DNS $EC2_PUBLIC_DNS"
  echo "Verifica que la instancia esté corriendo y las credenciales AWS estén configuradas."
  exit 1
fi

echo "Instance ID: $INSTANCE_ID"

# Obtener Security Group ID de la instancia
SG_ID=$(aws ec2 describe-instances \
  --region "$EC2_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].SecurityGroups[0].GroupId" \
  --output text)

echo "Security Group: $SG_ID"
echo ""

# Determinar CIDR de origen
if [[ "${1:-}" == "--my-ip" ]]; then
  MY_IP=$(curl -s https://checkip.amazonaws.com)
  CIDR="${MY_IP}/32"
  echo "Modo restringido: solo tu IP ($CIDR)"
else
  CIDR="0.0.0.0/0"
  echo "Modo abierto: cualquier IP (solo para pruebas)"
fi

# Verificar si la regla ya existe para evitar duplicados
EXISTING=$(aws ec2 describe-security-groups \
  --region "$EC2_REGION" \
  --group-ids "$SG_ID" \
  --query "SecurityGroups[0].IpPermissions[?FromPort==\`$DJANGO_PORT\` && ToPort==\`$DJANGO_PORT\` && IpProtocol=='tcp']" \
  --output text)

if [ -n "$EXISTING" ]; then
  echo "La regla para el puerto $DJANGO_PORT ya existe en $SG_ID. No se modificó."
else
  aws ec2 authorize-security-group-ingress \
    --region "$EC2_REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port "$DJANGO_PORT" \
    --cidr "$CIDR"
  echo "Regla agregada: TCP $DJANGO_PORT desde $CIDR en $SG_ID"
fi

# Regla SSH (22) — verificar que exista para no perder acceso
SSH_EXISTING=$(aws ec2 describe-security-groups \
  --region "$EC2_REGION" \
  --group-ids "$SG_ID" \
  --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\` && ToPort==\`22\` && IpProtocol=='tcp']" \
  --output text)

if [ -z "$SSH_EXISTING" ]; then
  echo "ADVERTENCIA: No hay regla SSH (22). Agregando para no perder acceso..."
  aws ec2 authorize-security-group-ingress \
    --region "$EC2_REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port 22 \
    --cidr "0.0.0.0/0"
fi

echo ""
echo "=== Reglas actuales del Security Group $SG_ID ==="
aws ec2 describe-security-groups \
  --region "$EC2_REGION" \
  --group-ids "$SG_ID" \
  --query "SecurityGroups[0].IpPermissions[*].{Proto:IpProtocol,Desde:FromPort,Hasta:ToPort,CIDR:IpRanges[0].CidrIp}" \
  --output table

echo ""
echo "=== Pasos siguientes en la instancia EC2 ==="
echo "1. Conectar: ssh -i YAGA_development_pm.pem ec2-user@$EC2_PUBLIC_DNS"
echo "2. Activar venv: source ~/venv/bin/activate  (o el path de tu venv)"
echo "3. Navegar: cd ~/venv/www/testing"
echo "4. Agregar ALLOWED_HOSTS en testing/settings.py:"
echo "   ALLOWED_HOSTS = ['$EC2_PUBLIC_DNS', 'localhost', '127.0.0.1']"
echo "5. Iniciar Django: python manage.py runserver 0.0.0.0:$DJANGO_PORT"
echo "6. Abrir en navegador: http://$EC2_PUBLIC_DNS:$DJANGO_PORT/"
