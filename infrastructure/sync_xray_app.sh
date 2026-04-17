#!/bin/bash
# © YAGA Project — Todos los derechos reservados
# Transfiere el app Django "xray" de la instancia Ubuntu (us-east-1)
# a la instancia EC2 (us-east-2) y configura settings.py + urls.py.
#
# Uso: bash infrastructure/sync_xray_app.sh
# Prerequisito: ambas PEM accesibles desde la máquina que ejecuta este script.

set -euo pipefail

# ── Configuración de instancias ─────────────────────────────────────────────
UBUNTU_HOST="ubuntu@ec2-34-228-82-92.compute-1.amazonaws.com"
UBUNTU_PEM="develomen.pem"
UBUNTU_XRAY_PATH="/home/ubuntu/venv/www/testing/xray"

EC2_HOST="ec2-user@ec2-13-58-246-32.us-east-2.compute.amazonaws.com"
EC2_PEM="YAGA_development_pm.pem"
EC2_TESTING_PATH="/home/ec2-user/venv/www/testing"
EC2_XRAY_PATH="$EC2_TESTING_PATH/xray"

DJANGO_PROJECT="testing"   # nombre del subdirectorio con settings.py y urls.py
VENV_ACTIVATE="/home/ec2-user/venv/bin/activate"

TMP_DIR=$(mktemp -d)
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15"

echo "========================================================"
echo " Sync xray: Ubuntu → EC2 testing environment"
echo "========================================================"
echo "  Origen : $UBUNTU_HOST:$UBUNTU_XRAY_PATH"
echo "  Destino: $EC2_HOST:$EC2_XRAY_PATH"
echo "  Tmp    : $TMP_DIR"
echo ""

# ── 1. Verificar PEM keys ────────────────────────────────────────────────────
for PEM in "$UBUNTU_PEM" "$EC2_PEM"; do
  if [ ! -f "$PEM" ]; then
    echo "ERROR: No se encontró $PEM en el directorio actual."
    echo "Ejecuta este script desde donde estén las llaves PEM."
    exit 1
  fi
  chmod 400 "$PEM"
done

# ── 2. Descargar xray desde Ubuntu a máquina local ──────────────────────────
echo "[1/4] Descargando xray desde Ubuntu..."
scp $SSH_OPTS -i "$UBUNTU_PEM" -r \
  "$UBUNTU_HOST:$UBUNTU_XRAY_PATH" \
  "$TMP_DIR/"
echo "      OK — archivos en $TMP_DIR/xray/"

# ── 3. Subir xray al EC2 ────────────────────────────────────────────────────
echo ""
echo "[2/4] Subiendo xray al EC2..."
# Primero limpiar destino por si quedó incompleto
ssh $SSH_OPTS -i "$EC2_PEM" "$EC2_HOST" \
  "rm -rf $EC2_XRAY_PATH && mkdir -p $EC2_XRAY_PATH"

scp $SSH_OPTS -i "$EC2_PEM" -r \
  "$TMP_DIR/xray/." \
  "$EC2_HOST:$EC2_XRAY_PATH/"
echo "      OK — xray copiado a $EC2_XRAY_PATH"

# ── 4. Configurar settings.py en EC2 ────────────────────────────────────────
echo ""
echo "[3/4] Configurando settings.py en EC2..."
ssh $SSH_OPTS -i "$EC2_PEM" "$EC2_HOST" bash <<REMOTE_SETTINGS
set -euo pipefail
SETTINGS="$EC2_TESTING_PATH/$DJANGO_PROJECT/settings.py"

# Agregar ALLOWED_HOSTS si no está configurado para el host público
if ! grep -q "ec2-13-58-246-32" "\$SETTINGS"; then
  sed -i "s/ALLOWED_HOSTS = \[\]/ALLOWED_HOSTS = ['ec2-13-58-246-32.us-east-2.compute.amazonaws.com', 'localhost', '127.0.0.1']/" "\$SETTINGS"
  sed -i "s/ALLOWED_HOSTS = \['/ALLOWED_HOSTS = ['ec2-13-58-246-32.us-east-2.compute.amazonaws.com', '/" "\$SETTINGS" 2>/dev/null || true
  echo "      ALLOWED_HOSTS actualizado"
fi

# Agregar 'xray' a INSTALLED_APPS si no existe
if ! grep -q "'xray'" "\$SETTINGS" && ! grep -q '"xray"' "\$SETTINGS"; then
  sed -i "s/'django.contrib.staticfiles',/'django.contrib.staticfiles',\n    'polls',\n    'xray',/" "\$SETTINGS"
  # Si ya tenía polls, evitar duplicado
  python3 -c "
content = open('\$SETTINGS').read()
if content.count(\"'polls'\") > 1:
    idx = content.rfind(\"'polls'\")
    content = content[:idx] + content[idx:].replace(\"'polls',\n    \", '', 1)
    open('\$SETTINGS', 'w').write(content)
print('INSTALLED_APPS actualizado')
"
else
  echo "      xray ya estaba en INSTALLED_APPS"
fi

# Asegurar polls también en INSTALLED_APPS
if ! grep -q "'polls'" "\$SETTINGS" && ! grep -q '"polls"' "\$SETTINGS"; then
  sed -i "s/'django.contrib.staticfiles',/'django.contrib.staticfiles',\n    'polls',/" "\$SETTINGS"
  echo "      polls agregado a INSTALLED_APPS"
fi

echo "      settings.py OK"
REMOTE_SETTINGS

# ── 5. Configurar urls.py en EC2 ─────────────────────────────────────────────
echo ""
echo "[4/4] Configurando urls.py en EC2..."
ssh $SSH_OPTS -i "$EC2_PEM" "$EC2_HOST" bash <<REMOTE_URLS
set -euo pipefail
URLS="$EC2_TESTING_PATH/$DJANGO_PROJECT/urls.py"

# Hacer backup
cp "\$URLS" "\$URLS.bak"

python3 -c "
import re

content = open('\$URLS').read()

# Agregar import include si falta
if 'include' not in content:
    content = content.replace('from django.urls import path', 'from django.urls import path, include')
    print('include importado')

# Agregar ruta polls si no existe
if 'polls' not in content:
    content = re.sub(
        r'(urlpatterns\s*=\s*\[)',
        r\"\1\n    path('polls/', include('polls.urls')),\",
        content
    )
    print('ruta polls agregada')

# Agregar ruta xray si no existe
if 'xray' not in content:
    content = re.sub(
        r'(urlpatterns\s*=\s*\[)',
        r\"\1\n    path('xray/', include('xray.urls')),\",
        content
    )
    print('ruta xray agregada')

open('\$URLS', 'w').write(content)
print('urls.py OK')
"

echo ""
echo "--- urls.py resultante ---"
cat "\$URLS"
REMOTE_URLS

# ── 6. Correr migraciones en EC2 ─────────────────────────────────────────────
echo ""
echo "[Extra] Ejecutando migraciones en EC2..."
ssh $SSH_OPTS -i "$EC2_PEM" "$EC2_HOST" bash <<REMOTE_MIGRATE
set -euo pipefail
cd $EC2_TESTING_PATH
source $VENV_ACTIVATE 2>/dev/null || true
python manage.py migrate --run-syncdb 2>&1 | tail -20
echo "Migraciones OK"
REMOTE_MIGRATE

# ── Limpieza ─────────────────────────────────────────────────────────────────
rm -rf "$TMP_DIR"

echo ""
echo "========================================================"
echo " COMPLETADO"
echo "========================================================"
echo ""
echo " Para iniciar Django en EC2:"
echo "   ssh -i $EC2_PEM $EC2_HOST"
echo "   source ~/venv/bin/activate"
echo "   cd ~/venv/www/testing"
echo "   python manage.py runserver 0.0.0.0:8000"
echo ""
echo " Abrir en navegador:"
echo "   http://ec2-13-58-246-32.us-east-2.compute.amazonaws.com:8000/xray/"
echo "   http://ec2-13-58-246-32.us-east-2.compute.amazonaws.com:8000/polls/"
echo ""
echo " Asegúrate de que el puerto 8000 esté abierto (ver configure_ec2_ports.sh)"
